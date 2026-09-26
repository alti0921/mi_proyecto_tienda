import sqlite3
import pytest
import os
from services import (
    calcular_score,
    calcular_sw1,
    calcular_sw2,
    calcular_sw3,
    aplicar_matriz_decision,
    evaluar_cold_start,
    registrar_snapshot,
)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")

@pytest.fixture
def db_conn():
    """
    Fixture que crea una base de datos SQLite en memoria e inicializa
    el esquema completo definido en db/schema.sql.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    
    yield conn
    conn.close()


def test_cliente_al_dia_riesgo_bajo(db_conn):
    """
    Escenario 1: Cliente al día (saldo_actual = 0), vínculo completo
    y compras frecuentes de canasta básica -> Score >= 60, Clase A o B.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Excelente', 2000.0, 0.0, 85, 'A', 'registro_completo')
    """)
    cliente_id = cursor.lastrowid

    # Simular 3 ciclos de abono para salir de Cold-Start
    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 100.0, 0.0)
        """, (cliente_id,))

    # Insertar producto canasta básica
    cursor.execute("""
        INSERT INTO productos (nombre, categoria, precio_venta, costo, stock, stock_minimo)
        VALUES ('Frijol Canasta', 'canasta_basica', 10.0, 7.0, 100, 10)
    """)
    prod_id = cursor.lastrowid

    # Simular 14 ventas en los últimos 30 días
    for _ in range(14):
        cursor.execute("""
            INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total, monto_pagado)
            VALUES (1, ?, 'efectivo', 10.0, 10.0)
        """, (cliente_id,))
        venta_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, 'Frijol Canasta', 1.0, 10.0, 10.0)
        """, (venta_id, prod_id))

    db_conn.commit()

    score, cat_riesgo = calcular_score(cliente_id, db_conn)
    decision = aplicar_matriz_decision(score)

    assert score >= 60.0
    assert cat_riesgo in ("A", "B")
    assert decision["aprobado"] is True
    assert decision["bloqueado"] is False


def test_cliente_mora_activa(db_conn):
    """
    Escenario 2: Cliente con mora activa moderada (12 días de mora, fuera del plazo de gracia de 8 días)
    -> Categoría C (Congelamiento de cupo y abono 50%).
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Con Mora 12 Días', 1000.0, 400.0, 50, 'C', 'conocido_referido')
    """)
    cliente_id = cursor.lastrowid

    # Simular 3 ciclos de abono previos (fuera de Cold-Start)
    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 50.0, 400.0)
        """, (cliente_id,))

    # Registrar un cargo realizado hace 12 días
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 400.0, 400.0, datetime('now', '-12 days'))
    """, (cliente_id,))

    db_conn.commit()

    score, cat_riesgo = calcular_score(cliente_id, db_conn)
    decision = aplicar_matriz_decision(score)

    assert 40.0 <= score < 60.0
    assert cat_riesgo == "C"
    assert decision["congelado"] is True
    assert decision["abono_minimo_pct"] == 0.50
    assert decision["bloqueado"] is False


def test_cliente_cartera_critica(db_conn):
    """
    Escenario 3: Cliente con mora > 15 días -> Categoría D (Bloqueo automático / Alerta Roja).
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Mora Crítica', 800.0, 800.0, 30, 'D', 'solo_apodo')
    """)
    cliente_id = cursor.lastrowid

    # 3 ciclos de abonos previos
    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 20.0, 800.0)
        """, (cliente_id,))

    # Cargo pendiente desde hace 20 días (> 15 días de mora)
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 800.0, 800.0, datetime('now', '-20 days'))
    """, (cliente_id,))

    db_conn.commit()

    score, cat_riesgo = calcular_score(cliente_id, db_conn)
    decision = aplicar_matriz_decision(score)

    assert score < 40.0
    assert cat_riesgo == "D"
    assert decision["bloqueado"] is True
    assert decision["congelado"] is True


def test_cliente_cold_start(db_conn):
    """
    Escenario 4: Cliente nuevo sin historial previo ni mora -> Protocolo Cold-Start.
    Evalúa SW3 y asigna cupo semilla ($30.000 a $50.000 COP) a 15 días con estructura propia.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Nuevo ColdStart', 0.0, 0.0, 60, 'B', 'conocido_referido')
    """)
    cliente_id = cursor.lastrowid
    db_conn.commit()

    cs_res = evaluar_cold_start(cliente_id, db_conn)

    assert cs_res["es_cold_start"] is True
    assert 30000.0 <= cs_res["cupo_semilla"] <= 50000.0
    assert cs_res["plazo_dias"] == 15
    assert cs_res["score_semilla"] == 60.0
    assert cs_res["decision"]["nivel_riesgo"] == "Cold-Start Semilla"


def test_cliente_moroso_sin_abonos(db_conn):
    """
    Escenario 5 (Prueba de Regresión - Bug Cold-Start Indefinido):
    Cliente nuevo sin abonos (total_ciclos = 0), pero con un cargo pendiente de 15 días (> 8 días de mora).
    Debe DESACTIVAR Cold-Start y evaluarlo con el modelo general, asignando Clase C o D.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Moroso Sin Abonos', 500.0, 500.0, 60, 'B', 'solo_apodo')
    """)
    cliente_id = cursor.lastrowid

    # 0 abonos registrados, 1 cargo con 15 días de antigüedad
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 500.0, 500.0, datetime('now', '-15 days'))
    """, (cliente_id,))
    db_conn.commit()

    # 1. Verificar que Cold-Start se desactiva por mora > 8 días
    cs_res = evaluar_cold_start(cliente_id, db_conn)
    assert cs_res["es_cold_start"] is False

    # 2. Verificar que el cálculo general bloquea o congela el crédito
    score, cat_riesgo = calcular_score(cliente_id, db_conn)
    decision = aplicar_matriz_decision(score)

    assert score < 60.0
    assert cat_riesgo in ("C", "D")
    assert (decision["congelado"] is True or decision["bloqueado"] is True)


