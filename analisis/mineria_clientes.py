# -*- coding: utf-8 -*-
"""Guía 10, minería de datos con IA: segmentación de clientes de una tienda en línea.

Datos: Online Retail del UCI Machine Learning Repository (Chen, 2015). Son las
541.909 líneas de factura de una tienda en línea del Reino Unido entre el 1 de
diciembre de 2010 y el 9 de diciembre de 2011.

El script recorre las fases de la guía:
  Fase 1. Comprensión de los datos
  Fase 2. Preparación, con una bitácora de qué se cambió, por qué y cuántas filas
  Fase 3. Exploración: gráficos e indicadores
  Fase 4. K-means sobre recencia, frecuencia y valor (RFM)
  Fase 5. Evaluación: silueta, Davies-Bouldin, estabilidad y perfil de cada grupo

Deja todo en resultados/ (figuras, tablas, resultados.json y reporte.html) y la
tabla de clientes preparada en datos/preparados/clientes.csv, que es la misma que
usa el software de escritorio.

    python analisis/mineria_clientes.py              # corre todo y abre el reporte
    python analisis/mineria_clientes.py --sin-abrir  # sin abrir el navegador
"""
import base64
import html
import json
import sys
import webbrowser
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.metrics import (adjusted_rand_score, calinski_harabasz_score,  # noqa: E402
                             davies_bouldin_score, silhouette_samples,
                             silhouette_score)
from sklearn.model_selection import cross_val_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.tree import DecisionTreeClassifier, export_text  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ORIGINAL = RAIZ / "datos" / "Online Retail.xlsx"
PREPARADOS = RAIZ / "datos" / "preparados"
RESULTADOS = RAIZ / "resultados"
FIGURAS = RESULTADOS / "figuras"

CORTE = pd.Timestamp("2011-12-10")  # el día siguiente a la última factura
DIAS_ACTIVO = 90                    # más de 90 días sin comprar = inactivo
K = 4
SEMILLA = 42
# Códigos que no son mercancía: envíos, comisiones, ajustes, descuentos y muestras.
NO_PRODUCTO = {"POST", "DOT", "M", "C2", "D", "S", "BANK CHARGES", "AMAZONFEE",
               "CRUK", "PADS", "B"}
PAISES = {"EIRE": "Ireland", "RSA": "South Africa"}
NOMBRES = {1: "Frecuentes de alto valor", 2: "Regulares",
           3: "Recientes de bajo gasto", 4: "Dormidos"}
COLORES = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#8a5cc2"}
MARCAS = {1: "o", 2: "s", 3: "^", 4: "D"}
TINTA, SUAVE, REJILLA, AZUL = "#1a1a19", "#555550", "#e4e3df", "#2a78d6"

BITACORA = []
PARTES = []
RES = {}


# ---------------------------------------------------------------------------
# Salida: todo se imprime en consola y además se guarda para el reporte HTML
# ---------------------------------------------------------------------------
def titulo(texto):
    print("\n" + "=" * 78 + "\n" + texto + "\n" + "=" * 78)
    PARTES.append(f"<h2>{html.escape(texto)}</h2>")


def subtitulo(texto):
    print("\n" + texto)
    PARTES.append(f"<h3>{html.escape(texto)}</h3>")


def mostrar(*cosas):
    texto = " ".join(str(c) for c in cosas)
    print(texto)
    PARTES.append(f"<p>{html.escape(texto)}</p>")


def mostrar_tabla(tabla):
    print(tabla.to_string())
    if isinstance(tabla, pd.Series):
        tabla = tabla.to_frame()
    PARTES.append(tabla.to_html(border=0))


def miles(x, dec=0):
    """2016.0 -> '2.016', como se escribe en Colombia."""
    texto = f"{x:,.{dec}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def anotar(paso, encontrado, accion, motivo, antes, despues):
    BITACORA.append(dict(paso=paso, encontrado=encontrado, accion=accion,
                         motivo=motivo, filas_antes=antes, filas_despues=despues))
    mostrar(f"[{paso}] {encontrado}. {accion}: {miles(antes)} -> {miles(despues)} filas.")


def estilo(ax, eje="y"):
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(SUAVE)
    ax.tick_params(colors=SUAVE, labelcolor=TINTA, labelsize=9)
    ax.grid(axis=eje, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)


def guardar(fig, nombre, pie):
    ruta = FIGURAS / nombre
    fig.tight_layout()
    fig.savefig(ruta, dpi=200, facecolor="white")
    plt.close(fig)
    datos = base64.b64encode(ruta.read_bytes()).decode()
    PARTES.append(f'<figure><img src="data:image/png;base64,{datos}" alt="{pie}">'
                  f"<figcaption>{html.escape(pie)}</figcaption></figure>")
    print("  figura:", nombre)


# ---------------------------------------------------------------------------
# Fase 1. Comprensión de los datos
# ---------------------------------------------------------------------------
def cargar():
    titulo("FASE 1. Selección y comprensión de los datos")
    crudo = pd.read_excel(ORIGINAL, dtype={"InvoiceNo": str, "StockCode": str})
    mostrar("Fuente: Online Retail, UCI Machine Learning Repository,"
            " https://doi.org/10.24432/C5BW33")
    mostrar("Filas:", miles(len(crudo)), "| columnas:", crudo.shape[1],
            "| desde", crudo["InvoiceDate"].min(), "hasta", crudo["InvoiceDate"].max())
    tipos = {
        "InvoiceNo": ("Cualitativa nominal",
                      "Número de factura; si empieza por C es una cancelación"),
        "StockCode": ("Cualitativa nominal", "Código del producto"),
        "Description": ("Cualitativa nominal", "Nombre del producto"),
        "Quantity": ("Cuantitativa discreta", "Unidades de la línea"),
        "InvoiceDate": ("Cuantitativa (fecha)", "Fecha y hora de la factura"),
        "UnitPrice": ("Cuantitativa continua", "Precio por unidad en libras esterlinas"),
        "CustomerID": ("Cualitativa nominal", "Identificador del cliente"),
        "Country": ("Cualitativa nominal", "País del cliente"),
    }
    variables = pd.DataFrame(
        [(c, t, d, str(crudo[c].dtype), int(crudo[c].isna().sum()), int(crudo[c].nunique()))
         for c, (t, d) in tipos.items()],
        columns=["variable", "tipo", "descripcion", "tipo_en_archivo", "nulos", "distintos"],
    ).set_index("variable")
    mostrar_tabla(variables[["tipo", "tipo_en_archivo", "nulos", "distintos"]])
    variables.to_csv(RESULTADOS / "variables.csv")
    RES["filas_originales"] = len(crudo)
    return crudo


