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


@pytest.fixture
def crear_cliente_score_alto():
    """
    Crea un cliente con perfil crediticio naturalmente alto (puntaje base > 80, Clase A o B),
    con o sin saldo pendiente.
    Permite parametrizar la antigüedad del cargo pendiente para probar las reglas de veto.

    Uso:
        cid = crear_cliente_score_alto(conn)                      # Sin deuda -> Clase A
        cid = crear_cliente_score_alto(conn, dias_cargo_pendiente=16) # Veto R1 -> Clase C
        cid = crear_cliente_score_alto(conn, dias_cargo_pendiente=19) # Veto R2 -> Clase D
    """
    def _crear(conn, dias_cargo_pendiente=None) -> int:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios ORDER BY id LIMIT 1")
        u_row = cursor.fetchone()
        if not u_row:
            raise RuntimeError("No hay usuarios en la base de datos.")
        u_id = u_row[0]

        saldo_inicial = 20000.0 if dias_cargo_pendiente is not None else 0.0
        cursor.execute("""
            INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
            VALUES (?, 500000.0, ?, 60, 'B', 'registro_completo')
        """, (f"Cliente Alto {dias_cargo_pendiente}", saldo_inicial))
        cid = cursor.lastrowid

        cursor.execute("""
            INSERT INTO productos (nombre, categoria, precio_venta, costo, stock, stock_minimo)
            VALUES (?, 'canasta_basica', 1000.0, 700.0, 1000, 10)
        """, (f"Prod Alto {cid}",))
        pid = cursor.lastrowid

        for d in range(1, 13):
            cursor.execute(f"""
                INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total, monto_pagado, fecha_venta)
                VALUES (?, ?, 'efectivo', 1000.0, 1000.0, datetime('now', '-{d} days'))
            """, (u_id, cid))
            vid = cursor.lastrowid
            cursor.execute("""
                INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, 'Item Alto', 1.0, 1000.0, 1000.0)
            """, (vid, pid))

        ciclos = [(60, 58), (45, 43), (35, 33)]
        for d_c, d_a in ciclos:
            cursor.execute(f"""
                INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
                VALUES (?, 'cargo', 10000.0, 10000.0, datetime('now', '-{d_c} days'))
            """, (cid,))
            cursor.execute(f"""
                INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
                VALUES (?, 'abono', 10000.0, 0.0, datetime('now', '-{d_a} days'))
            """, (cid,))

        if dias_cargo_pendiente is not None:
            cursor.execute(f"""
                INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
                VALUES (?, 'cargo', 20000.0, 20000.0, datetime('now', '-{dias_cargo_pendiente} days'))
            """, (cid,))

        conn.commit()
        return cid
    return _crear
