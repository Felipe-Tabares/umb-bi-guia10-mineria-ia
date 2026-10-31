"""Gráficas del Segmentador de Clientes.

Cada tipo de gráfica es una función que dibuja sobre una Figure de matplotlib.
No se usa pyplot: la misma función sirve para la ventana (Tkinter) y para
exportar a PNG o PDF sin pantalla. Cada grupo tiene siempre el mismo color y la
misma forma de marcador en todas las gráficas, para que no dependa solo del color.
"""
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .formato import libras, numero
from .validacion import UMBRAL_ACTIVO

COLORES = ("#2a78d6", "#eb6834", "#1baf7a", "#8a5cc2", "#eda100", "#e87ba4", "#008300", "#e34948")
MARCADORES = ("o", "s", "^", "D", "v", "P", "X", "*")
TEXTO = "#1a1a19"
TEXTO_SUAVE = "#5f5e5a"
REJILLA = "#e4e3df"
INACTIVO = "#b4b2ab"

# Clave interna -> (nombre visible, para qué sirve)
TIPOS = {
    "grupos": ("Clientes por grupo",
               "Cuántos clientes quedaron en cada grupo del modelo K-means."),
    "dispersion": ("Frecuencia vs valor total",
                   "Cada punto es un cliente; ejes logarítmicos. Muestra cómo el modelo separa a los clientes."),
    "participacion": ("Participación en el valor",
                      "Qué parte del dinero vendido aporta cada grupo, frente a cuántos clientes tiene."),
    "recencia": ("Histograma de recencia",
                 "Días desde la última compra. La línea de 90 días separa activos de inactivos."),
    "paises": ("Top 10 países por valor",
               "Los diez países que más compraron, con su parte del valor total."),
}


def color_grupo(grupo):
    return COLORES[(int(grupo) - 1) % len(COLORES)]


def marcador_grupo(grupo):
    return MARCADORES[(int(grupo) - 1) % len(MARCADORES)]


def _partir(texto, ancho=14):
    """Parte una etiqueta larga en dos líneas para que no se monten."""
    if len(texto) <= ancho or " " not in texto:
        return texto
    corte = texto.rfind(" ", 0, ancho + 1)
    corte = corte if corte > 0 else texto.find(" ")
    return texto[:corte] + "\n" + texto[corte + 1:]


def _ejes(ax, rejilla="y"):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#8d8b84")
    ax.tick_params(colors=TEXTO, labelsize=9)
    ax.set_axisbelow(True)
    if rejilla:
        ax.grid(axis=rejilla, color=REJILLA, linewidth=0.8)


def _arrays(clientes):
    return {c: np.array([f[c] for f in clientes]) for c in ("recencia_dias", "frecuencia", "valor_total", "grupo")}


def grupos(fig, clientes, modelo):
    """Barras con la cantidad de clientes de cada grupo."""
    ax = fig.add_subplot(111)
    g = _arrays(clientes)["grupo"]
    numeros = list(range(1, modelo.k + 1))
    cuantos = [int((g == n).sum()) for n in numeros]
    total = sum(cuantos)
    barras = ax.bar([_partir(modelo.etiqueta(n), 16) for n in numeros], cuantos,
                    color=[color_grupo(n) for n in numeros], width=0.62)
    ax.bar_label(barras, labels=[f"{numero(c)}  ({numero(100 * c / total, 1)} %)" for c in cuantos],
                 padding=3, fontsize=9, color=TEXTO)
    ax.set_ylabel("Clientes", color=TEXTO)
    ax.set_ylim(0, max(cuantos) * 1.15 if max(cuantos) else 1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: numero(v)))
    _ejes(ax)
    if modelo.k > 5:
        ax.tick_params(axis="x", labelsize=8)
    return f"{numero(total)} clientes en {modelo.k} grupos"