# ---------------------------------------------------------------------------
# Fase 2. Preparación de los datos
# ---------------------------------------------------------------------------
def preparar(crudo):
    titulo("FASE 2. Preparación de los datos (bitácora)")
    df = crudo.copy()

    n = len(df)
    df = df.drop_duplicates()
    anotar("Duplicados", f"{miles(n - len(df))} líneas idénticas repetidas",
           "Eliminar", "La misma línea cargada dos veces infla ventas y frecuencia",
           n, len(df))

    n = len(df)
    cancelada = df["InvoiceNo"].str.startswith("C")
    devoluciones = df[cancelada].copy()
    df = df[~cancelada]
    anotar("Cancelaciones", f"{miles(cancelada.sum())} líneas de facturas que empiezan por C",
           "Sacar de las ventas y contarlas aparte por cliente",
           "Son devoluciones, no compras", n, len(df))

    n = len(df)
    malas = df["Quantity"] <= 0
    df = df[~malas]
    anotar("Cantidad no positiva", f"{miles(malas.sum())} líneas con cantidad 0 o negativa",
           "Eliminar", "Son ajustes de inventario sin factura de venta", n, len(df))

    n = len(df)
    malas = df["UnitPrice"] <= 0
    df = df[~malas]
    anotar("Precio no positivo", f"{miles(malas.sum())} líneas con precio 0 o negativo",
           "Eliminar", "Una venta sin precio no aporta valor y distorsiona el ticket",
           n, len(df))

    n = len(df)
    no_es = df["StockCode"].isin(NO_PRODUCTO) | df["StockCode"].str.startswith("gift_")
    df = df[~no_es]
    anotar("Códigos que no son producto",
           f"{miles(no_es.sum())} líneas de envío, comisiones, descuentos, muestras y bonos",
           "Eliminar", "No son mercancía y la guía pregunta por productos", n, len(df))

    # Un mismo código aparece con varias descripciones; se deja la más usada.
    df["Description"] = df["Description"].str.strip()
    varias = int((df.groupby("StockCode")["Description"].nunique() > 1).sum())
    comun = df.groupby("StockCode")["Description"].agg(lambda s: s.mode().iloc[0])
    df["Description"] = df["StockCode"].map(comun)
    anotar("Descripciones inconsistentes",
           f"{miles(varias)} códigos con más de una descripción",
           "Unificar con la descripción más frecuente de cada código",
           "Si no, un producto cuenta como varios en el ranking", len(df), len(df))

    df["Country"] = df["Country"].replace(PAISES)
    anotar("Nombres de país", "EIRE y RSA en vez de Ireland y South Africa",
           "Renombrar", "Que cada país tenga un solo nombre", len(df), len(df))

    n = len(df)
    sin_cliente = df["CustomerID"].isna()
    valor_sin = (df.loc[sin_cliente, "Quantity"] * df.loc[sin_cliente, "UnitPrice"]).sum()
    valor_todo = (df["Quantity"] * df["UnitPrice"]).sum()
    df = df[~sin_cliente]
    anotar("Cliente faltante",
           f"{miles(sin_cliente.sum())} líneas sin CustomerID"
           f" ({miles(valor_sin / valor_todo * 100, 1)} % del valor)",
           "Eliminar del análisis", "No se pueden asignar a ningún cliente y no hay"
           " forma honesta de imputarlas", n, len(df))
    RES["pct_valor_sin_cliente"] = round(float(valor_sin / valor_todo) * 100, 1)

    # Conversión de tipos
    df["CustomerID"] = df["CustomerID"].astype(int).astype(str)
    devoluciones = devoluciones.dropna(subset=["CustomerID"])
    devoluciones["CustomerID"] = devoluciones["CustomerID"].astype(int).astype(str)
    df["Importe"] = df["Quantity"] * df["UnitPrice"]
    df["Mes"] = df["InvoiceDate"].dt.to_period("M")
    anotar("Conversión de variables", "CustomerID venía como decimal (17850.0)",
           "Pasar a texto entero y calcular Importe = Quantity x UnitPrice",
           "El identificador no es una cantidad", len(df), len(df))

    # Ventas que después se anularon completas: la factura C trae el mismo cliente,
    # el mismo producto y la misma cantidad en negativo. Se saca la venta más
    # reciente anterior a la anulación, para no contar dos veces un pedido que no fue.
    n = len(df)
    ventas = df.reset_index().rename(columns={"index": "fila"})
    anul = devoluciones.assign(Quantity=-devoluciones["Quantity"])
    pares = ventas.merge(anul[["CustomerID", "StockCode", "Quantity", "InvoiceDate"]],
                         on=["CustomerID", "StockCode", "Quantity"], suffixes=("", "_anul"))
    pares = pares[pares["InvoiceDate"] <= pares["InvoiceDate_anul"]]
    pares = pares.sort_values("InvoiceDate").groupby(
        ["CustomerID", "StockCode", "Quantity", "InvoiceDate_anul"]).tail(1)
    anuladas = pares["fila"].unique()
    valor_anulado = (df.loc[anuladas, "Quantity"] * df.loc[anuladas, "UnitPrice"]).sum()
    df = df.drop(index=anuladas)
    anotar("Ventas anuladas después",
           f"{miles(len(anuladas))} ventas con una cancelación idéntica posterior"
           f" ({miles(valor_anulado)} libras)",
           "Eliminar la venta original", "El pedido no se hizo efectivo; los dos más"
           " grandes eran de 80.995 y 74.215 unidades", n, len(df))

    # Clientes con compras registradas en más de un país: se deja el más frecuente.
    paises = df.groupby("CustomerID")["Country"].agg(lambda s: s.mode().iloc[0])
    varios = int((df.groupby("CustomerID")["Country"].nunique() > 1).sum())
    df["Country"] = df["CustomerID"].map(paises)
    anotar("Cliente en varios países", f"{varios} clientes con dos países",
           "Dejar el país donde más compró", "Un cliente debe tener un solo país",
           len(df), len(df))

    RES["lineas_limpias"] = len(df)
    pd.DataFrame(BITACORA).to_csv(RESULTADOS / "bitacora_preparacion.csv", index=False)
    return df, devoluciones


