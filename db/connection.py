import sqlite3
import os
from db.migraciones import aplicar_migraciones
from db.rutas import ruta_base_datos

DB_PATH = ruta_base_datos()

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Establece y retorna una conexión a la base de datos SQLite.
    Activa la verificación de claves foráneas y configura row_factory como sqlite3.Row.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    aplicar_migraciones(conn, db_path)
    return conn
