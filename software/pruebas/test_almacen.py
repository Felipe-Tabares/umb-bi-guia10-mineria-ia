"""Pruebas unitarias de la base SQLite: carga, persistencia, deshacer y CSV.

Usan fixture_clientes.csv, un archivo sintético de 120 clientes en cuatro grupos
bien separados que existe solo para estas pruebas.
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from segmentador.datos import Almacen, ErrorValidacion  # noqa: E402
from segmentador.modelo import NOMBRES_K4  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture_clientes.csv"
NUEVO = {"cliente": "N1", "pais": "germany", "recencia_dias": "8", "frecuencia": "20", "valor_total": "6000,00"}


class AlmacenPrueba(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = Almacen(Path(self.tmp.name) / "t.db", inicial=FIXTURE)

    def tearDown(self):
        self.a.cerrar()
        self.tmp.cleanup()

    def test_carga_inicial_respeta_los_grupos_del_archivo(self):
        with open(FIXTURE, encoding="utf-8") as f:
            esperado = {fila["cliente"]: int(fila["grupo"]) for fila in csv.DictReader(f)}
        self.assertEqual({c["cliente"]: c["grupo"] for c in self.a.clientes()}, esperado)
        self.assertEqual(self.a.modelo.nombres, NOMBRES_K4)
        self.assertIn("reproduce", self.a.bitacora()[0]["detalle"])

    def test_agregar_asigna_el_grupo_de_alto_valor(self):
        fila = self.a.agregar(NUEVO)
        self.assertEqual((fila["pais"], fila["grupo"], fila["estado"]), ("Germany", 1, "Activo"))
        with self.assertRaisesRegex(ErrorValidacion, "Ya existe"):
            self.a.agregar(NUEVO)

    def test_persistencia_en_disco(self):
        self.a.agregar(NUEVO)
        self.a.recalcular(3)
        self.a.cerrar()
        self.a = Almacen(self.a.ruta)
        self.assertIsNotNone(self.a.cliente("N1"))
        self.assertEqual(self.a.modelo.k, 3)
        self.assertEqual(len(self.a.clientes()), 121)

    def test_editar_reasigna_grupo_y_deshacer(self):
        original = self.a.cliente("P001")
        self.a.actualizar("P001", {**original, "recencia_dias": "300", "frecuencia": "1", "valor_total": "50"})
        self.assertEqual(self.a.cliente("P001")["grupo"], 4)
        self.a.deshacer()
        self.assertEqual(self.a.cliente("P001"), original)

    def test_eliminar_agregar_y_deshacer_en_orden(self):
        self.a.agregar(NUEVO)
        self.a.eliminar("P002")
        self.assertIn("Eliminar", self.a.deshacer())
        self.assertIsNotNone(self.a.cliente("P002"))
        self.assertIn("Agregar", self.a.deshacer())
        self.assertIsNone(self.a.cliente("N1"))
        self.assertIsNone(self.a.deshacer())

    def test_restaurar_vuelve_al_analisis(self):
        self.a.agregar(NUEVO)
        self.a.recalcular(5)
        self.assertTrue(self.a.diferencias_con_originales())
        self.a.restaurar_originales()
        self.assertEqual(self.a.diferencias_con_originales(), [])
        self.assertEqual(self.a.modelo.k, 4)

    def test_filtros(self):
        self.assertEqual(len(self.a.clientes(grupo=4)), 30)
        self.assertTrue(all(c["estado"] == "Inactivo" for c in self.a.clientes(grupo=4)))
        self.assertTrue(all("germany" in c["pais"].lower() for c in self.a.clientes(texto="GERMÁNY")))
        self.assertEqual([c["cliente"] for c in self.a.clientes(texto="p010")], ["P010"])

    def test_csv_ida_y_vuelta(self):
        ruta = Path(self.tmp.name) / "salida.csv"
        self.a.exportar_csv(ruta)
        texto = ruta.read_text(encoding="utf-8-sig")
        self.assertTrue(texto.startswith("cliente;pais;mercado"))
        antes = self.a.clientes()
        self.a.agregar(NUEVO)
        self.assertEqual(self.a.importar_csv(ruta), 120)
        self.assertEqual(self.a.clientes(), antes)

    def test_csv_con_errores_no_cambia_nada(self):
        ruta = Path(self.tmp.name) / "malo.csv"
        ruta.write_text("cliente,pais,recencia_dias,frecuencia,valor_total\nX1,Spain,4,0,10\n", encoding="utf-8")
        with self.assertRaisesRegex(ErrorValidacion, "Línea 2"):
            self.a.importar_csv(ruta)
        ruta.write_text("cliente;pais\nX1;Spain\n", encoding="utf-8")
        with self.assertRaisesRegex(ErrorValidacion, "faltan columnas"):
            self.a.importar_csv(ruta)
        self.assertEqual(len(self.a.clientes()), 120)


class CargaInicialSinCoincidencia(unittest.TestCase):
    """Si K-means no reproduce los grupos del archivo, se respetan los del archivo."""

    def test_respeta_grupos_del_archivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(FIXTURE, encoding="utf-8") as f:
                filas = list(csv.DictReader(f))
            filas[0]["grupo"], filas[0]["nombre_grupo"] = "4", "Dormidos"  # un cliente movido a mano
            ruta = Path(tmp) / "movido.csv"
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(filas[0]))
                w.writeheader()
                w.writerows(filas)
            a = Almacen(Path(tmp) / "t.db", inicial=ruta)
            self.assertEqual(a.cliente(filas[0]["cliente"])["grupo"], 4)
            self.assertIn("se respetan", a.bitacora()[0]["detalle"])
            self.assertEqual(a.modelo.nombres[1], "Frecuentes de alto valor")
            a.cerrar()

    def test_sin_columna_grupo_entrena_con_k_4(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "sin_grupo.csv"
            lineas = FIXTURE.read_text(encoding="utf-8").splitlines()
            ruta.write_text("\n".join(linea.rsplit(",", 2)[0] for linea in lineas), encoding="utf-8")  # sin grupo
            a = Almacen(Path(tmp) / "t.db", inicial=ruta)
            self.assertEqual(a.modelo.k, 4)
            self.assertEqual(sorted({c["grupo"] for c in a.clientes()}), [1, 2, 3, 4])
            a.cerrar()


if __name__ == "__main__":
    unittest.main()