def tabla_clientes(ventas, devoluciones):
    subtitulo("Tabla de clientes (RFM) y valores atípicos")
    c = ventas.groupby("CustomerID").agg(
        pais=("Country", "first"),
        ultima=("InvoiceDate", "max"),
        frecuencia=("InvoiceNo", "nunique"),
        valor_total=("Importe", "sum"),
        unidades=("Quantity", "sum"),
        productos_distintos=("StockCode", "nunique"),
    )
    c["recencia_dias"] = (CORTE - c["ultima"]).dt.days
    c["ticket_promedio"] = c["valor_total"] / c["frecuencia"]
    dev = devoluciones.groupby("CustomerID")["InvoiceNo"].nunique()
    c["devoluciones"] = dev.reindex(c.index).fillna(0).astype(int)
    c["mercado"] = np.where(c["pais"] == "United Kingdom", "Reino Unido", "Internacional")
    c["estado"] = np.where(c["recencia_dias"] <= DIAS_ACTIVO, "Activo", "Inactivo")
    c = c.drop(columns="ultima")
    c.index.name = "cliente"
    mostrar("Clientes:", miles(len(c)))
    mostrar_tabla(c[["recencia_dias", "frecuencia", "valor_total"]].describe().round(1))

    # Atípicos con la regla de 1,5 veces el rango intercuartílico.
    atip = {}
    for col in ("recencia_dias", "frecuencia", "valor_total"):
        q1, q3 = c[col].quantile([0.25, 0.75])
        atip[col] = int(((c[col] < q1 - 1.5 * (q3 - q1)) | (c[col] > q3 + 1.5 * (q3 - q1))).sum())
    mostrar("Atípicos (regla 1,5 RIC):", atip)
    mostrar("Decisión: no se borran porque son clientes reales (mayoristas);"
            " para K-means se usa log(1 + x) y luego estandarización.")
    RES["atipicos"] = atip
    anotar("Valores atípicos", f"{atip['frecuencia']} en frecuencia y"
           f" {atip['valor_total']} en valor total", "Conservar y transformar con log(1 + x)",
           "Son mayoristas reales; borrarlos quitaría el grupo que más vende",
           len(c), len(c))
    anotar("Estandarización", "Recencia en días, frecuencia en facturas y valor en libras",
           "log(1 + x) y luego media 0 y desviación 1",
           "K-means usa distancias; sin esto el valor decide solo", len(c), len(c))
    pd.DataFrame(BITACORA).to_csv(RESULTADOS / "bitacora_preparacion.csv", index=False)
    return c


