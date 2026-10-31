"""Capa de datos del Segmentador de Clientes.

Guarda los clientes en SQLite, valida todo lo que entra (con las reglas de
validacion.py), asigna el grupo con el modelo K-means vigente y deja cada cambio
en una bitácora con lo necesario para deshacerlo. Los datos originales del
análisis quedan en una tabla aparte que no se modifica, para poder restaurarlos
y para que cualquier cifra se pueda rastrear hasta ellos.
"""
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from . import modelo as km
from .formato import numero
from .validacion import ErrorValidacion, clave_de, validar_cliente, validar_codigo

NOMBRE_BASE = "segmentador_clientes.db"
DATOS_INICIALES = Path(__file__).resolve().parent / "datos_iniciales" / "clientes.csv"
FUENTE = "UCI Online Retail (Chen, 2015): clientes de una tienda en línea del Reino Unido, dic-2010 a dic-2011"
COLUMNAS = ("cliente", "pais", "mercado", "recencia_dias", "frecuencia", "valor_total", "ticket_promedio",
            "unidades", "productos_distintos", "devoluciones", "estado", "grupo")
OBLIGATORIAS = ("cliente", "pais", "recencia_dias", "frecuencia", "valor_total")
ORDENABLES = set(COLUMNAS)
_ESQUEMA_CLIENTES = """(
    cliente TEXT PRIMARY KEY,
    pais TEXT NOT NULL,
    mercado TEXT NOT NULL CHECK (mercado IN ('Reino Unido', 'Internacional')),
    recencia_dias INTEGER NOT NULL CHECK (recencia_dias >= 0),
    frecuencia INTEGER NOT NULL CHECK (frecuencia >= 1),
    valor_total REAL NOT NULL CHECK (valor_total > 0),
    ticket_promedio REAL NOT NULL,
    unidades INTEGER NOT NULL CHECK (unidades >= 0),
    productos_distintos INTEGER NOT NULL CHECK (productos_distintos >= 0),
    devoluciones INTEGER NOT NULL CHECK (devoluciones >= 0),
    estado TEXT NOT NULL CHECK (estado IN ('Activo', 'Inactivo')),
    grupo INTEGER NOT NULL CHECK (grupo >= 1))"""


def carpeta_portable():
    """Carpeta donde vive el programa: la base se guarda al lado, sin instalar nada.

    Si esa carpeta no deja escribir (por ejemplo, un disco protegido de la sala),
    se usa la carpeta SegmentadorClientes en el perfil del usuario.
    """
    if getattr(sys, "frozen", False):
        carpeta = Path(sys.executable).resolve().parent
        if carpeta.name == "MacOS" and carpeta.parent.name == "Contents":
            carpeta = carpeta.parent.parent.parent  # al lado del .app, no adentro
    else:
        carpeta = Path(__file__).resolve().parent.parent
    try:
        prueba = carpeta / ".escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return carpeta
    except OSError:
        respaldo = Path.home() / "SegmentadorClientes"
        respaldo.mkdir(exist_ok=True)
        return respaldo


def leer_csv(ruta, con_grupo=False):
    """Lee y valida un CSV de clientes, separado por coma o por punto y coma. Todo o nada.

    Exige encabezado con al menos cliente, pais, recencia_dias, frecuencia y valor_total.
    Mercado, estado y ticket promedio se vuelven a calcular. Con `con_grupo` también
    devuelve la columna grupo (y nombre_grupo si viene), que se usa solo en la carga inicial.
    """
    try:
        texto = Path(ruta).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ErrorValidacion("El archivo no está en UTF-8. Guárdelo desde Excel como «CSV UTF-8».")
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    if not lineas:
        raise ErrorValidacion("El archivo está vacío.")
    separador = ";" if lineas[0].count(";") > lineas[0].count(",") else ","
    lector = csv.reader(lineas, delimiter=separador)
    encabezado = [clave_de(c).replace(" ", "_") for c in next(lector)]
    faltan = [c for c in OBLIGATORIAS if c not in encabezado]
    if faltan:
        raise ErrorValidacion("Al archivo le faltan columnas: " + ", ".join(faltan) + ". La primera fila debe ser "
                              "el encabezado (cliente, pais, recencia_dias, frecuencia, valor_total...).")
    if con_grupo and "grupo" not in encabezado:
        con_grupo = False
    filas, errores, vistos, paises = [], [], set(), []
    for n, valores in enumerate(lector, 2):
        datos = dict(zip(encabezado, valores))
        try:
            fila = validar_cliente(datos, paises)
            if fila["cliente"] in vistos:
                raise ErrorValidacion(f"el cliente {fila['cliente']} está repetido.")
            if con_grupo:
                grupo = datos.get("grupo", "").strip()
                if not grupo.isdigit() or int(grupo) < 1:
                    raise ErrorValidacion(f"el grupo debe ser un entero desde 1; recibí «{grupo}».")
                fila["grupo"] = int(grupo)
                fila["nombre_grupo"] = datos.get("nombre_grupo", "").strip()
        except ErrorValidacion as e:
            errores.append(f"Línea {n}: {e}")
            continue
        vistos.add(fila["cliente"])
        if fila["pais"] not in paises:
            paises.append(fila["pais"])
        filas.append(fila)
    if errores:
        sobran = f"\n... y {len(errores) - 6} errores más." if len(errores) > 6 else ""
        raise ErrorValidacion("No se importó nada.\n" + "\n".join(errores[:6]) + sobran)
    if not filas:
        raise ErrorValidacion("El archivo no trae filas de clientes.")
    return filas


