import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "tienda.db")

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Establece y retorna una conexión a la base de datos SQLite.
    Activa la verificación de claves foráneas y configura row_factory como sqlite3.Row.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn
