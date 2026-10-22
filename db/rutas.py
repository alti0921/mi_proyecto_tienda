"""
Módulo de resolución de rutas para modo desarrollo y ejecutable empaquetado (PyInstaller).
Provee funciones puras sin efectos colaterales al momento de importar.
"""

import os
import sys
import tempfile


def es_ejecutable() -> bool:
    """Devuelve True si la aplicación se ejecuta empaquetada (con PyInstaller), False en desarrollo."""
    return bool(getattr(sys, "frozen", False))


def ruta_recursos(*partes: str) -> str:
    """
    Retorna la ruta absoluta a un recurso estático del proyecto.
    Si se ejecuta como empaquetado (.exe), busca en sys._MEIPASS;
    en modo desarrollo, busca a partir de la raíz del proyecto.
    """
    if es_ejecutable():
        base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, *partes)


def carpeta_datos() -> str:
    """
    Retorna la ruta absoluta al directorio donde residen los datos mutables (BD, logs, respaldos).
    - Modo ejecutable: %LOCALAPPDATA%/MiTienda (o ~/MiTienda si no está definida).
    - Modo desarrollo: carpeta db/ del proyecto.
    Crea el directorio si aún no existe.
    """
    if es_ejecutable():
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        ruta = os.path.join(base, "MiTienda")
    else:
        ruta = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db"))
    os.makedirs(ruta, exist_ok=True)
    return ruta


def ruta_base_datos() -> str:
    """Retorna la ruta absoluta al archivo tienda.db dentro de la carpeta de datos."""
    return os.path.join(carpeta_datos(), "tienda.db")


def carpeta_comprobantes() -> str:
    """
    Retorna la ruta absoluta al directorio para guardar los comprobantes PDF de cuentas por cobrar.
    - Modo ejecutable: carpeta_datos()/comprobantes.
    - Modo desarrollo: directorio temporal del sistema operativo (tempfile.gettempdir()).
    Crea el directorio si aún no existe.
    """
    if es_ejecutable():
        ruta = os.path.join(carpeta_datos(), "comprobantes")
    else:
        ruta = tempfile.gettempdir()
    os.makedirs(ruta, exist_ok=True)
    return ruta
