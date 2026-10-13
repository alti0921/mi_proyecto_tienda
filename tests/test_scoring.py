import sqlite3
import pytest
import os
from services import (
    calcular_v1_1,
    calcular_score,
    calcular_sw1,
    calcular_sw2,
    calcular_sw3,
    aplicar_matriz_decision,
    evaluar_cold_start,
    registrar_snapshot,
    calcular_mora_efectiva,
    aplicar_reglas_veto,
    decision_por_clase,
    evaluar_cliente,
)

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

        # 1. Verificación directa de V1.1 sin álgebra inversa
        assert calcular_v1_1(mora_efectiva) == v1_1_esp, (
            f"Fallo en {mora_efectiva} días de mora: "
            f"V1.1 esperado {v1_1_esp}, obtenido {calcular_v1_1(mora_efectiva)}"
        )

        # 2. Validación de integración en SW1
        assert sw1_calculado == sw1_esp, (
            f"Fallo en integración SW1 para {dias_trans} días (mora efectiva {mora_efectiva}): "
            f"SW1 esperado {sw1_esp}, obtenido {sw1_calculado}"
        )


def test_venta_credito_requiere_cliente_integrity_error(db_conn):
    """
    Verifica que la restricción CHECK (tipo_pago != 'credito' OR cliente_id IS NOT NULL)
    en la tabla ventas dispare un sqlite3.IntegrityError si se intenta registrar una
    venta a crédito sin cliente asociado (cliente_id = NULL).
    """
    cursor = db_conn.cursor()

    # 1. Intento inválido: crédito sin cliente -> Debe fallar con IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total)
            VALUES (1, NULL, 'credito', 5000.0)
        """)

    # 2. Ventas válidas: efectivo sin cliente y crédito con cliente deben operar con normalidad
    cursor.execute("""
        INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total)
        VALUES (1, NULL, 'efectivo', 3000.0)
    """)
    assert cursor.lastrowid is not None

    cursor.execute("""
        INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total)
        VALUES (1, 1, 'credito', 4000.0)
    """)
    assert cursor.lastrowid is not None


# ============================================================================
# NUEVOS TESTS - MATRIZ DE SCORING V2.0 (REGLAS DE VETO Y REFERENCIA FIFO)
# ============================================================================

@pytest.mark.parametrize("clase,mora,esperado", [
    ("A", 6, ("A", None)),
    ("A", 7, ("C", "R1")),
    ("B", 10, ("C", "R1")),
    ("C", 8, ("C", None)),
    ("D", 9, ("D", None)),
    ("A", 11, ("D", "R2")),
    ("C", 15, ("D", "R2")),
    ("D", 11, ("D", None)),
])
def test_aplicar_reglas_veto_tabla(clase, mora, esperado):
    assert aplicar_reglas_veto(clase, mora) == esperado


def test_aplicar_reglas_veto_errores():
    with pytest.raises(ValueError):
        aplicar_reglas_veto("X", 0)
    with pytest.raises(ValueError):
        aplicar_reglas_veto("A", -1)


def test_mora_fifo_ignora_cargo_antiguo_pagado(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente FIFO 1', 100000.0, 20000.0, 60, 'B', 'registro_completo')
    """)
    cid = cursor.lastrowid
    # Cargo de 50.000 hace 60 días
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 50000.0, 50000.0, datetime('now', '-60 days'))
    """, (cid,))
    # Abono de 50.000 hace 55 días
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'abono', 50000.0, 0.0, datetime('now', '-55 days'))
    """, (cid,))
    # Cargo de 20.000 hace 3 días
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 20000.0, 20000.0, datetime('now', '-3 days'))
    """, (cid,))
    db_conn.commit()

    assert calcular_mora_efectiva(cid, db_conn) == 0
    assert calcular_sw1(cid, db_conn) == 100.0


def test_mora_fifo_abono_parcial(db_conn):
    cursor = db_conn.cursor()

    # Cliente 1: cargo 30k hace 20d, cargo 30k hace 5d, abono 30k hace 2d -> saldo 30k, mora 0
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente FIFO Parcial 1', 100000.0, 30000.0, 60, 'B', 'registro_completo')
    """)
    cid1 = cursor.lastrowid
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 30000.0, 30000.0, datetime('now', '-20 days'))
    """, (cid1,))
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 30000.0, 60000.0, datetime('now', '-5 days'))
    """, (cid1,))
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'abono', 30000.0, 30000.0, datetime('now', '-2 days'))
    """, (cid1,))

    # Cliente 2: cargo 30k hace 20d, cargo 30k hace 5d, abono 20k hace 2d -> saldo 40k, mora 12
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente FIFO Parcial 2', 100000.0, 40000.0, 60, 'B', 'registro_completo')
    """)
    cid2 = cursor.lastrowid
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 30000.0, 30000.0, datetime('now', '-20 days'))
    """, (cid2,))
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 30000.0, 60000.0, datetime('now', '-5 days'))
    """, (cid2,))
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'abono', 20000.0, 40000.0, datetime('now', '-2 days'))
    """, (cid2,))

    db_conn.commit()

    assert calcular_mora_efectiva(cid1, db_conn) == 0
    assert calcular_mora_efectiva(cid2, db_conn) == 12


def _crear_cliente_matriz(conn, nombre, dias_cargo_pendiente):
    cursor = conn.cursor()
    saldo_inicial = 20000.0 if dias_cargo_pendiente is not None else 0.0
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES (?, 500000.0, ?, 60, 'B', 'conocido_referido')
    """, (nombre, saldo_inicial))
    cid = cursor.lastrowid

    # Producto canasta básica
    cursor.execute("""
        INSERT INTO productos (nombre, categoria, precio_venta, costo, stock, stock_minimo)
        VALUES (?, 'canasta_basica', 1000.0, 700.0, 100, 10)
    """, (f"Prod Canasta {cid}",))
    pid = cursor.lastrowid

    # 8 ventas en efectivo con usuario_id = 1, fechadas hace 1 a 8 días
    for d in range(1, 9):
        cursor.execute(f"""
            INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total, monto_pagado, fecha_venta)
            VALUES (1, ?, 'efectivo', 1000.0, 1000.0, datetime('now', '-{d} days'))
        """, (cid,))
        vid = cursor.lastrowid
        cursor.execute("""
            INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, 'Item Canasta', 1.0, 1000.0, 1000.0)
        """, (vid, pid))

    # 3 ciclos ya pagados cronológicamente
    ciclos = [
        (60, 58),
        (45, 43),
        (35, 33),
    ]
    for d_cargo, d_abono in ciclos:
        cursor.execute(f"""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
            VALUES (?, 'cargo', 10000.0, 10000.0, datetime('now', '-{d_cargo} days'))
        """, (cid,))
        cursor.execute(f"""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
            VALUES (?, 'abono', 10000.0, 0.0, datetime('now', '-{d_abono} days'))
        """, (cid,))

    if dias_cargo_pendiente is not None:
        cursor.execute(f"""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
            VALUES (?, 'cargo', 20000.0, 20000.0, datetime('now', '-{dias_cargo_pendiente} days'))
        """, (cid,))

    conn.commit()
    return cid