def dispersion(fig, clientes, modelo):
    """Frecuencia contra valor total en escala logarítmica, un color y un marcador por grupo."""
    ax = fig.add_subplot(111)
    a = _arrays(clientes)
    # Pequeño corrimiento horizontal fijo: muchos clientes tienen la misma frecuencia y se taparían.
    corrimiento = 10 ** np.random.default_rng(0).uniform(-0.035, 0.035, len(clientes))
    manejadores = {}
    for n in range(modelo.k, 0, -1):  # el grupo 1 se dibuja encima
        m = a["grupo"] == n
        manejadores[n] = ax.scatter(a["frecuencia"][m] * corrimiento[m], a["valor_total"][m], s=13,
                                    color=color_grupo(n), marker=marcador_grupo(n), alpha=0.6, linewidths=0,
                                    label=f"{modelo.etiqueta(n)} ({numero(int(m.sum()))})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: numero(v)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: libras(v)))
    ax.set_xlabel("Frecuencia: compras distintas (escala logarítmica)", color=TEXTO)
    ax.set_ylabel("Valor total (escala logarítmica)", color=TEXTO)
    _ejes(ax, rejilla="both")
    # Abajo a la derecha casi no hay clientes (muchas compras con poco valor), así la leyenda no tapa puntos.
    ax.legend(handles=[manejadores[n] for n in range(1, modelo.k + 1)], loc="lower right", frameon=False,
              fontsize=8.5, markerscale=1.6, handletextpad=0.3)
    silueta = f" · silueta del modelo {numero(modelo.silueta, 3)}" if modelo.silueta is not None else ""
    return f"Cada punto es un cliente; el color y la forma indican el grupo{silueta}"


def participacion(fig, clientes, modelo):
    """Porcentaje del valor vendido que aporta cada grupo, de mayor a menor."""
    ax = fig.add_subplot(111)
    a = _arrays(clientes)
    total_valor, total_clientes = a["valor_total"].sum(), len(clientes)
    filas = []
    for n in range(1, modelo.k + 1):
        m = a["grupo"] == n
        filas.append((n, 100 * a["valor_total"][m].sum() / total_valor, 100 * m.sum() / total_clientes))
    filas.sort(key=lambda f: f[1])  # barh dibuja de abajo hacia arriba: el mayor queda arriba
    barras = ax.barh([modelo.etiqueta(n) for n, _, _ in filas], [p for _, p, _ in filas],
                     color=[color_grupo(n) for n, _, _ in filas], height=0.6)
    # Dos líneas por etiqueta: en una sola, la del grupo más grande se salía del borde derecho.
    ax.bar_label(barras, labels=[f"{numero(p, 1)} % del valor\n{numero(c, 1)} % de los clientes"
                                 for _, p, c in filas], padding=4, fontsize=9, color=TEXTO)
    ax.set_xlim(0, max(p for _, p, _ in filas) * 1.5)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{numero(v)} %"))
    ax.set_xlabel("Participación en el valor total vendido", color=TEXTO)
    _ejes(ax, rejilla="x")
    mayor = filas[-1]
    return (f"El grupo {mayor[0]} tiene el {numero(mayor[2], 1)} % de los clientes y aporta el "
            f"{numero(mayor[1], 1)} % del valor ({libras(total_valor)} en total)")


def recencia(fig, clientes, modelo):
    """Histograma de días desde la última compra, con la línea de 90 días."""
    ax = fig.add_subplot(111)
    r = _arrays(clientes)["recencia_dias"]
    # Barras de 15 días con un borde justo en 90,5: el día 90 cuenta como activo y ninguna
    # barra queda partida por la línea. La primera barra va del día 0 al 15.
    corte = UMBRAL_ACTIVO + 0.5
    bordes = np.concatenate(([-0.5], np.arange(corte % 15 + 15, max(r.max(), UMBRAL_ACTIVO) + 16, 15)))
    cuentas, _ = np.histogram(r, bins=bordes)
    colores = [color_grupo(1) if derecho <= corte else INACTIVO for derecho in bordes[1:]]
    ax.bar(bordes[:-1], cuentas, width=np.diff(bordes) * 0.92, align="edge", color=colores)
    ax.axvline(corte, color=TEXTO, linestyle="--", linewidth=1.2)
    activos = int((r <= UMBRAL_ACTIVO).sum())
    inactivos = len(r) - activos
    ax.text(UMBRAL_ACTIVO + 4, max(cuentas) * 0.97, f"{UMBRAL_ACTIVO} días", fontsize=9, color=TEXTO, va="top")
    ax.legend(handles=[Patch(color=color_grupo(1), label=f"Activos, hasta {UMBRAL_ACTIVO} días: "
                             f"{numero(activos)} ({numero(100 * activos / len(r), 1)} %)"),
                       Patch(color=INACTIVO, label=f"Inactivos, más de {UMBRAL_ACTIVO} días: "
                             f"{numero(inactivos)} ({numero(100 * inactivos / len(r), 1)} %)")],
              loc="upper right", frameon=False, fontsize=9)
    ax.set_xlabel("Días desde la última compra (corte: 10 de diciembre de 2011)", color=TEXTO)
    ax.set_ylabel("Clientes", color=TEXTO)
    ax.set_xlim(bordes[0], bordes[-1])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: numero(v)))
    ax.xaxis.set_major_locator(MaxNLocator(steps=[1, 3, 6], integer=True))
    _ejes(ax)
    return f"Mediana: {numero(float(np.median(r)))} días sin comprar"