def test_registrar_snapshot_atomicidad(db_conn):
    """
    Verifica que registrar_snapshot inserte la trazabilidad en scoring_historial,
    garantice el casteo a entero (int) y actualice atómicamente la tabla clientes.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Test Snapshot', 1000.0, 0.0, 60, 'B', 'registro_completo')
    """)
    cliente_id = cursor.lastrowid
    db_conn.commit()

    snapshot = registrar_snapshot(
        cliente_id=cliente_id,
        sw1=100.0,
        sw2=80.0,
        sw3=100.0,
        score_ant=60,
        score_nuevo=93.4,  # Flotante que debe castearse a int (93)
        cat_ant="B",
        cat_nueva="A",
        motivo="Mejora por excelente historial de pago",
        conn=db_conn
    )
    db_conn.commit()

    # 1. Verificar inserción en scoring_historial
    cursor.execute("SELECT * FROM scoring_historial WHERE id = ?", (snapshot.id,))
    hist_row = cursor.fetchone()
    assert hist_row is not None
    assert hist_row["cliente_id"] == cliente_id
    assert isinstance(hist_row["score_nuevo"], int)
    assert hist_row["score_nuevo"] == 93
    assert hist_row["categoria_nueva"] == "A"
    assert hist_row["sw1"] == 100.0

    # 2. Verificar actualización atómica en la tabla clientes
    cursor.execute("SELECT score_crediticio, categoria_riesgo FROM clientes WHERE id = ?", (cliente_id,))
    cli_row = cursor.fetchone()
    assert isinstance(cli_row["score_crediticio"], int)
    assert cli_row["score_crediticio"] == 93
    assert cli_row["categoria_riesgo"] == "A"


def test_v1_1_mora_efectiva_bordes(db_conn):
    """
    Prueba de bordes específicos para la variable V1.1 (Mora Efectiva según P-Q9):
    Dado que días_mora_efectiva = max(0, días_transcurridos - 8) y V1.2 = 100 (< 30 días):
    - Días mora efectiva = 6 (14 días transcurridos - 8) -> V1.1 = 70.0 pts (SW1 = 82.0).
    - Días mora efectiva = 7 (15 días transcurridos - 8) -> V1.1 = 30.0 pts (SW1 = 58.0).
    - Días mora efectiva = 10 (18 días transcurridos - 8) -> V1.1 = 30.0 pts (SW1 = 58.0).
    - Días mora efectiva = 11 (19 días transcurridos - 8) -> V1.1 = 0.0 pts (SW1 = 40.0).
    """
    cursor = db_conn.cursor()

    casos_borde = [
        # (dias_transcurridos, mora_efectiva_esperada, v1_1_esperado, sw1_esperado)
        (14, 6, 70.0, 82.0),
        (15, 7, 30.0, 58.0),
        (18, 10, 30.0, 58.0),
        (19, 11, 0.0, 40.0),
    ]

    for dias_trans, mora_efectiva, v1_1_esp, sw1_esp in casos_borde:
        cursor.execute("""
            INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
            VALUES (?, 1000.0, 200.0, 60, 'B', 'conocido_referido')
        """, (f"Cliente Borde {dias_trans}d",))
        cid = cursor.lastrowid

        cursor.execute(f"""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
            VALUES (?, 'cargo', 200.0, 200.0, datetime('now', '-{dias_trans} days'))
        """, (cid,))
        db_conn.commit()

        sw1_calculado = calcular_sw1(cid, db_conn)

        # SW1 = 0.60 * V1.1 + 0.40 * 100.0  =>  V1.1 = (SW1 - 40.0) / 0.60
        v1_1_derivado = round((sw1_calculado - 40.0) / 0.60, 1)

        assert sw1_calculado == sw1_esp, (
            f"Fallo en {dias_trans} días (mora efectiva {mora_efectiva}): "
            f"SW1 esperado {sw1_esp}, obtenido {sw1_calculado}"
        )
        assert v1_1_derivado == v1_1_esp, (
            f"Fallo en {dias_trans} días (mora efectiva {mora_efectiva}): "
            f"V1.1 esperado {v1_1_esp}, derivado {v1_1_derivado}"
        )