def test_matriz_v2_caso_1_al_dia(db_conn):
    cid = _crear_cliente_matriz(db_conn, "Caso 1 Al Día", None)
    eval_res = evaluar_cliente(cid, db_conn)
    score, clase_final = calcular_score(cid, db_conn)

    assert eval_res["es_cold_start"] is False
    assert eval_res["score"] == pytest.approx(85.625, abs=0.01)
    assert eval_res["sw1"] == 100.0
    assert eval_res["clase_puntaje"] == "A"
    assert eval_res["clase_final"] == "A"
    assert eval_res["veto_aplicado"] is None
    assert eval_res["dias_mora_efectiva"] == 0
    assert calcular_sw2(cid, db_conn) == 87.5
    assert calcular_sw3(cid, db_conn) == 60.0
    assert clase_final == "A"


def test_matriz_v2_caso_2_preventiva(db_conn):
    cid = _crear_cliente_matriz(db_conn, "Caso 2 Preventiva", 13)
    eval_res = evaluar_cliente(cid, db_conn)
    score, clase_final = calcular_score(cid, db_conn)

    assert eval_res["es_cold_start"] is False
    assert eval_res["score"] == pytest.approx(78.425, abs=0.01)
    assert eval_res["sw1"] == 82.0
    assert eval_res["clase_puntaje"] == "B"
    assert eval_res["clase_final"] == "B"
    assert eval_res["veto_aplicado"] is None
    assert eval_res["dias_mora_efectiva"] == 5
    assert calcular_sw2(cid, db_conn) == 87.5
    assert calcular_sw3(cid, db_conn) == 60.0
    assert clase_final == "B"


