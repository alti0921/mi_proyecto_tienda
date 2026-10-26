import re

MENSAJE_ERROR_MONTO = "Escriba el valor con números, por ejemplo 2500 o 2.500."

_PATRON_PUNTO_MILES = re.compile(r"^\d{1,3}(\.\d{3})+(,\d{1,2})?$")
_PATRON_COMA_MILES = re.compile(r"^\d{1,3}(,\d{3})+$")
_PATRON_SIN_MILES_COMA = re.compile(r"^\d+(,\d{1,2})?$")
_PATRON_PUNTO_DECIMAL = re.compile(r"^\d+(\.\d{1,2})?$")


def leer_monto(texto: str) -> float:
    """
    Convierte una representación en texto de un monto monetario a float.
    Soporta formato colombiano con punto de miles y coma decimal opcional,
    coma de miles, enteros simples y decimales con punto o coma.

    Reglas (en orden, tras remover espacios y símbolo '$'):
      1. Vacío -> ValueError
      2. ^\\d{1,3}(\\.\\d{3})+(,\\d{1,2})?$ -> punto de miles (ej: "50.000", "2.500,50")
      3. ^\\d{1,3}(,\\d{3})+$             -> coma de miles (ej: "50,000")
      4. ^\\d+(,\\d{1,2})?$               -> sin miles, coma decimal opcional (ej: "2500", "2500,5")
      5. ^\\d+(\\.\\d{1,2})?$              -> punto decimal (ej: "2.5", "0.50")
      6. Cualquier otro formato            -> ValueError
    """
    s = str(texto).strip().replace("$", "").strip()
    if not s:
        raise ValueError(MENSAJE_ERROR_MONTO)

    if _PATRON_PUNTO_MILES.match(s):
        return float(s.replace(".", "").replace(",", "."))

    if _PATRON_COMA_MILES.match(s):
        return float(s.replace(",", ""))

    if _PATRON_SIN_MILES_COMA.match(s):
        return float(s.replace(",", "."))

    if _PATRON_PUNTO_DECIMAL.match(s):
        return float(s)

    raise ValueError(MENSAJE_ERROR_MONTO)
