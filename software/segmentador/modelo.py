"""Modelo de segmentación con K-means sobre recencia, frecuencia y valor (RFM).

Receta, la misma del análisis de la Fase 4:
  1. Variables: log(1 + recencia_dias), log(1 + frecuencia), log(1 + valor_total).
     El logaritmo baja el peso de los pocos clientes que compran muchísimo.
  2. Estandarización (StandardScaler): cada variable con media 0 y desviación 1,
     para que ninguna domine la distancia solo por su escala.
  3. KMeans(n_clusters=k, n_init=20, random_state=42).
  4. Los grupos se renumeran por valor_total medio, de mayor a menor, para que el
     grupo 1 sea siempre el de más valor y los números no cambien entre corridas.

El modelo guarda la media y la escala del estandarizador y los centroides. Con
eso un cliente nuevo se asigna al centroide más cercano sin volver a entrenar.
"""
from datetime import datetime

import numpy as np

from .validacion import UMBRAL_ACTIVO, ErrorValidacion

K_MINIMO, K_MAXIMO, K_DEFECTO = 2, 8, 4
REPETICIONES = 20
SEMILLA = 42
NOMBRES_K4 = {1: "Frecuentes de alto valor", 2: "Regulares", 3: "Recientes de bajo gasto", 4: "Dormidos"}


def validar_k(texto):
    """Número de grupos: entero entre 2 y 8."""
    try:
        k = int(str(texto).strip())
    except ValueError:
        raise ErrorValidacion(
            f"El número de grupos debe ser un entero entre {K_MINIMO} y {K_MAXIMO}; recibí «{texto}».")
    if not K_MINIMO <= k <= K_MAXIMO:
        raise ErrorValidacion(f"El número de grupos debe estar entre {K_MINIMO} y {K_MAXIMO}; recibí {k}.")
    return k


def variables(clientes):
    """Matriz n x 3 con log(1 + R), log(1 + F), log(1 + M)."""
    return np.log1p(np.array([[c["recencia_dias"], c["frecuencia"], c["valor_total"]] for c in clientes],
                             dtype=float).reshape(-1, 3))


class Modelo:
    """Estandarizador + centroides ya renumerados. Se guarda como JSON en la base."""

    def __init__(self, k, media, escala, centroides, nombres, silueta=None, davies_bouldin=None,
                 origen="", fecha=None):
        self.k = int(k)
        self.media = np.asarray(media, dtype=float)
        self.escala = np.asarray(escala, dtype=float)
        self.centroides = np.asarray(centroides, dtype=float)
        self.nombres = {int(g): str(n) for g, n in nombres.items()}
        self.silueta = silueta
        self.davies_bouldin = davies_bouldin
        self.origen = origen
        self.fecha = fecha or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def estandarizar(self, clientes):
        return (variables(clientes) - self.media) / self.escala

    def asignar(self, clientes):
        """Grupo (1..k) del centroide más cercano para cada cliente."""
        z = self.estandarizar(clientes)
        distancias = ((z[:, None, :] - self.centroides[None, :, :]) ** 2).sum(axis=2)
        return distancias.argmin(axis=1) + 1

    def nombre(self, grupo):
        return self.nombres.get(int(grupo), f"Grupo {grupo}")

    def etiqueta(self, grupo):
        """«1. Frecuentes de alto valor», o solo «Grupo 5» cuando el grupo no tiene nombre propio."""
        nombre = self.nombre(grupo)
        return nombre if nombre == f"Grupo {grupo}" else f"{grupo}. {nombre}"

    def a_dict(self):
        return {"k": self.k, "media": self.media.tolist(), "escala": self.escala.tolist(),
                "centroides": self.centroides.tolist(), "nombres": {str(g): n for g, n in self.nombres.items()},
                "silueta": self.silueta, "davies_bouldin": self.davies_bouldin,
                "origen": self.origen, "fecha": self.fecha}

    @classmethod
    def desde_dict(cls, d):
        return cls(d["k"], d["media"], d["escala"], d["centroides"], d["nombres"], d.get("silueta"),
                   d.get("davies_bouldin"), d.get("origen", ""), d.get("fecha"))


def _revisar_cantidad(clientes, k):
    if len(clientes) < k:
        raise ErrorValidacion(f"Para formar {k} grupos se necesitan al menos {k} clientes; hay {len(clientes)}.")
    distintos = len({(c["recencia_dias"], c["frecuencia"], round(c["valor_total"], 2)) for c in clientes})
    if distintos < k:
        raise ErrorValidacion(f"Solo hay {distintos} clientes distintos entre sí; no alcanzan para {k} grupos.")


