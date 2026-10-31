"""Autoprueba: comprueba el programa ya empaquetado en el equipo donde se va a usar.

Se corre con `SegmentadorClientes --autoprueba <carpeta>`. Trabaja sobre una base
temporal con los datos que trae el programa (no toca los datos del usuario), deja
las gráficas y un reporte en la carpeta y devuelve código 0 si todo pasó. Así se
prueba en Windows, macOS y Linux sin abrir la ventana a mano.
"""
import csv
import platform
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from . import NOMBRE, VERSION, graficas
from .formato import numero
from .datos import DATOS_INICIALES, Almacen, ErrorValidacion
from .modelo import NOMBRES_K4

CLIENTE_VALIDO = {"cliente": "90001", "pais": "germany", "recencia_dias": "12", "frecuencia": "15",
                  "valor_total": "8.450,75", "unidades": "3200", "productos_distintos": "140", "devoluciones": "1"}


def ejecutar(carpeta):
    salida = Path(carpeta)
    salida.mkdir(parents=True, exist_ok=True)
    resultados = []

    def caso(nombre, funcion):
        inicio = time.perf_counter()
        try:
            detalle = funcion()
            resultados.append((True, nombre, detalle or "", time.perf_counter() - inicio))
        except Exception as e:  # la autoprueba reporta cualquier falla, no solo las esperadas
            resultados.append((False, nombre, f"{type(e).__name__}: {e}", time.perf_counter() - inicio))

    def rechaza(funcion, texto):
        try:
            funcion()
        except ErrorValidacion as e:
            assert texto.lower() in str(e).lower(), f"rechazó con otro motivo: {e}"
            return f"«{e}»"
        raise AssertionError("debía rechazar el dato y lo aceptó")

    def con(**cambios):
        return {**CLIENTE_VALIDO, **cambios}

    with tempfile.TemporaryDirectory() as tmp:
        with open(DATOS_INICIALES, encoding="utf-8-sig") as f:
            original = {fila["cliente"]: fila for fila in csv.DictReader(f)}
        a = Almacen(Path(tmp) / "prueba.db")

        def carga_inicial():
            clientes = a.clientes()
            assert len(clientes) == len(original) > 0, f"{len(clientes)} clientes, el archivo trae {len(original)}"
            assert all(c["grupo"] == int(original[c["cliente"]]["grupo"]) for c in clientes), "grupos distintos"
            return f"{numero(len(clientes))} clientes; {a.bitacora()[0]['detalle'].split('; ')[1]}"
        caso("Carga los clientes del análisis con sus grupos", carga_inicial)

        def calculados():
            for c in a.clientes():
                assert c["estado"] == ("Activo" if c["recencia_dias"] <= 90 else "Inactivo"), c
                assert c["mercado"] == ("Reino Unido" if c["pais"] == "United Kingdom" else "Internacional"), c
                assert abs(c["ticket_promedio"] - c["valor_total"] / c["frecuencia"]) < 0.01, c
        caso("Estado, mercado y ticket promedio calculados bien en todos", calculados)

        def modelo_inicial():
            m = a.modelo
            assert m.k == 4 and m.nombres == NOMBRES_K4, m.nombres
            assert m.silueta > 0, m.silueta
            return f"k = 4, silueta {numero(m.silueta, 3)}, Davies-Bouldin {numero(m.davies_bouldin, 3)}"
        caso("Modelo inicial con k = 4 y los nombres del análisis", modelo_inicial)

        def reproduce_analisis():
            m = a.recalcular(4)
            distintos = [c["cliente"] for c in a.clientes() if c["grupo"] != int(original[c["cliente"]]["grupo"])]
            assert not distintos, f"{len(distintos)} clientes cambiaron de grupo frente al análisis"
            tamanos = [len(a.clientes(grupo=g)) for g in range(1, 5)]
            a.deshacer()
            return (f"silueta {numero(m.silueta, 3)}, Davies-Bouldin {numero(m.davies_bouldin, 3)}, "
                    f"tamaños {tamanos}, todos los clientes en el mismo grupo del análisis")
        caso("Recalcular con k = 4 reproduce exactamente los grupos del análisis", reproduce_analisis)

        def agregar():
            f = a.agregar(CLIENTE_VALIDO)
            assert f["pais"] == "Germany", "debía usar el país ya guardado"
            assert (f["valor_total"], f["estado"], f["mercado"]) == (8450.75, "Activo", "Internacional"), f
            z = a.modelo.estandarizar([f])[0]
            cercano = int(np.argmin(((a.modelo.centroides - z) ** 2).sum(axis=1))) + 1
            assert f["grupo"] == cercano, "no quedó en el centroide más cercano"
            return f"cliente 90001 en {a.modelo.etiqueta(f['grupo'])}"
        caso("Agrega un cliente válido y le asigna grupo", agregar)

        caso("Rechaza cliente repetido", lambda: rechaza(lambda: a.agregar(con(cliente="12347")), "ya existe"))
        caso("Rechaza código vacío", lambda: rechaza(lambda: a.agregar(con(cliente="  ")), "código"))
        caso("Rechaza código con símbolos", lambda: rechaza(lambda: a.agregar(con(cliente="12#4")), "letras"))
        caso("Rechaza país vacío", lambda: rechaza(lambda: a.agregar(con(cliente="90002", pais="")), "país"))
        caso("Rechaza recencia negativa",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", recencia_dias="-3")), "mayor o igual a 0"))
        caso("Rechaza frecuencia 0",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", frecuencia="0")), "mayor o igual a 1"))
        caso("Rechaza frecuencia con decimales",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", frecuencia="2,5")), "sin decimales"))
        caso("Rechaza valor total 0",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", valor_total="0")), "mayor que 0"))
        caso("Rechaza valor total con texto",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", valor_total="mil")), "debe ser un número"))
        caso("Rechaza más productos que unidades",
             lambda: rechaza(lambda: a.agregar(con(cliente="90002", unidades="3", productos_distintos="9")),
                             "no pueden ser más"))

        def editar():
            a.actualizar("90001", con(recencia_dias="300", frecuencia="1", valor_total="45"))
            f = a.cliente("90001")
            assert (f["estado"], f["grupo"]) == ("Inactivo", 4), f
            return "quedó inactivo y pasó a 4. Dormidos"
        caso("Edita un cliente y le reasigna el grupo", editar)

        def eliminar_y_deshacer():
            a.eliminar("90001")
            assert a.cliente("90001") is None
            assert "Eliminar" in a.deshacer()
            assert a.cliente("90001")["grupo"] == 4
        caso("Elimina y deshacer lo recupera", eliminar_y_deshacer)

        def recalcular_k4():
            antes = {c["cliente"]: c["grupo"] for c in a.clientes()}
            m = a.recalcular(4)
            despues = {c["cliente"]: c["grupo"] for c in a.clientes()}
            assert m.silueta > 0, m.silueta
            medias = [np.mean([c["valor_total"] for c in a.clientes(grupo=g)]) for g in range(1, 5)]
            assert medias == sorted(medias, reverse=True), "los grupos no quedaron ordenados por valor medio"
            iguales = sum(antes[c] == despues[c] for c in antes)
            tamanos = [len(a.clientes(grupo=g)) for g in range(1, 5)]
            return (f"con {numero(len(antes))} clientes: silueta {numero(m.silueta, 3)}, tamaños {tamanos}, "
                    f"{numero(iguales)} siguen en su grupo")
        caso("Recalcula con los datos ya editados: silueta > 0 y grupos ordenados por valor", recalcular_k4)

        def otros_k():
            for k in (2, 8):
                m = a.recalcular(k)
                assert m.k == k and m.silueta > 0 and len({c["grupo"] for c in a.clientes()}) == k
            rechaza(lambda: a.recalcular(1), "entre 2 y 8")
            rechaza(lambda: a.recalcular("nueve"), "entero")
            return "k = 2 y k = 8 funcionan; k = 1 y texto se rechazan"
        caso("Recalcula con k = 2 y k = 8 y rechaza k fuera de rango", otros_k)

        def deshacer_recalculo():
            a.deshacer()
            a.deshacer()
            assert a.modelo.k == 4 and a.modelo.nombres == NOMBRES_K4
        caso("Deshacer devuelve el modelo y los grupos anteriores", deshacer_recalculo)

        def trazabilidad():
            assert a.diferencias_con_originales(), "debía reportar diferencias"
            a.restaurar_originales()
            assert a.diferencias_con_originales() == [], a.diferencias_con_originales()
            acciones = [f["accion"] for f in reversed(a.bitacora())]
            for esperada in ("Carga inicial", "Agregar", "Editar", "Eliminar", "Recalcular grupos", "Deshacer",
                             "Restaurar"):
                assert esperada in acciones, f"falta {esperada} en la bitácora"
            return f"{len(acciones)} registros en la bitácora"
        caso("Bitácora y restauración llevan a los datos originales", trazabilidad)

        def csv_ida_y_vuelta():
            ruta = salida / "clientes-exportados.csv"
            a.exportar_csv(ruta)
            antes = a.clientes()
            a.agregar(con(cliente="TEMPORAL"))
            assert a.importar_csv(ruta) == len(antes)
            despues = a.clientes()

            def sin_grupo(filas):
                return [{c: v for c, v in f.items() if c != "grupo"} for f in filas]
            assert sin_grupo(despues) == sin_grupo(antes), "el CSV exportado no devolvió los mismos datos"
            # Al importar, el grupo lo vuelve a asignar el modelo vigente; debe coincidir con el que tenían.
            iguales = sum(x["grupo"] == y["grupo"] for x, y in zip(antes, despues))
            assert iguales >= 0.99 * len(antes), f"solo {iguales} de {len(antes)} conservaron el grupo"
            return f"{numero(len(antes))} clientes; {numero(iguales)} conservan el grupo al reasignarlo con el modelo"
        caso("Exporta e importa CSV (punto y coma, coma decimal) sin perder datos", csv_ida_y_vuelta)

        def csv_con_coma():
            ruta = Path(tmp) / "coma.csv"
            ruta.write_text("cliente,pais,recencia_dias,frecuencia,valor_total\nA1,Spain,10,3,1500.50\n"
                            "A2,France,200,1,80\n", encoding="utf-8")
            assert a.importar_csv(ruta) == 2
            assert a.cliente("A1")["valor_total"] == 1500.5
            a.deshacer()
        caso("Importa CSV separado por coma", csv_con_coma)

        def csv_malo():
            malo = Path(tmp) / "malo.csv"
            malo.write_text("cliente;pais;recencia_dias;frecuencia;valor_total\nB1;Spain;5;2;100\nB1;Spain;5;2;100\n"
                            "B2;;5;0;x\n", encoding="utf-8")
            antes = a.cantidad()
            mensaje = rechaza(lambda: a.importar_csv(malo), "no se importó")
            assert a.cantidad() == antes, "un CSV con errores no debe cambiar nada"
            return mensaje.replace("\n", " | ")
        caso("Un CSV con errores no cambia nada", csv_malo)

        for tipo, (nombre, _) in graficas.TIPOS.items():
            def grafica(tipo=tipo):
                ruta = salida / f"grafica-{tipo}.png"
                graficas.exportar(ruta, tipo, a.clientes(), a.modelo)
                assert ruta.stat().st_size > 20000, "la imagen quedó casi vacía"
            caso(f"Genera la gráfica «{nombre}» en PNG", grafica)

        def pdf():
            ruta = graficas.exportar(salida / "grafica-dispersion.pdf", "dispersion", a.clientes(), a.modelo)
            assert Path(ruta).read_bytes()[:4] == b"%PDF", "el archivo no es un PDF"
        caso("Exporta una gráfica en PDF", pdf)

        def vacia():
            graficas.exportar(salida / "grafica-vacia.png", "grupos", [], a.modelo)
        caso("Gráfica sin datos no falla", vacia)

        def persistencia():
            a.agregar(con(cliente="PERSISTE"))
            a.cerrar()
            otra = Almacen(a.ruta)
            try:
                assert otra.cliente("PERSISTE") is not None, "el cliente no quedó guardado en disco"
            finally:
                otra.cerrar()
        caso("Los datos quedan guardados al cerrar y volver a abrir", persistencia)
        caso("Ventana", lambda: _prueba_ventana(Path(tmp) / "ventana.db"))

    lineas = [f"{NOMBRE} {VERSION} · autoprueba",
              f"Sistema: {platform.system()} {platform.release()} · Python {platform.python_version()}"
              f" · {'ejecutable empaquetado' if getattr(sys, 'frozen', False) else 'código fuente'}", ""]
    for ok, nombre, detalle, segundos in resultados:
        linea = f"{'OK  ' if ok else 'FALLA'} {nombre}" + (f"  -> {detalle}" if detalle else "")
        lineas.append(linea + (f"  ({numero(segundos, 1)} s)" if segundos >= 0.5 else ""))
    aprobadas = sum(ok for ok, _, _, _ in resultados)
    lineas += ["", f"{aprobadas} de {len(resultados)} pruebas aprobadas."]
    (salida / "reporte.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    return aprobadas == len(resultados)


def _prueba_ventana(ruta_db):
    """Abre la ventana real, usa el formulario y el panel de K-means y cambia de gráfica.
    Si no hay pantalla, lo dice."""
    import tkinter as tk
    from .interfaz import Aplicacion
    try:
        raiz = tk.Tk()
    except tk.TclError as e:
        raise RuntimeError(f"sin pantalla disponible ({e})")
    almacen = Almacen(ruta_db)
    try:
        app = Aplicacion(raiz, almacen)
        raiz.update()
        total = len(app.arbol.get_children())
        for campo, valor in CLIENTE_VALIDO.items():
            app.campos[campo].set(valor)
        app.guardar()
        assert len(app.arbol.get_children()) == total + 1, "la tabla no mostró el cliente nuevo"
        app.campos["cliente"].set("90002")
        app.campos["pais"].set("Spain")
        app.campos["recencia_dias"].set("10")
        app.campos["frecuencia"].set("2")
        app.campos["valor_total"].set("abc")
        app.guardar()
        assert "debe ser un número" in app.aviso.cget("text"), "la ventana no mostró el error de validación"
        app.limpiar_formulario()
        app.buscar.set("90001")
        app.llenar_tabla()
        assert app.arbol.get_children() == ("90001",), "la búsqueda no encontró el cliente"
        app.k.set("3")
        app.recalcular()
        assert almacen.modelo.k == 3 and len(app.perfil.get_children()) == 3, "el panel K-means no se actualizó"
        for tipo in graficas.TIPOS:
            app.poner_tipo(tipo)
            raiz.update()
        app.ver_bitacora().destroy()
        return f"formulario, búsqueda, K-means con k = 3 y {len(graficas.TIPOS)} gráficas en pantalla"
    finally:
        almacen.cerrar()
        raiz.destroy()
