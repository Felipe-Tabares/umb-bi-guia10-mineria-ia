"""Segmentador de Clientes · punto de entrada.

Uso:
    SegmentadorClientes                       abre la ventana
    SegmentadorClientes --autoprueba carpeta  prueba todo sin intervención y deja un reporte
    SegmentadorClientes --datos archivo.db    usa otra base de datos
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="SegmentadorClientes",
                                     description="Ingreso de clientes, grupos con K-means y gráficas automáticas.")
    parser.add_argument("--autoprueba", metavar="CARPETA", help="corre la autoprueba y deja el reporte en CARPETA")
    parser.add_argument("--datos", metavar="ARCHIVO", help="ruta de la base SQLite (por defecto, al lado del programa)")
    args = parser.parse_args()

    if args.autoprueba:
        from segmentador.autoprueba import ejecutar
        sys.exit(0 if ejecutar(args.autoprueba) else 1)

    from segmentador.interfaz import abrir
    abrir(args.datos)


if __name__ == "__main__":
    main()