def paises(fig, clientes, modelo):
    """Los diez países con más valor vendido, de mayor a menor."""
    ax = fig.add_subplot(111)
    suma = {}
    for c in clientes:
        suma[c["pais"]] = suma.get(c["pais"], 0.0) + c["valor_total"]
    total = sum(suma.values())
    top = sorted(suma.items(), key=lambda p: p[1], reverse=True)[:10][::-1]
    barras = ax.barh([p for p, _ in top], [v for _, v in top], color=color_grupo(1), height=0.6)
    ax.bar_label(barras, labels=[f"{libras(v)}  ({numero(100 * v / total, 1)} %)" for _, v in top],
                 padding=4, fontsize=9, color=TEXTO)
    ax.set_xlim(0, max(v for _, v in top) * 1.32)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: libras(v)))
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.set_xlabel("Valor total vendido", color=TEXTO)
    _ejes(ax, rejilla="x")
    primero = top[-1]
    return f"{primero[0]} concentra el {numero(100 * primero[1] / total, 1)} % del valor de {len(suma)} países"


DIBUJAR = {"grupos": grupos, "dispersion": dispersion, "participacion": participacion,
           "recencia": recencia, "paises": paises}
# Márgenes en puntos (izquierda, abajo) para cada gráfica. Se fijan en puntos y no en fracciones
# para que títulos, ejes y fuente no se monten cuando la ventana es pequeña.
MARGENES = {"grupos": (62, 64), "dispersion": (78, 54), "participacion": (178, 54),
            "recencia": (62, 54), "paises": (118, 54)}


def _vacia(fig, titulo):
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0.5, 0.5, "No hay clientes para graficar.\nAgregue uno o importe un CSV.",
            ha="center", va="center", fontsize=12, color=TEXTO)
    _encabezado(fig, titulo, "")


def _encabezado(fig, titulo, lectura):
    alto = fig.get_figheight() * 72
    fig.text(0.02, 1 - 10 / alto, titulo, fontsize=13, fontweight="bold", color=TEXTO, ha="left", va="top")
    if lectura:
        fig.text(0.02, 1 - 32 / alto, lectura, fontsize=9.5, color=TEXTO_SUAVE, ha="left", va="top")


def ubicar(fig, tipo):
    """Ajusta los márgenes al tamaño actual de la figura. La ventana lo llama también al redimensionar."""
    ancho, alto = fig.get_figwidth() * 72, fig.get_figheight() * 72
    izquierda, abajo = MARGENES.get(tipo, (62, 54))
    fig.subplots_adjust(left=min(izquierda / ancho, 0.45), right=1 - 16 / ancho,
                        bottom=min(abajo / alto, 0.35), top=1 - 64 / alto)


def dibujar(fig, tipo, clientes, modelo):
    """Limpia la figura y dibuja el tipo pedido. Devuelve la frase de lectura que va debajo del título."""
    if tipo not in DIBUJAR:
        raise ValueError(f"Tipo de gráfica desconocido: {tipo}")
    fig.clear()
    titulo = TIPOS[tipo][0]
    if not clientes:
        _vacia(fig, titulo)
        return ""
    lectura = DIBUJAR[tipo](fig, clientes, modelo)
    _encabezado(fig, titulo, lectura)
    fig.text(0.02, 6 / (fig.get_figheight() * 72), f"Fuente: UCI Online Retail 2010-2011 y datos del Segmentador · "
             f"modelo K-means con k = {modelo.k}", fontsize=7.5, color="#77756f", va="bottom")
    ubicar(fig, tipo)
    return lectura


def exportar(ruta, tipo, clientes, modelo):
    """Guarda la gráfica en PNG o PDF según la extensión. Funciona sin pantalla."""
    # backend_pdf se importa explícito para que PyInstaller lo empaquete; sin esto el PDF falla en el ejecutable.
    from matplotlib.backends import backend_pdf  # noqa: F401
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(9, 5.4), dpi=100, facecolor="white")
    FigureCanvasAgg(fig)
    dibujar(fig, tipo, clientes, modelo)
    fig.savefig(ruta, dpi=200 if str(ruta).lower().endswith(".png") else None, facecolor="white")
    return ruta
