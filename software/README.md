# Segmentador de Clientes

Programa de escritorio para gestionar los clientes de una tienda en línea, agruparlos con K-means y ver
las gráficas que salen de esos grupos. Arranca con los 4.324 clientes que preparamos en el análisis de la
Guía 10 de Inteligencia de Negocios (UMB), tomados del conjunto UCI Online Retail (Reino Unido, 2010-2011),
cada uno con su recencia, frecuencia y valor total, y con el grupo que le asignó el modelo.

## Cómo se usa (sin instalar nada)

1. Descargue el `.zip` de su sistema en la sección **Releases** del repositorio (versión v1.0).
2. Descomprímalo.
3. Windows: abra `SegmentadorClientes\SegmentadorClientes.exe`. macOS: abra `SegmentadorClientes.app`
   (la primera vez, clic derecho y Abrir). Linux: `SegmentadorClientes/SegmentadorClientes`.

Los datos se guardan en `segmentador_clientes.db`, en la misma carpeta del programa. Si esa carpeta no
permite escribir, se guardan en la carpeta `SegmentadorClientes` del usuario.

Si Windows muestra "Windows protegió su PC", es porque el ejecutable no tiene firma comercial: clic en
**Más información** y luego en **Ejecutar de todas formas**.

## Qué hace

- Tabla de clientes con búsqueda por código o país, filtros por grupo y por estado, y orden por columna.
- Formulario para agregar, editar y eliminar clientes. Valida código único, país, recencia entera desde 0,
  frecuencia entera desde 1 y valor total mayor que 0 (con coma o punto decimal). El estado (activo hasta
  90 días), el mercado y el grupo se calculan solos; el grupo lo asigna el modelo K-means vigente.
- Panel para recalcular los grupos con K-means escogiendo k entre 2 y 8. Muestra silueta, Davies-Bouldin,
  tamaño y medianas de recencia, frecuencia y valor de cada grupo.
- Cinco gráficas que se redibujan solas: clientes por grupo, frecuencia contra valor total, participación
  de cada grupo en el valor vendido, histograma de recencia y los diez países con más valor. Se exportan a
  PNG o PDF.
- Deshacer, restaurar los datos originales del análisis y bitácora de cambios con fecha.
- Importar CSV (coma o punto y coma) y exportar CSV con punto y coma, que abre directo en Excel.

## Para desarrolladores

```
pip install -r requirements.txt
python app.py                          # ventana
python app.py --autoprueba salida      # 33 pruebas sin intervención, deja reporte y gráficas
python -m unittest discover -s pruebas # 38 pruebas unitarias
```

Para empaquetar (en Windows el separador de `--add-data` es `;` en vez de `:`):

```
pip install "pyinstaller>=6.16"
pyinstaller --noconfirm --clean --onedir --windowed --collect-submodules numpy._core \
  --add-data "segmentador/datos_iniciales/clientes.csv:segmentador/datos_iniciales" \
  --name SegmentadorClientes app.py
```

Cada push a `main` compila y prueba el ejecutable en Windows, macOS y Linux con GitHub Actions
(`.github/workflows/compilar.yml` en la raíz del repositorio) y publica los `.zip` en la versión v1.0.

| Archivo | Función |
|---|---|
| `app.py` | Punto de entrada y argumentos |
| `segmentador/validacion.py` | Reglas de validación de un cliente |
| `segmentador/modelo.py` | K-means: entrenar, asignar grupo, nombres y perfil de los grupos |
| `segmentador/datos.py` | Base SQLite, bitácora, deshacer, restaurar, CSV |
| `segmentador/graficas.py` | Las cinco gráficas con matplotlib |
| `segmentador/interfaz.py` | Ventana en Tkinter |
| `segmentador/formato.py` | Números con punto de miles y coma decimal |
| `segmentador/autoprueba.py` | Prueba del programa empaquetado en el equipo donde corre |
| `segmentador/datos_iniciales/clientes.csv` | Clientes del análisis (copia de `datos/preparados/clientes.csv`) |
| `pruebas/` | Pruebas unitarias y `fixture_clientes.csv`, datos sintéticos solo para las pruebas |
| `docs/` | Documentación, diagramas, pseudocódigo PSeInt y capturas |

La documentación completa está en [docs/DOCUMENTACION.md](docs/DOCUMENTACION.md).

Autores: Andrés Felipe Tabares Benavides y Kevin Santiago García · Universidad Manuela Beltrán · Inteligencia de Negocios · 2026