# ---------------------------------------------------------------------------
# Fase 3. Exploración y visualización
# ---------------------------------------------------------------------------
def explorar(ventas, devoluciones, c):
    titulo("FASE 3. Exploración y visualización")

    subtitulo("Indicadores")
    facturas = ventas["InvoiceNo"].nunique()
    canceladas = devoluciones["InvoiceNo"].nunique()
    top = c["valor_total"].sort_values(ascending=False)
    ind = {
        "ventas_totales": round(float(ventas["Importe"].sum()), 2),
        "facturas": int(facturas),
        "ticket_promedio_factura": round(float(ventas["Importe"].sum() / facturas), 2),
        "tasa_recompra_pct": round(float((c["frecuencia"] >= 2).mean() * 100), 1),
        "clientes_activos_pct": round(float((c["estado"] == "Activo").mean() * 100), 1),
        "concentracion_top20_pct": round(float(
            top.head(int(len(top) * 0.2)).sum() / top.sum() * 100), 1),
        "tasa_cancelacion_pct": round(float(canceladas / (facturas + canceladas) * 100), 1),
    }
    for k, v in ind.items():
        mostrar(f"{k}: {v}")
    RES["indicadores"] = ind

    # Gráfico 1: ventas por mes
    mes = ventas.groupby("Mes")["Importe"].sum()
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    colores = [AZUL] * (len(mes) - 1) + ["#a9c7ee"]
    ax.bar([p.strftime("%b %y") for p in mes.index], mes.values / 1000, color=colores, width=0.7)
    ax.set_ylabel("Ventas (miles de libras)", color=TINTA, fontsize=9)
    ax.tick_params(axis="x", rotation=45)
    estilo(ax)
    guardar(fig, "g1_ventas_por_mes.png",
            "Ventas por mes (diciembre de 2011 llega solo hasta el día 9)")
    RES["mes_pico"] = str(mes.idxmax())

    # Gráfico 2: productos con más demanda
    prod = ventas.groupby("Description")["Quantity"].sum().nlargest(10).sort_values()
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.barh([d.title()[:34] for d in prod.index], prod.values / 1000, color=AZUL, height=0.6)
    ax.set_xlabel("Unidades vendidas (miles)", color=TINTA, fontsize=9)
    estilo(ax, "x")
    guardar(fig, "g2_productos_mas_vendidos.png", "Los 10 productos con más unidades vendidas")
    RES["top_productos"] = {k: int(v) for k, v in prod.sort_values(ascending=False).items()}

    # Gráfico 3: frecuencia contra valor total
    rho = c["frecuencia"].corr(c["valor_total"], method="spearman")
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.scatter(c["frecuencia"], c["valor_total"], s=8, alpha=0.35, color=AZUL, linewidths=0)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Frecuencia (facturas en el año, escala log)", color=TINTA, fontsize=9)
    ax.set_ylabel("Valor total (libras, escala log)", color=TINTA, fontsize=9)
    estilo(ax, "both")
    guardar(fig, "g3_frecuencia_vs_valor.png",
            f"Frecuencia contra valor total por cliente (Spearman = {rho:.2f})")
    RES["spearman_frecuencia_valor"] = round(float(rho), 3)

    # Gráfico 4: recencia
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.hist(c["recencia_dias"], bins=37, color=AZUL, edgecolor="white")
    ax.axvline(DIAS_ACTIVO, color=TINTA, linestyle="--", linewidth=1)
    ax.text(DIAS_ACTIVO + 5, ax.get_ylim()[1] * 0.9, "90 días", color=TINTA, fontsize=9)
    ax.set_xlabel("Días desde la última compra", color=TINTA, fontsize=9)
    ax.set_ylabel("Clientes", color=TINTA, fontsize=9)
    estilo(ax)
    guardar(fig, "g4_recencia.png", "Días desde la última compra de cada cliente")

    subtitulo("Patrones")
    por_mercado = c.groupby("mercado").agg(clientes=("frecuencia", "size"),
                                           frecuencia_mediana=("frecuencia", "median"),
                                           frecuencia_media=("frecuencia", "mean"),
                                           valor_mediano=("valor_total", "median"))
    mostrar_tabla(por_mercado.round(1))
    pais = c.groupby("pais").agg(clientes=("frecuencia", "size"),
                                 frecuencia_media=("frecuencia", "mean"),
                                 valor_total=("valor_total", "sum"))
    pais = pais[pais["clientes"] >= 10].sort_values("frecuencia_media", ascending=False)
    mostrar("Países con 10 o más clientes, ordenados por frecuencia media:")
    mostrar_tabla(pais.head(8).round(1))
    RES["por_mercado"] = por_mercado.round(2).to_dict(orient="index")
    RES["paises_frecuencia"] = pais.head(5).round(2).to_dict(orient="index")


