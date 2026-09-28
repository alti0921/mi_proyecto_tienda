import sqlite3
import pytest
import os

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
SEEDS_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "seeds_test.sql")

@pytest.fixture
def db_conn():
    """
    Fixture compartida que crea una base de datos SQLite en memoria, inicializa
    el DDL puro definido en db/schema.sql y carga las semillas de prueba de db/seeds_test.sql.
    Garantiza la activación de PRAGMA foreign_keys = ON;.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    with open(SEEDS_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    
    yield conn
    conn.close()
