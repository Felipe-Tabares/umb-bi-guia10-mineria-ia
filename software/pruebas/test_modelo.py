"""Pruebas unitarias del modelo K-means y de las gráficas."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from segmentador import formato, graficas, modelo  # noqa: E402
from segmentador.validacion import ErrorValidacion  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixture_clientes.csv"


def cargar():
    with open(FIXTURE, encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    for f in filas:
        for c in ("recencia_dias", "frecuencia", "grupo"):
            f[c] = int(f[c])
        f["valor_total"] = float(f["valor_total"])
    return filas


class Entrenamiento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filas = cargar()
        cls.m, cls.grupos = modelo.entrenar(cls.filas, 4)

    def test_grupos_numerados_por_valor_medio(self):
        valor = np.array([f["valor_total"] for f in self.filas])
        medias = [valor[self.grupos == g].mean() for g in range(1, 5)]
        self.assertEqual(medias, sorted(medias, reverse=True))

    def test_reproduce_los_grupos_del_archivo_y_es_determinista(self):
        self.assertEqual(list(self.grupos), [f["grupo"] for f in self.filas])
        _, otra_vez = modelo.entrenar(self.filas, 4)
        self.assertEqual(list(otra_vez), list(self.grupos))

    def test_metricas(self):
        self.assertGreater(self.m.silueta, 0.5)   # cuatro grupos sintéticos bien separados
        self.assertGreater(self.m.davies_bouldin, 0)

    def test_nombres_con_k_4_cuando_el_perfil_coincide(self):
        self.assertEqual(self.m.nombres, modelo.NOMBRES_K4)

    def test_nombres_genericos_con_otro_k(self):
        m5, _ = modelo.entrenar(self.filas, 5)
        self.assertEqual(m5.nombres, {g: f"Grupo {g}" for g in range(1, 6)})
        self.assertEqual(m5.etiqueta(5), "Grupo 5")

    def test_nombres_genericos_si_el_perfil_no_coincide(self):
        invertidos = np.where(self.grupos == 3, 4, np.where(self.grupos == 4, 3, self.grupos))
        self.assertEqual(modelo.nombrar(self.filas, invertidos, 4)[3], "Grupo 3")

    def test_asigna_al_centroide_mas_cercano(self):
        self.assertEqual(list(self.m.asignar(self.filas)), list(self.grupos))
        z = self.m.estandarizar(self.filas[:5])
        d = ((z[:, None, :] - self.m.centroides[None]) ** 2).sum(axis=2)
        self.assertEqual(list(d.argmin(axis=1) + 1), list(self.m.asignar(self.filas[:5])))

    def test_guardar_y_leer_modelo(self):
        copia = modelo.Modelo.desde_dict(self.m.a_dict())
        self.assertEqual(list(copia.asignar(self.filas)), list(self.grupos))
        self.assertEqual(copia.nombres, self.m.nombres)

    def test_desde_grupos_promedia_cada_grupo(self):
        m = modelo.desde_grupos(self.filas, self.grupos)
        z = m.estandarizar(self.filas)
        np.testing.assert_allclose(m.centroides[0], z[self.grupos == 1].mean(axis=0))
        self.assertAlmostEqual(m.silueta, self.m.silueta, places=3)

    def test_perfil(self):
        p = modelo.perfil(self.filas, self.grupos, self.m)
        self.assertEqual(sum(f["clientes"] for f in p), len(self.filas))
        self.assertAlmostEqual(sum(f["pct_valor"] for f in p), 100)
        self.assertGreater(p[3]["recencia_mediana"], 90)


class ValidarK(unittest.TestCase):
    def test_rango(self):
        self.assertEqual(modelo.validar_k(" 6 "), 6)
        for malo in ("1", "9", "x", ""):
            with self.subTest(malo=malo), self.assertRaises(ErrorValidacion):
                modelo.validar_k(malo)

    def test_pocos_clientes(self):
        with self.assertRaisesRegex(ErrorValidacion, "al menos"):
            modelo.entrenar(cargar()[:3], 4)


class Graficas(unittest.TestCase):
    def test_todas_las_graficas_se_exportan(self):
        filas = cargar()
        m, _ = modelo.entrenar(filas, 4)
        with tempfile.TemporaryDirectory() as tmp:
            for tipo in graficas.TIPOS:
                for ext in ("png", "pdf"):
                    ruta = Path(tmp) / f"{tipo}.{ext}"
                    graficas.exportar(ruta, tipo, filas, m)
                    self.assertGreater(ruta.stat().st_size, 1000, f"{tipo}.{ext} quedó vacío")

    def test_numero_en_formato_colombiano(self):
        self.assertEqual(formato.numero(1234567.891, 2), "1.234.567,89")
        self.assertEqual(formato.libras(8450), "£ 8.450")


if __name__ == "__main__":
    unittest.main()