# ---------------------------------------------------------------------------
# Fase 4. Minería de datos: K-means sobre RFM
# ---------------------------------------------------------------------------
def matriz(c):
    rfm = np.log1p(c[["recencia_dias", "frecuencia", "valor_total"]])
    return StandardScaler().fit_transform(rfm)


def agrupar(c):
    titulo("FASE 4. K-means sobre recencia, frecuencia y valor")
    x = matriz(c)
    filas = []
    for k in range(2, 9):
        km = KMeans(n_clusters=k, n_init=20, random_state=SEMILLA).fit(x)
        filas.append(dict(k=k, silueta=silhouette_score(x, km.labels_),
                          davies_bouldin=davies_bouldin_score(x, km.labels_),
                          calinski_harabasz=calinski_harabasz_score(x, km.labels_),
                          inercia=km.inertia_,
                          tamanos=str(sorted(np.bincount(km.labels_).tolist()))))
    evaluacion = pd.DataFrame(filas).set_index("k")
    mostrar_tabla(evaluacion.drop(columns="tamanos").round(3))
    for k, tamanos in evaluacion["tamanos"].items():
        mostrar(f"k = {k}, clientes por grupo: {tamanos}")
    evaluacion.to_csv(RESULTADOS / "evaluacion_k.csv")
    RES["evaluacion_k"] = evaluacion.round(4).reset_index().to_dict(orient="records")

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.2))
    a1.plot(evaluacion.index, evaluacion["inercia"], marker="o", color=AZUL, linewidth=2)
    a1.set_title("Inercia (método del codo)", fontsize=10, color=TINTA)
    a2.plot(evaluacion.index, evaluacion["silueta"], marker="o", color=AZUL, linewidth=2)
    a2.set_title("Coeficiente de silueta", fontsize=10, color=TINTA)
    for a in (a1, a2):
        a.axvline(K, color=SUAVE, linestyle="--", linewidth=1)
        a.set_xlabel("Número de grupos (k)", color=TINTA, fontsize=9)
        estilo(a)
    guardar(fig, "g5_codo_y_silueta.png", "Inercia y silueta para k de 2 a 8 (línea: k = 4)")

    km = KMeans(n_clusters=K, n_init=20, random_state=SEMILLA).fit(x)
    c["grupo_km"] = km.labels_
    # Se numeran por valor promedio, de mayor a menor, para que el 1 sea el mejor.
    orden = c.groupby("grupo_km")["valor_total"].mean().sort_values(ascending=False).index
    c["grupo"] = c["grupo_km"].map({g: i + 1 for i, g in enumerate(orden)})
    c["nombre_grupo"] = c["grupo"].map(NOMBRES)
    return x


