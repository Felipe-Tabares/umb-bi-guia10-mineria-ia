"""Formato de números para mostrar al usuario: punto de miles y coma decimal, como se escribe en Colombia."""


def numero(valor, decimales=0):
    """12345.678 -> «12.345,68» con dos decimales."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def libras(valor):
    """Valor en libras esterlinas sin decimales: «£ 8.450»."""
    return f"£ {numero(valor)}"