def test_matriz_v2_caso_3_veto_r1(db_conn):
    cid = _crear_cliente_matriz(db_conn, "Caso 3 Veto R1", 16)
    eval_res = evaluar_cliente(cid, db_conn)
    score, clase_final = calcular_score(cid, db_conn)

    assert eval_res["es_cold_start"] is False
    assert eval_res["score"] == pytest.approx(68.825, abs=0.01)
    assert eval_res["sw1"] == 58.0
    assert eval_res["clase_puntaje"] == "B"
    assert eval_res["clase_final"] == "C"
    assert eval_res["veto_aplicado"] == "R1"
    assert eval_res["dias_mora_efectiva"] == 8
    assert calcular_sw2(cid, db_conn) == 87.5
    assert calcular_sw3(cid, db_conn) == 60.0
    assert clase_final == "C"


def test_matriz_v2_caso_4_veto_r2(db_conn):
    cid = _crear_cliente_matriz(db_conn, "Caso 4 Veto R2", 23)
    eval_res = evaluar_cliente(cid, db_conn)
    score, clase_final = calcular_score(cid, db_conn)

    assert eval_res["es_cold_start"] is False
    assert eval_res["score"] == pytest.approx(61.625, abs=0.01)
    assert eval_res["sw1"] == 40.0
    assert eval_res["clase_puntaje"] == "B"
    assert eval_res["clase_final"] == "D"
    assert eval_res["veto_aplicado"] == "R2"
    assert eval_res["dias_mora_efectiva"] == 15
    assert calcular_sw2(cid, db_conn) == 87.5
    assert calcular_sw3(cid, db_conn) == 60.0
    assert clase_final == "D"


def test_matriz_v2_caso_5_cold_start_solo_apodo(db_conn):
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente ColdStart Apodo', 0.0, 0.0, 60, 'B', 'solo_apodo')
    """)
    cid = cursor.lastrowid
    db_conn.commit()

    eval_res = evaluar_cliente(cid, db_conn)
    assert eval_res["es_cold_start"] is True
    assert eval_res["clase_final"] == "C"
    assert eval_res["veto_aplicado"] is None
    assert eval_res["cold_start"] is not None
    assert eval_res["cold_start"]["cupo_semilla"] == 30000.0


def test_evaluar_cliente_incluye_dias_transcurridos(db_conn, crear_cliente_score_alto):
    """Verifica que evaluar_cliente incluya 'dias_transcurridos' en cold-start y no-cold-start."""
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente CS Dias', 0.0, 0.0, 60, 'B', 'solo_apodo')
    """)
    cid_cs = cursor.lastrowid
    db_conn.commit()

    res_cs = evaluar_cliente(cid_cs, db_conn)
    assert res_cs["es_cold_start"] is True
    assert "dias_transcurridos" in res_cs
    assert res_cs["dias_transcurridos"] == 0

    cid_alto = crear_cliente_score_alto(db_conn, dias_cargo_pendiente=16)
    res_alto = evaluar_cliente(cid_alto, db_conn)
    assert res_alto["es_cold_start"] is False
    assert "dias_transcurridos" in res_alto
    assert res_alto["dias_transcurridos"] == 16
    assert res_alto["dias_mora_efectiva"] == 8
    assert res_alto["score"] == pytest.approx(83.2, abs=0.01)
    assert res_alto["sw1"] == 58.0
    assert res_alto["sw2"] == 100.0
    assert res_alto["sw3"] == 100.0
    assert res_alto["clase_puntaje"] == "A"
    assert res_alto["clase_final"] == "C"
    assert res_alto["veto_aplicado"] == "R1"

    cid_19 = crear_cliente_score_alto(db_conn, dias_cargo_pendiente=19)
    res_19 = evaluar_cliente(cid_19, db_conn)
    assert res_19["dias_transcurridos"] == 19
    assert res_19["dias_mora_efectiva"] == 11
    assert res_19["score"] == pytest.approx(76.0, abs=0.01)
    assert res_19["clase_puntaje"] == "B"
    assert res_19["clase_final"] == "D"
    assert res_19["veto_aplicado"] == "R2"