class Almacen:
    """Base SQLite de clientes. Toda escritura pasa por aquí y queda en la bitácora."""

    def __init__(self, ruta=None, inicial=None):
        self.ruta = Path(ruta) if ruta else carpeta_portable() / NOMBRE_BASE
        self.db = sqlite3.connect(self.ruta)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS configuracion (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS clientes {_ESQUEMA_CLIENTES};
            CREATE TABLE IF NOT EXISTS clientes_originales {_ESQUEMA_CLIENTES};
            CREATE TABLE IF NOT EXISTS bitacora (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                accion TEXT NOT NULL,
                detalle TEXT NOT NULL,
                reversa TEXT NOT NULL,
                deshecho INTEGER NOT NULL DEFAULT 0);
            """
        )
        self._modelo = None
        if not self.db.execute("SELECT 1 FROM clientes_originales LIMIT 1").fetchone():
            self._carga_inicial(Path(inicial) if inicial else DATOS_INICIALES)

    def _carga_inicial(self, ruta):
        """Primera vez: copia fija de los datos del análisis y modelo K-means de partida.

        Se vuelve a entrenar K-means con la misma receta del análisis y se comprueba que dé los
        mismos grupos del archivo. Si coinciden, ese es el modelo; si no (otra versión de las
        librerías, por ejemplo), se respetan los grupos del archivo y los centroides se calculan
        como el promedio de cada grupo. En los dos casos los grupos que se ven son los del análisis.
        """
        filas = leer_csv(ruta, con_grupo=True)
        if "grupo" in filas[0]:
            del_archivo = [f["grupo"] for f in filas]
            k = max(del_archivo)
            nombres = {f["grupo"]: f["nombre_grupo"] for f in filas if f.get("nombre_grupo")}
            entrenado, grupos = km.entrenar(filas, k) if km.K_MINIMO <= k <= km.K_MAXIMO else (None, None)
            if entrenado is not None and list(grupos) == del_archivo:
                entrenado.origen = "Análisis de la Fase 4 (reproducido al cargar)"
                modelo, nota = entrenado, f"K-means con k = {k} reproduce los grupos del archivo"
            else:
                modelo = km.desde_grupos(filas, del_archivo, nombres or None)
                nota = f"se respetan los {k} grupos del archivo"
            for f in filas:
                f.pop("nombre_grupo", None)
        else:
            modelo, grupos = km.entrenar(filas, km.K_DEFECTO)
            for f, g in zip(filas, grupos):
                f["grupo"] = int(g)
            nota = f"grupos calculados con K-means, k = {km.K_DEFECTO}"
        with self.db:
            self.db.executemany(self._insertar("clientes_originales"), [self._tupla(f) for f in filas])
            self._poner_clientes(filas)
            self._poner_config("modelo_original", json.dumps(modelo.a_dict(), ensure_ascii=False))
            self._poner_modelo(modelo)
            self._poner_config("fuente", f"{FUENTE}. Archivo: {ruta.name}")
            self._registrar("Carga inicial", f"{numero(len(filas))} clientes de {ruta.name}; {nota}", {})

    # ---------- lectura ----------

    def clientes(self, texto="", grupo=None, estado=None, orden="cliente", descendente=False):
        """Clientes filtrados por código o país (sin tildes ni mayúsculas), grupo y estado."""
        condiciones, parametros = [], []
        if grupo:
            condiciones.append("grupo = ?")
            parametros.append(int(grupo))
        if estado:
            condiciones.append("estado = ?")
            parametros.append(estado)
        donde = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
        columna = orden if orden in ORDENABLES else "cliente"
        sentido = "DESC" if descendente else "ASC"
        filas = [dict(f) for f in self.db.execute(
            f"SELECT * FROM clientes{donde} ORDER BY {columna} {sentido}, cliente", parametros)]
        buscado = clave_de(texto)
        if buscado:
            filas = [f for f in filas if buscado in f["cliente"].lower() or buscado in clave_de(f["pais"])]
        return filas

    def cliente(self, codigo):
        fila = self.db.execute("SELECT * FROM clientes WHERE cliente = ?", (str(codigo).strip(),)).fetchone()
        return dict(fila) if fila else None

    def cantidad(self):
        return self.db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]

    def paises(self):
        return [f[0] for f in self.db.execute("SELECT DISTINCT pais FROM clientes ORDER BY pais")]

    @property
    def modelo(self):
        if self._modelo is None:
            self._modelo = km.Modelo.desde_dict(json.loads(self._config("modelo")))
        return self._modelo

    @property
    def fuente(self):
        return self._config("fuente")

    def perfil(self):
        filas = self.clientes()
        return km.perfil(filas, [f["grupo"] for f in filas], self.modelo)

    def bitacora(self):
        filas = self.db.execute("SELECT id, fecha, accion, detalle, deshecho FROM bitacora ORDER BY id DESC")
        return [dict(f) for f in filas]

    def diferencias_con_originales(self):
        """Lista en palabras de lo que cambió frente a los datos del análisis. Vacía si no cambió nada."""
        def ids(sql):
            return [f[0] for f in self.db.execute(sql)]
        agregados = ids("SELECT cliente FROM clientes WHERE cliente NOT IN (SELECT cliente FROM clientes_originales)")
        eliminados = ids("SELECT cliente FROM clientes_originales WHERE cliente NOT IN (SELECT cliente FROM clientes)")
        datos = [c for c in COLUMNAS if c not in ("cliente", "grupo")]
        distinto = " OR ".join(f"a.{c} IS NOT o.{c}" for c in datos)
        editados = ids(f"SELECT a.cliente FROM clientes a JOIN clientes_originales o USING (cliente) WHERE {distinto}")
        regrupados = self.db.execute("SELECT COUNT(*) FROM clientes a JOIN clientes_originales o USING (cliente) "
                                     "WHERE a.grupo <> o.grupo").fetchone()[0]

        def lista(codigos):
            return ", ".join(codigos[:8]) + (f" y {len(codigos) - 8} más" if len(codigos) > 8 else "")
        cambios = []
        if agregados:
            cambios.append(f"Clientes agregados ({len(agregados)}): {lista(agregados)}.")
        if eliminados:
            cambios.append(f"Clientes eliminados ({len(eliminados)}): {lista(eliminados)}.")
        if editados:
            cambios.append(f"Clientes con datos editados ({len(editados)}): {lista(editados)}.")
        if regrupados:
            cambios.append(f"Clientes que cambiaron de grupo frente al análisis: {numero(regrupados)}.")
        original = km.Modelo.desde_dict(json.loads(self._config("modelo_original")))
        if self.modelo.k != original.k or self.modelo.origen != original.origen:
            cambios.append(f"Modelo: el análisis usó k = {original.k}; el vigente tiene k = {self.modelo.k} "
                           f"({self.modelo.origen.lower()}).")
        return cambios

    # ---------- escritura ----------

    def agregar(self, datos):
        """Valida y guarda un cliente nuevo; el grupo lo asigna el modelo vigente. Devuelve el cliente guardado."""
        fila = validar_cliente(datos, self.paises())
        existente = self.cliente(fila["cliente"])
        if existente:
            raise ErrorValidacion(f"Ya existe el cliente {existente['cliente']} ({existente['pais']}). "
                                  "Selecciónelo en la tabla para editarlo.")
        fila["grupo"] = int(self.modelo.asignar([fila])[0])
        with self.db:
            self.db.execute(self._insertar("clientes"), self._tupla(fila))
            self._registrar("Agregar", f"{fila['cliente']} ({fila['pais']}): {self.modelo.etiqueta(fila['grupo'])}",
                            {"borrar": [fila["cliente"]]})
        return fila

    def actualizar(self, codigo, datos):
        """Guarda los cambios de un cliente. El código no cambia; el grupo se vuelve a asignar."""
        actual = self._buscar(codigo)
        fila = validar_cliente({**datos, "cliente": actual["cliente"]}, self.paises())
        fila["grupo"] = int(self.modelo.asignar([fila])[0])
        cambios = [f"{c}: {actual[c]} → {fila[c]}" for c in COLUMNAS if c != "cliente" and fila[c] != actual[c]]
        if not cambios:
            return actual
        with self.db:
            self.db.execute(f"UPDATE clientes SET {', '.join(f'{c} = ?' for c in COLUMNAS[1:])} WHERE cliente = ?",
                            self._tupla(fila)[1:] + (actual["cliente"],))
            self._registrar("Editar", f"{actual['cliente']}: " + "; ".join(cambios), {"poner": [actual]})
        return fila

    def eliminar(self, codigo):
        actual = self._buscar(codigo)
        with self.db:
            self.db.execute("DELETE FROM clientes WHERE cliente = ?", (actual["cliente"],))
            self._registrar("Eliminar", f"{actual['cliente']} ({actual['pais']})", {"poner": [actual]})

    def recalcular(self, k):
        """Entrena K-means de nuevo con todos los clientes actuales y reasigna los grupos."""
        filas = self.clientes()
        nuevo, grupos = km.entrenar(filas, k)
        previo = {"grupos": [[f["cliente"], f["grupo"]] for f in filas], "modelo": self.modelo.a_dict()}
        tamanos = ", ".join(numero(int((grupos == g).sum())) for g in range(1, nuevo.k + 1))
        with self.db:
            self.db.executemany("UPDATE clientes SET grupo = ? WHERE cliente = ?",
                                [(int(g), f["cliente"]) for f, g in zip(filas, grupos)])
            self._poner_modelo(nuevo)
            self._registrar("Recalcular grupos", f"k = {nuevo.k}; silueta {numero(nuevo.silueta, 3)}; "
                            f"Davies-Bouldin {numero(nuevo.davies_bouldin, 3)}; tamaños {tamanos}", previo)
        return nuevo

    def restaurar_originales(self):
        """Vuelve a los clientes y al modelo del análisis. Se puede deshacer."""
        previo = self._foto()
        with self.db:
            self.db.execute("DELETE FROM clientes")
            self.db.execute("INSERT INTO clientes SELECT * FROM clientes_originales")
            self._poner_modelo(km.Modelo.desde_dict(json.loads(self._config("modelo_original"))))
            self._registrar("Restaurar", "Clientes y grupos del análisis original", previo)

    def importar_csv(self, ruta):
        """Reemplaza los clientes con los de un CSV. Los grupos los asigna el modelo vigente."""
        filas = leer_csv(ruta)
        for f, g in zip(filas, self.modelo.asignar(filas)):
            f["grupo"] = int(g)
        previo = self._foto()
        with self.db:
            self._poner_clientes(filas)
            self._registrar("Importar CSV", f"{Path(ruta).name}: {numero(len(filas))} clientes", previo)
        return len(filas)

    def exportar_csv(self, ruta):
        """Escribe los clientes con su grupo. Punto y coma, coma decimal y BOM, para que Excel lo abra bien."""
        modelo = self.modelo
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            w = csv.writer(archivo, delimiter=";")
            w.writerow(COLUMNAS + ("nombre_grupo",))
            for f in self.clientes():
                fila = [f"{f[c]:.2f}".replace(".", ",") if isinstance(f[c], float) else f[c] for c in COLUMNAS]
                w.writerow(fila + [modelo.nombre(f["grupo"])])
        return ruta

    def deshacer(self):
        """Vuelve al estado anterior al último cambio. Devuelve qué se deshizo, o None."""
        fila = self.db.execute(
            "SELECT id, accion, detalle, reversa FROM bitacora "
            "WHERE deshecho = 0 AND accion NOT IN ('Carga inicial', 'Deshacer') ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not fila:
            return None
        reversa = json.loads(fila["reversa"])
        with self.db:
            self._aplicar_reversa(reversa)
            self.db.execute("UPDATE bitacora SET deshecho = 1 WHERE id = ?", (fila["id"],))
            self._registrar("Deshacer", f"{fila['accion']}: {fila['detalle']}", {})
        return f"{fila['accion']}: {fila['detalle']}"

    def cerrar(self):
        self.db.close()

    # ---------- internos ----------

    def _buscar(self, codigo):
        fila = self.cliente(validar_codigo(codigo))
        if not fila:
            raise ErrorValidacion("Ese cliente ya no existe; seleccione otro en la tabla.")
        return fila

    def _foto(self):
        """Copia completa de clientes y modelo, para deshacer cambios que tocan todo."""
        return {"todo": True, "poner": self.clientes(), "modelo": self.modelo.a_dict()}

    def _aplicar_reversa(self, r):
        """Aplica lo guardado en la bitácora para volver atrás. Se llama dentro de una transacción."""
        if r.get("todo"):
            self.db.execute("DELETE FROM clientes")
        for codigo in r.get("borrar", []):
            self.db.execute("DELETE FROM clientes WHERE cliente = ?", (codigo,))
        if r.get("poner"):
            self.db.executemany(self._insertar("clientes", reemplazar=True), [self._tupla(f) for f in r["poner"]])
        if r.get("grupos"):
            self.db.executemany("UPDATE clientes SET grupo = ? WHERE cliente = ?",
                                [(g, codigo) for codigo, g in r["grupos"]])
        if r.get("modelo"):
            self._poner_modelo(km.Modelo.desde_dict(r["modelo"]))

    def _poner_clientes(self, filas):
        self.db.execute("DELETE FROM clientes")
        self.db.executemany(self._insertar("clientes"), [self._tupla(f) for f in filas])

    def _poner_modelo(self, modelo):
        self._poner_config("modelo", json.dumps(modelo.a_dict(), ensure_ascii=False))
        self._modelo = modelo

    @staticmethod
    def _insertar(tabla, reemplazar=False):
        verbo = "INSERT OR REPLACE" if reemplazar else "INSERT"
        return f"{verbo} INTO {tabla} ({', '.join(COLUMNAS)}) VALUES ({', '.join('?' * len(COLUMNAS))})"

    @staticmethod
    def _tupla(fila):
        return tuple(fila[c] for c in COLUMNAS)

    def _config(self, clave):
        fila = self.db.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
        return fila["valor"] if fila else None

    def _poner_config(self, clave, valor):
        self.db.execute("INSERT INTO configuracion VALUES (?, ?) "
                        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, str(valor)))

    def _registrar(self, accion, detalle, reversa):
        self.db.execute("INSERT INTO bitacora (fecha, accion, detalle, reversa) VALUES (?, ?, ?, ?)",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), accion, detalle,
                         json.dumps(reversa, ensure_ascii=False)))