def _metricas(z, grupos):
    from sklearn.metrics import davies_bouldin_score, silhouette_score
    if len(set(grupos.tolist())) < 2:
        return None, None
    return round(float(silhouette_score(z, grupos)), 4), round(float(davies_bouldin_score(z, grupos)), 4)


def entrenar(clientes, k):
    """Corre K-means con la receta del análisis. Devuelve (modelo, grupos en el orden de `clientes`)."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    k = validar_k(k)
    _revisar_cantidad(clientes, k)
    x = variables(clientes)
    escalador = StandardScaler().fit(x)
    z = escalador.transform(x)
    km = KMeans(n_clusters=k, n_init=REPETICIONES, random_state=SEMILLA).fit(z)
    valor = np.array([c["valor_total"] for c in clientes])
    medias = [valor[km.labels_ == e].mean() for e in range(k)]
    orden = np.argsort(medias)[::-1]                     # etiqueta de K-means, de mayor a menor valor medio
    nuevo = np.empty(k, dtype=int)
    nuevo[orden] = np.arange(1, k + 1)
    grupos = nuevo[km.labels_]
    silueta, db = _metricas(z, grupos)
    modelo = Modelo(k, escalador.mean_, escalador.scale_, km.cluster_centers_[orden],
                    nombrar(clientes, grupos, k), silueta, db, origen="Recalculado en el programa")
    return modelo, grupos


def desde_grupos(clientes, grupos, nombres=None, origen="Análisis de la Fase 4"):
    """Arma el modelo a partir de grupos ya conocidos (los del análisis que trae el CSV inicial).

    En K-means cada centroide es el promedio de sus clientes, así que basta con
    promediar los datos estandarizados de cada grupo para recuperar los centroides
    del análisis sin volver a entrenar.
    """
    grupos = np.asarray(grupos, dtype=int)
    k = int(grupos.max())
    if sorted(set(grupos.tolist())) != list(range(1, k + 1)):
        raise ErrorValidacion("Los grupos del archivo deben ir numerados de 1 en adelante, sin saltos.")
    x = variables(clientes)
    media, escala = x.mean(axis=0), x.std(axis=0)
    escala[escala == 0] = 1.0
    z = (x - media) / escala
    centroides = np.array([z[grupos == g].mean(axis=0) for g in range(1, k + 1)])
    silueta, db = _metricas(z, grupos)
    return Modelo(k, media, escala, centroides, nombres or nombrar(clientes, grupos, k), silueta, db, origen=origen)


def nombrar(clientes, grupos, k):
    """Nombres de los grupos. Solo con k = 4 y cuando el perfil de verdad coincide se usan los
    nombres del análisis; en cualquier otro caso cada grupo se llama «Grupo N».

    El perfil coincide si el grupo 1 tiene la frecuencia mediana más alta y, entre los dos de
    menor valor (3 y 4), el 4 lleva más días sin comprar (más de 90, inactivo) y el 3 compró
    hace poco (90 días o menos).
    """
    genericos = {g: f"Grupo {g}" for g in range(1, k + 1)}
    if k != 4:
        return genericos
    grupos = np.asarray(grupos)
    recencia = np.array([c["recencia_dias"] for c in clientes], dtype=float)
    frecuencia = np.array([c["frecuencia"] for c in clientes], dtype=float)
    r = {g: np.median(recencia[grupos == g]) for g in range(1, 5)}
    f = {g: np.median(frecuencia[grupos == g]) for g in range(1, 5)}
    coincide = (f[1] == max(f.values())
                and r[4] > r[3]
                and r[4] > UMBRAL_ACTIVO >= r[3])
    return dict(NOMBRES_K4) if coincide else genericos


def perfil(clientes, grupos, modelo):
    """Tamaño y medianas de recencia, frecuencia y valor por grupo, más su peso en clientes y en valor."""
    grupos = np.asarray(grupos, dtype=int)
    n = len(clientes)
    recencia = np.array([c["recencia_dias"] for c in clientes], dtype=float)
    frecuencia = np.array([c["frecuencia"] for c in clientes], dtype=float)
    valor = np.array([c["valor_total"] for c in clientes], dtype=float)
    total_valor = valor.sum()
    filas = []
    for g in range(1, modelo.k + 1):
        m = grupos == g
        cuantos = int(m.sum())
        filas.append({
            "grupo": g, "nombre": modelo.nombre(g), "clientes": cuantos,
            "pct_clientes": 100 * cuantos / n if n else 0.0,
            "pct_valor": 100 * valor[m].sum() / total_valor if total_valor else 0.0,
            "recencia_mediana": float(np.median(recencia[m])) if cuantos else None,
            "frecuencia_mediana": float(np.median(frecuencia[m])) if cuantos else None,
            "valor_mediano": float(np.median(valor[m])) if cuantos else None,
        })
    return filas