def test_clasificar_banda_mora_desde_scoring():
    """Verifica que clasificar_banda_mora clasifique correctamente en las 4 bandas."""
    from services.scoring_service import clasificar_banda_mora as cbm_scoring
    from services import clasificar_banda_mora as cbm_services

    assert cbm_scoring is cbm_services

    assert cbm_scoring(0) == ("vigente_0_3", "Cartera Vigente (0 a 3 días)")
    assert cbm_scoring(3) == ("vigente_0_3", "Cartera Vigente (0 a 3 días)")
    assert cbm_scoring(4) == ("preventiva_4_6", "Alerta Preventiva (4 a 6 días)")
    assert cbm_scoring(6) == ("preventiva_4_6", "Alerta Preventiva (4 a 6 días)")
    assert cbm_scoring(7) == ("congelada_7_10", "Cartera Congelada (7 a 10 días)")
    assert cbm_scoring(10) == ("congelada_7_10", "Cartera Congelada (7 a 10 días)")
    assert cbm_scoring(11) == ("critica_mas_10", "Cartera Crítica (> 10 días)")


def test_schema_plazo_por_defecto_y_check(db_conn):
    """Verifica que el schema aplique DEFAULT 8 y CHECK (plazo_pactado_dias IN (8, 15))."""
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Default Plazo', 1000.0, 0.0, 60, 'B', 'solo_apodo')
    """)
    cid = cursor.lastrowid
    db_conn.commit()

    cursor.execute("SELECT plazo_pactado_dias FROM clientes WHERE id = ?", (cid,))
    assert cursor.fetchone()["plazo_pactado_dias"] == 8

    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("""
            INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo, plazo_pactado_dias)
            VALUES ('Cliente Plazo Invalido', 1000.0, 0.0, 60, 'B', 'solo_apodo', 10)
        """)


def test_mora_efectiva_usa_plazo_del_cliente(db_conn, crear_cliente_score_alto):
    """
    Verifica que calcular_mora_efectiva descuente el plazo específico del cliente (8 o 15 días).
    Cargo pendiente de hace 16 días:
    - Con plazo 8 -> mora 8 días, clase_final C, veto R1.
    - Con plazo 15 -> mora 1 día, sw1 100, clase_final A, veto None.
    """
    cid_8 = crear_cliente_score_alto(db_conn, dias_cargo_pendiente=16)
    cid_15 = crear_cliente_score_alto(db_conn, dias_cargo_pendiente=16)

    db_conn.execute("UPDATE clientes SET plazo_pactado_dias = 15 WHERE id = ?", (cid_15,))
    db_conn.commit()

    # Cliente con plazo 8
    res_8 = evaluar_cliente(cid_8, db_conn)
    assert res_8["dias_mora_efectiva"] == 8
    assert res_8["clase_final"] == "C"
    assert res_8["veto_aplicado"] == "R1"

    # Cliente con plazo 15
    res_15 = evaluar_cliente(cid_15, db_conn)
    assert res_15["dias_mora_efectiva"] == 1
    assert res_15["sw1"] == 100.0
    assert res_15["clase_final"] == "A"
    assert res_15["veto_aplicado"] is None


def test_cliente_quincenal_que_paga_el_dia_15_no_queda_en_mora(db_conn, crear_cliente_score_alto):
    """Verifica que un cliente quincenal con cargo de 15 días tenga mora 0 (Matriz v2 §3.1)."""
    cid = crear_cliente_score_alto(db_conn, dias_cargo_pendiente=15)
    db_conn.execute("UPDATE clientes SET plazo_pactado_dias = 15 WHERE id = ?", (cid,))
    db_conn.commit()

    assert calcular_mora_efectiva(cid, db_conn) == 0
    res = evaluar_cliente(cid, db_conn)
    assert res["dias_mora_efectiva"] == 0
    assert res["veto_aplicado"] is None