# ---------------------------------------------------------------------------
# Fase 5. Evaluación del modelo
# ---------------------------------------------------------------------------
def evaluar(c, x):
    titulo("FASE 5. Evaluación del modelo con k = 4")
    sil = silhouette_score(x, c["grupo"])
    mostrar(f"Silueta: {sil:.3f} | Davies-Bouldin: {davies_bouldin_score(x, c['grupo']):.3f}"
            f" | Calinski-Harabasz: {calinski_harabasz_score(x, c['grupo']):.0f}")
    c["silueta"] = silhouette_samples(x, c["grupo"])

    # Estabilidad: el mismo k con otras 10 semillas, comparado con el modelo base.
    ari = [adjusted_rand_score(c["grupo_km"],
                               KMeans(n_clusters=K, n_init=20, random_state=s).fit_predict(x))
           for s in range(1, 11)]
    mostrar(f"Estabilidad con 10 semillas (índice de Rand ajustado): mínimo {min(ari):.3f},"
            f" promedio {np.mean(ari):.3f}")

    total = c["valor_total"].sum()
    perfil = c.groupby(["grupo", "nombre_grupo"]).agg(
        clientes=("frecuencia", "size"),
        recencia_mediana=("recencia_dias", "median"),
        frecuencia_mediana=("frecuencia", "median"),
        valor_mediano=("valor_total", "median"),
        ticket_mediano=("ticket_promedio", "median"),
        productos_medianos=("productos_distintos", "median"),
        pct_activos=("estado", lambda s: (s == "Activo").mean() * 100),
        pct_reino_unido=("mercado", lambda s: (s == "Reino Unido").mean() * 100),
        devoluciones_media=("devoluciones", "mean"),
        silueta_media=("silueta", "mean"),
        valor=("valor_total", "sum"),
    )
    perfil["pct_clientes"] = perfil["clientes"] / len(c) * 100
    perfil["pct_valor"] = perfil["valor"] / total * 100
    perfil = perfil.drop(columns="valor")
    mostrar_tabla(perfil.round(2).T)
    perfil.round(3).to_csv(RESULTADOS / "perfil_grupos.csv")

    # Qué variables separan los grupos: un árbol pequeño que imita a K-means.
    variables = ["recencia_dias", "frecuencia", "valor_total", "ticket_promedio",
                 "productos_distintos", "devoluciones"]
    arbol = DecisionTreeClassifier(max_depth=3, random_state=SEMILLA)
    exactitud = cross_val_score(arbol, c[variables], c["grupo"], cv=5).mean()
    arbol.fit(c[variables], c["grupo"])
    importancia = pd.Series(arbol.feature_importances_, index=variables).sort_values(
        ascending=False)
    mostrar(f"Árbol de 3 niveles que reproduce los grupos: exactitud en validación"
            f" cruzada de 5 partes = {exactitud:.3f}")
    mostrar_tabla(importancia.round(3).rename("importancia"))
    reglas = export_text(arbol, feature_names=variables, decimals=0)
    print(reglas)
    PARTES.append(f"<pre>{html.escape(reglas)}</pre>")

    RES["modelo"] = dict(
        k=K, silueta=round(float(sil), 3),
        davies_bouldin=round(float(davies_bouldin_score(x, c["grupo"])), 3),
        calinski_harabasz=round(float(calinski_harabasz_score(x, c["grupo"])), 1),
        estabilidad_ari_min=round(float(min(ari)), 3),
        estabilidad_ari_promedio=round(float(np.mean(ari)), 3),
        arbol_exactitud_cv=round(float(exactitud), 3),
        importancia={k: round(float(v), 3) for k, v in importancia.items()},
    )
    RES["perfil"] = perfil.reset_index().round(2).to_dict(orient="records")

    # Gráfico 6: los grupos en el plano frecuencia y valor
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    for g in range(1, K + 1):
        s = c[c["grupo"] == g]
        ax.scatter(s["frecuencia"], s["valor_total"], s=10, alpha=0.5, color=COLORES[g],
                   marker=MARCAS[g], linewidths=0, label=f"{g}. {NOMBRES[g]}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Frecuencia (facturas, escala log)", color=TINTA, fontsize=9)
    ax.set_ylabel("Valor total (libras, escala log)", color=TINTA, fontsize=9)
    ax.legend(frameon=False, fontsize=8, markerscale=2, labelcolor=TINTA)
    estilo(ax, "both")
    guardar(fig, "g6_grupos_frecuencia_valor.png", "Los cuatro grupos de K-means")

    # Gráfico 7: peso de cada grupo en clientes y en valor
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    pos = np.arange(K)
    etiquetas = [f"{g}. {NOMBRES[g]}" for g in range(1, K + 1)]
    ax.barh(pos + 0.2, perfil["pct_clientes"].values, height=0.38, color="#a9c7ee",
            label="% de clientes")
    ax.barh(pos - 0.2, perfil["pct_valor"].values, height=0.38, color=AZUL,
            label="% del valor vendido")
    for p, v in zip(pos, perfil["pct_valor"].values):
        ax.text(v + 1, p - 0.2, f"{v:.0f} %", va="center", fontsize=8, color=TINTA)
    for p, v in zip(pos, perfil["pct_clientes"].values):
        ax.text(v + 1, p + 0.2, f"{v:.0f} %", va="center", fontsize=8, color=TINTA)
    ax.set_yticks(pos, etiquetas)
    ax.invert_yaxis()
    ax.set_xlim(0, 75)
    ax.set_xlabel("Porcentaje", color=TINTA, fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=TINTA)
    estilo(ax, "x")
    guardar(fig, "g7_peso_de_cada_grupo.png", "Peso de cada grupo en clientes y en valor")


