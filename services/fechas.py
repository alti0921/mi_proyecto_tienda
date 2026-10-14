"""Módulo de utilidades de fecha y hora para la aplicación.

La base de datos SQLite guarda marcas de tiempo en UTC (mediante CURRENT_TIMESTAMP);
la conversión a hora local es únicamente para fines de presentación en interfaz de usuario y reportes.
"""

from datetime import datetime, timezone
from typing import Optional


def a_hora_local(fecha_utc: Optional[str]) -> str:
    """Convierte una fecha/hora en UTC (como las guardadas por SQLite con CURRENT_TIMESTAMP)
    a la zona horaria local del sistema operativo.

    Acepta formato 'YYYY-MM-DD HH:MM:SS', con 'T' en lugar del espacio y fracciones de segundo.
    La base de datos guarda marcas de tiempo en UTC; la conversión es solo para mostrar.

    Retorna:
    - '--' si fecha_utc es None o cadena vacía.
    - La fecha/hora formateada como 'YYYY-MM-DD HH:MM:SS' en hora local.
    - La cadena original sin error si no se puede interpretar.
    """
    if fecha_utc is None or fecha_utc == "":
        return "--"

    try:
        if isinstance(fecha_utc, datetime):
            dt = fecha_utc
        elif isinstance(fecha_utc, str):
            dt = datetime.fromisoformat(fecha_utc)
        else:
            return str(fecha_utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(fecha_utc) if fecha_utc is not None else "--"
