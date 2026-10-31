"""Reglas de validación de un cliente.

Es el único lugar donde se decide si un dato entra o no. La ventana, la
importación de CSV y la autoprueba llaman a estas funciones, así que una regla
nunca queda escrita dos veces. Cada mensaje de error está redactado para
mostrárselo al usuario tal cual.
"""
import re
import unicodedata

LARGO_CODIGO = 20
LARGO_PAIS = 40
RECENCIA_MAXIMA = 3650   # diez años; más que eso ya no es un cliente de la tienda
UMBRAL_ACTIVO = 90       # días: hasta 90 desde la última compra el cliente se considera activo
PAISES_REINO_UNIDO = {"united kingdom", "reino unido", "uk", "u.k."}


class ErrorValidacion(ValueError):
    """Dato rechazado. El mensaje está escrito para mostrárselo al usuario tal cual."""


def clave_de(texto):
    """Llave para comparar textos: sin tildes, sin mayúsculas y sin espacios de más."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _limpio(texto):
    return re.sub(r"\s+", " ", str(texto if texto is not None else "")).strip()


def validar_codigo(texto):
    """Código del cliente: obligatorio, letras, números o guiones, máximo 20 caracteres."""
    codigo = _limpio(texto)
    if not codigo:
        raise ErrorValidacion("Escriba el código del cliente.")
    if not re.fullmatch(rf"[A-Za-z0-9-]{{1,{LARGO_CODIGO}}}", codigo):
        raise ErrorValidacion(
            f"El código del cliente admite solo letras, números y guiones, máximo {LARGO_CODIGO}; recibí «{codigo}».")
    return codigo


def validar_pais(texto, conocidos=()):
    """País: obligatorio. Si coincide con uno que ya existe (sin mirar tildes ni mayúsculas),
    se usa la forma ya guardada para que un mismo país no aparezca dos veces en las gráficas."""
    pais = _limpio(texto)
    if not pais:
        raise ErrorValidacion("Escriba el país del cliente.")
    if len(pais) > LARGO_PAIS:
        raise ErrorValidacion(f"El país tiene {len(pais)} caracteres; el máximo es {LARGO_PAIS}.")
    if re.fullmatch(r"[\d\s.,-]+", pais):
        raise ErrorValidacion("El país no puede ser un número.")
    for existente in conocidos:
        if clave_de(existente) == clave_de(pais):
            return existente
    return pais


def validar_entero(texto, campo, minimo, maximo=None, opcional=False):
    """Convierte a entero y revisa el rango. `campo` va con artículo: «La recencia»."""
    if isinstance(texto, bool):
        raise ErrorValidacion(f"{campo} debe ser un número entero.")
    if isinstance(texto, int):
        valor = texto
    else:
        limpio = _limpio(texto)
        if not limpio:
            if opcional:
                return 0
            raise ErrorValidacion(f"Falta {campo[0].lower() + campo[1:]}.")
        if re.fullmatch(r"-?\d+[.,]\d+", limpio):
            raise ErrorValidacion(f"{campo} debe ser un número entero, sin decimales; recibí «{limpio}».")
        if not re.fullmatch(r"-?\d+", limpio):
            raise ErrorValidacion(f"{campo} debe ser un número entero; recibí «{limpio}».")
        valor = int(limpio)
    if valor < minimo:
        raise ErrorValidacion(f"{campo} debe ser un número entero mayor o igual a {minimo}; recibí «{valor}».")
    if maximo is not None and valor > maximo:
        raise ErrorValidacion(f"{campo} no puede pasar de {maximo}; recibí «{valor}».")
    return valor


def leer_decimal(texto):
    """Lee un número escrito con coma o punto decimal: 1250,5 · 1250.5 · 1.250,50 · 1,250.50.

    Si trae los dos signos, el último es el decimal y el otro separa miles.
    Devuelve None si no es un número.
    """
    limpio = _limpio(texto).replace(" ", "").replace("£", "")
    if "," in limpio and "." in limpio:
        decimal = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        miles = "." if decimal == "," else ","
        limpio = limpio.replace(miles, "").replace(decimal, ".")
    elif limpio.count(",") == 1:
        limpio = limpio.replace(",", ".")
    elif limpio.count(",") > 1 or limpio.count(".") > 1:
        limpio = limpio.replace(",", "").replace(".", "")  # 1.234.567 o 1,234,567: solo miles
    if not re.fullmatch(r"-?\d+(\.\d+)?", limpio):
        return None
    return float(limpio)


def validar_valor(texto, campo="El valor total"):
    """Número mayor que cero, con coma o punto decimal. Se guarda con dos decimales."""
    if isinstance(texto, bool):
        raise ErrorValidacion(f"{campo} debe ser un número.")
    if isinstance(texto, (int, float)):
        valor = float(texto)
        crudo = texto
    else:
        crudo = _limpio(texto)
        if not crudo:
            raise ErrorValidacion(f"Falta {campo[0].lower() + campo[1:]}.")
        valor = leer_decimal(crudo)
        if valor is None:
            raise ErrorValidacion(f"{campo} debe ser un número, por ejemplo 1250,50; recibí «{crudo}».")
    if not valor > 0:
        raise ErrorValidacion(f"{campo} debe ser mayor que 0; recibí «{crudo}».")
    return round(valor, 2)


def mercado_de(pais):
    """Reino Unido o Internacional, según el país."""
    return "Reino Unido" if clave_de(pais) in PAISES_REINO_UNIDO else "Internacional"


def estado_de(recencia_dias):
    """Activo si compró en los últimos 90 días; si no, Inactivo."""
    return "Activo" if recencia_dias <= UMBRAL_ACTIVO else "Inactivo"


def validar_cliente(datos, paises_conocidos=()):
    """Valida un cliente completo y calcula lo que no se digita.

    `datos` trae los textos del formulario (o de una fila de CSV) con las llaves
    cliente, pais, recencia_dias, frecuencia, valor_total y, opcionales,
    unidades, productos_distintos y devoluciones. Devuelve el cliente listo para
    guardar, sin el grupo (ese lo pone el modelo K-means).
    """
    cliente = validar_codigo(datos.get("cliente"))
    pais = validar_pais(datos.get("pais"), paises_conocidos)
    recencia = validar_entero(datos.get("recencia_dias"), "La recencia", 0, RECENCIA_MAXIMA)
    frecuencia = validar_entero(datos.get("frecuencia"), "La frecuencia", 1)
    valor = validar_valor(datos.get("valor_total"))
    unidades = validar_entero(datos.get("unidades"), "Las unidades", 0, opcional=True)
    productos = validar_entero(datos.get("productos_distintos"), "Los productos distintos", 0, opcional=True)
    devoluciones = validar_entero(datos.get("devoluciones"), "Las devoluciones", 0, opcional=True)
    if unidades and productos > unidades:
        raise ErrorValidacion(
            f"Los productos distintos ({productos}) no pueden ser más que las unidades compradas ({unidades}).")
    return {
        "cliente": cliente,
        "pais": pais,
        "mercado": mercado_de(pais),
        "recencia_dias": recencia,
        "frecuencia": frecuencia,
        "valor_total": valor,
        "ticket_promedio": round(valor / frecuencia, 2),
        "unidades": unidades,
        "productos_distintos": productos,
        "devoluciones": devoluciones,
        "estado": estado_de(recencia),
    }