# ---------------------------------------------------------------------------
# Salidas
# ---------------------------------------------------------------------------
def guardar_todo(c):
    columnas = ["pais", "mercado", "recencia_dias", "frecuencia", "valor_total",
                "ticket_promedio", "unidades", "productos_distintos", "devoluciones",
                "estado", "grupo", "nombre_grupo"]
    salida = c[columnas].copy()
    salida["valor_total"] = salida["valor_total"].round(2)
    salida["ticket_promedio"] = salida["ticket_promedio"].round(2)
    salida.to_csv(PREPARADOS / "clientes.csv")
    (RESULTADOS / "resultados.json").write_text(
        json.dumps(RES, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    css = ("body{font-family:Arial,sans-serif;max-width:960px;margin:32px auto;"
           "padding:0 16px;color:#1a1a19;line-height:1.5}"
           "h2{border-bottom:1px solid #999;padding-bottom:4px;margin-top:40px}"
           "table{border-collapse:collapse;margin:8px 0 16px;font-size:14px}"
           "th,td{padding:4px 12px;border-bottom:1px solid #ddd;text-align:right}"
           "th:first-child,td:first-child{text-align:left}"
           "img{max-width:100%}figcaption{font-size:14px;color:#555}"
           "pre{background:#f6f6f4;padding:12px;overflow-x:auto}")
    pagina = ("<!doctype html>\n<html lang='es'>\n<head>\n<meta charset='utf-8'>\n"
              "<meta name='viewport' content='width=device-width'>\n"
              f"<title>Guía 10: minería de datos con IA</title>\n<style>{css}</style>\n"
              "</head>\n<body>\n<h1>Guía 10: segmentación de clientes con K-means</h1>\n"
              "<p>Inteligencia de Negocios, Universidad Manuela Beltrán. Datos: Online"
              " Retail, UCI Machine Learning Repository.</p>\n"
              + "\n".join(PARTES) + "\n</body>\n</html>\n")
    reporte = RESULTADOS / "reporte.html"
    reporte.write_text(pagina, encoding="utf-8")
    print("\nGuardado: datos/preparados/clientes.csv, resultados/ y resultados/reporte.html")
    if "--sin-abrir" not in sys.argv:
        webbrowser.open(reporte.resolve().as_uri())


if __name__ == "__main__":
    for carpeta in (PREPARADOS, RESULTADOS, FIGURAS):
        carpeta.mkdir(parents=True, exist_ok=True)
    crudo = cargar()
    ventas, devoluciones = preparar(crudo)
    clientes = tabla_clientes(ventas, devoluciones)
    explorar(ventas, devoluciones, clientes)
    matriz_rfm = agrupar(clientes)
    evaluar(clientes, matriz_rfm)
    guardar_todo(clientes)
