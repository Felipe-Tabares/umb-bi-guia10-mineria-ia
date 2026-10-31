"""Pruebas unitarias de las reglas de validación (python -m unittest discover -s pruebas)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from segmentador.validacion import (ErrorValidacion, estado_de, leer_decimal, mercado_de,  # noqa: E402
                                    validar_cliente, validar_codigo, validar_entero, validar_pais,
                                    validar_valor)

BASE = {"cliente": "70001", "pais": "Spain", "recencia_dias": "30", "frecuencia": "4", "valor_total": "1000"}


class Codigo(unittest.TestCase):
    def test_se_limpia(self):
        self.assertEqual(validar_codigo("  12346 "), "12346")
        self.assertEqual(validar_codigo("NUEVO-1"), "NUEVO-1")

    def test_invalidos(self):
        for malo in ("", "   ", "12 34", "12#4", "x" * 21, None):
            with self.subTest(malo=malo), self.assertRaises(ErrorValidacion):
                validar_codigo(malo)


class Pais(unittest.TestCase):
    def test_usa_la_forma_guardada(self):
        self.assertEqual(validar_pais("  united   kingdom ", ["Germany", "United Kingdom"]), "United Kingdom")
        self.assertEqual(validar_pais("Colombia", ["Germany"]), "Colombia")

    def test_invalidos(self):
        for malo in ("", "123", "x" * 41):
            with self.subTest(malo=malo), self.assertRaises(ErrorValidacion):
                validar_pais(malo)


class Numeros(unittest.TestCase):
    def test_entero(self):
        self.assertEqual(validar_entero(" 12 ", "La recencia", 0), 12)
        self.assertEqual(validar_entero("", "Las unidades", 0, opcional=True), 0)
        self.assertEqual(validar_entero(7, "La frecuencia", 1), 7)

    def test_entero_rechazos_con_motivo(self):
        casos = {"": "Falta", "-3": "mayor o igual a 0", "2,5": "sin decimales", "dos": "número entero",
                 "4000": "no puede pasar"}
        for texto, motivo in casos.items():
            with self.subTest(texto=texto), self.assertRaisesRegex(ErrorValidacion, motivo):
                validar_entero(texto, "La recencia", 0, 3650)
        with self.assertRaises(ErrorValidacion):
            validar_entero(True, "La frecuencia", 1)

    def test_decimal_con_coma_o_punto(self):
        casos = {"1250,5": 1250.5, "1250.5": 1250.5, "1.250,50": 1250.5, "1,250.50": 1250.5,
                 "£ 99": 99.0, "1.234.567": 1234567.0, "abc": None, "1,2,3x": None, "": None}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(leer_decimal(texto), esperado)

    def test_valor_total(self):
        self.assertEqual(validar_valor("1.250,555"), 1250.56)
        for malo in ("0", "-5", "0,00", "mil", ""):
            with self.subTest(malo=malo), self.assertRaises(ErrorValidacion):
                validar_valor(malo)


class Cliente(unittest.TestCase):
    def test_calcula_lo_que_no_se_digita(self):
        c = validar_cliente({**BASE, "valor_total": "1001,00", "unidades": "", "productos_distintos": ""})
        self.assertEqual(c["mercado"], "Internacional")
        self.assertEqual(c["estado"], "Activo")
        self.assertEqual(c["ticket_promedio"], 250.25)
        self.assertEqual((c["unidades"], c["productos_distintos"], c["devoluciones"]), (0, 0, 0))

    def test_limite_de_activo_es_90_dias(self):
        self.assertEqual(estado_de(90), "Activo")
        self.assertEqual(estado_de(91), "Inactivo")

    def test_mercado(self):
        self.assertEqual(mercado_de("United Kingdom"), "Reino Unido")
        self.assertEqual(mercado_de("reino unido"), "Reino Unido")
        self.assertEqual(mercado_de("France"), "Internacional")

    def test_productos_no_pasan_de_unidades(self):
        with self.assertRaisesRegex(ErrorValidacion, "no pueden ser más"):
            validar_cliente({**BASE, "unidades": "5", "productos_distintos": "6"})

    def test_frecuencia_minima_uno(self):
        with self.assertRaisesRegex(ErrorValidacion, "mayor o igual a 1"):
            validar_cliente({**BASE, "frecuencia": "0"})


if __name__ == "__main__":
    unittest.main()
