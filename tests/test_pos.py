import sqlite3
import pytest
from services.pos_service import (
    registrar_venta,
    asignar_limite_credito,
    LineaVentaInput,
)
from services.cxc_service import (
    crear_cliente,
    registrar_cargo,
    registrar_abono,
)
from models.venta import Venta


def test_asignar_limite_credito_exitoso_y_validaciones(db_conn):
    """
    Verifica la asignación manual de cupo de crédito por el tendero (RF-SCR-02 / RF-CXC-05).
    Rechaza cupos negativos y clientes inexistentes.
    """
    # 1. Asignación válida a cliente semilla Doña María
    cli_actualizado = asignar_limite_credito(cliente_id=1, nuevo_limite=2500.0, conn=db_conn)
    assert cli_actualizado.limite_credito == 2500.0

    cursor = db_conn.cursor()
    cursor.execute("SELECT limite_credito FROM clientes WHERE id = 1")
    assert cursor.fetchone()["limite_credito"] == 2500.0

    # 2. Rechazo de cupo negativo
    with pytest.raises(ValueError, match="El límite de crédito no puede ser negativo"):
        asignar_limite_credito(cliente_id=1, nuevo_limite=-100.0, conn=db_conn)

    # 3. Rechazo de cliente inexistente
    with pytest.raises(ValueError, match="Cliente ID 999 no encontrado"):
        asignar_limite_credito(cliente_id=999, nuevo_limite=1000.0, conn=db_conn)


def test_venta_efectivo_con_cambio_y_descuento_stock(db_conn):
    """
    Verifica una venta de contado en efectivo:
    - Descuento de stock en catálogo.
    - Registro en ventas y venta_detalle.
    - Cálculo de vuelto/cambio correcto (propiedad monto_cambio).
    """
    cursor = db_conn.cursor()
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    stock_inicial_arroz = cursor.fetchone()["stock"]  # 100

    items = [
        LineaVentaInput(producto_id=1, cantidad=2.0, precio_unitario=25.0),  # Arroz: 50.0
        LineaVentaInput(producto_id=None, cantidad=1.0, precio_unitario=30.0, descripcion="Panela por libra"),
    ]
    # Total = 80.0, monto_pagado = 100.0 -> cambio = 20.0
    venta = registrar_venta(
        usuario_id=1,
        tipo_pago="efectivo",
        items=items,
        conn=db_conn,
        monto_pagado=100.0,
    )

    assert isinstance(venta, Venta)
    assert venta.id is not None
    assert venta.total == 80.0
    assert venta.monto_pagado == 100.0
    assert venta.monto_cambio == 20.0
    assert venta.tipo_pago == "efectivo"

    # Verificar stock descontado
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    assert cursor.fetchone()["stock"] == stock_inicial_arroz - 2

    # Verificar líneas de venta_detalle
    cursor.execute("SELECT * FROM venta_detalle WHERE venta_id = ?", (venta.id,))
    detalles = cursor.fetchall()
    assert len(detalles) == 2
    assert detalles[0]["producto_id"] == 1
    assert detalles[0]["subtotal"] == 50.0
    assert detalles[1]["producto_id"] is None
    assert detalles[1]["descripcion"] == "Panela por libra"
    assert detalles[1]["subtotal"] == 30.0


def test_venta_nequi_exacta(db_conn):
    """
    Verifica venta de contado liquidada por transferencia digital (Nequi):
    - No genera cambio (monto_cambio == 0.0).
    - Descuenta stock adecuadamente.
    """
    cursor = db_conn.cursor()
    cursor.execute("SELECT stock FROM productos WHERE id = 2")
    stock_inicial_aceite = cursor.fetchone()["stock"]  # 50

    items = [
        {"producto_id": 2, "cantidad": 1.0, "precio_unitario": 48.0}
    ]
    venta = registrar_venta(
        usuario_id=1,
        tipo_pago="nequi",
        items=items,
        conn=db_conn,
        monto_pagado=48.0,
    )

    assert venta.total == 48.0
    assert venta.monto_pagado == 48.0
    assert venta.monto_cambio == 0.0
    assert venta.tipo_pago == "nequi"

    cursor.execute("SELECT stock FROM productos WHERE id = 2")
    assert cursor.fetchone()["stock"] == stock_inicial_aceite - 1


def test_rechazo_venta_contado_monto_insuficiente(db_conn):
    """
    Valida la regla preventiva: en ventas de contado (efectivo o nequi),
    monto_pagado debe ser mayor o igual al total.
    """
    items = [
        LineaVentaInput(producto_id=1, cantidad=2.0, precio_unitario=25.0)  # Total 50.0
    ]

    with pytest.raises(ValueError, match="El monto pagado .* es insuficiente"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="efectivo",
            items=items,
            conn=db_conn,
            monto_pagado=40.0,
        )

    with pytest.raises(ValueError, match="El monto pagado .* es insuficiente"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="nequi",
            items=items,
            conn=db_conn,
            monto_pagado=49.99,
        )


def test_venta_credito_autorizada_clases_a_b(db_conn):
    """
    Verifica venta a crédito autorizada para un cliente en Clase A/B (Doña María):
    - Creación de cabecera ventas y líneas venta_detalle.
    - Descuento de stock en productos.
    - Creación de movimiento inmutable en cuentas_por_cobrar (tipo 'cargo').
    - Incremento del saldo_actual del cliente.
    - Registro de snapshot inmutable en scoring_historial.
    """
    cursor = db_conn.cursor()
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    stock_inicial = cursor.fetchone()["stock"]  # 100

    items = [
        LineaVentaInput(producto_id=1, cantidad=4.0, precio_unitario=25.0)  # Total: 100.0
    ]

    venta = registrar_venta(
        usuario_id=1,
        tipo_pago="credito",
        items=items,
        conn=db_conn,
        cliente_id=1,
    )

    assert venta.id is not None
    assert venta.total == 100.0
    assert venta.cliente_id == 1
    assert venta.tipo_pago == "credito"

    # Verificar stock
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    assert cursor.fetchone()["stock"] == stock_inicial - 4

    # Verificar cuentas_por_cobrar
    cursor.execute("SELECT * FROM cuentas_por_cobrar WHERE venta_id = ?", (venta.id,))
    cxc = cursor.fetchone()
    assert cxc is not None
    assert cxc["cliente_id"] == 1
    assert cxc["usuario_id"] == 1
    assert cxc["tipo_movimiento"] == "cargo"
    assert cxc["monto"] == 100.0
    assert cxc["saldo_resultante"] == 100.0

    # Verificar saldo_actual en cliente
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = 1")
    assert cursor.fetchone()["saldo_actual"] == 100.0

    # Verificar snapshot en scoring_historial
    cursor.execute("SELECT * FROM scoring_historial WHERE cliente_id = ? ORDER BY id DESC LIMIT 1", (1,))
    snap = cursor.fetchone()
    assert snap is not None
    assert snap["motivo"] == f"Venta a crédito #{venta.id}"


def test_rechazo_venta_credito_clase_d_bloqueado(db_conn):
    """
    Verifica que un cliente en Clase D (Riesgo Crítico / Mora > 10 días efectivos)
    sea bloqueado automáticamente por RF-SCR-03.
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Riesgo Crítico', 500.0, 400.0, 25, 'D', 'solo_apodo')
    """)
    cliente_id = cursor.lastrowid

    # 3 ciclos de abonos previos (no cold-start)
    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 10.0, 400.0)
        """, (cliente_id,))

    # Cargo realizado hace 20 días
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 400.0, 400.0, datetime('now', '-20 days'))
    """, (cliente_id,))
    db_conn.commit()

    items = [LineaVentaInput(producto_id=1, cantidad=1.0, precio_unitario=25.0)]

    with pytest.raises(ValueError, match="Crédito rechazado \\(RF-SCR-03\\).*Crédito bloqueado"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=cliente_id,
        )


def test_rechazo_venta_credito_clase_c_sin_abono(db_conn):
    """
    Verifica que un cliente en Clase C (Riesgo Alto / Congelado)
    sea rechazado si no ha realizado un abono previo del 50% de su saldo (RF-SCR-04).
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Congelado Sin Abono', 1000.0, 400.0, 50, 'C', 'conocido_referido')
    """)
    cliente_id = cursor.lastrowid

    # 3 ciclos previos
    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 50.0, 400.0)
        """, (cliente_id,))

    # Cargo pendiente desde hace 12 días (mora efectiva = 4 días -> Clase C)
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 400.0, 400.0, datetime('now', '-12 days'))
    """, (cliente_id,))
    db_conn.commit()

    items = [LineaVentaInput(producto_id=1, cantidad=1.0, precio_unitario=25.0)]

    with pytest.raises(ValueError, match="Crédito rechazado \\(RF-SCR-04\\).*Requiere un abono previo"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=cliente_id,
        )


def test_venta_credito_clase_c_con_abono_previo_50_pct(db_conn):
    """
    Verifica que un cliente en Clase C que realice el abono requerido del 50%
    pueda desbloquear el despacho de un nuevo fiado (RF-SCR-04).
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo)
        VALUES ('Cliente Congelado Con Abono', 1000.0, 400.0, 50, 'C', 'conocido_referido')
    """)
    cliente_id = cursor.lastrowid

    for _ in range(3):
        cursor.execute("""
            INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante)
            VALUES (?, 'abono', 50.0, 400.0)
        """, (cliente_id,))

    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 400.0, 400.0, datetime('now', '-12 days'))
    """, (cliente_id,))
    db_conn.commit()

    # El cliente abona 200.0 (50% de 400.0)
    registrar_abono(cliente_id=cliente_id, monto=200.0, conn=db_conn)

    # Ahora el despacho a crédito debe autorizarse exitosamente
    items = [LineaVentaInput(producto_id=1, cantidad=1.0, precio_unitario=25.0)]
    venta = registrar_venta(
        usuario_id=1,
        tipo_pago="credito",
        items=items,
        conn=db_conn,
        cliente_id=cliente_id,
    )

    assert venta.id is not None
    assert venta.total == 25.0
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = ?", (cliente_id,))
    assert cursor.fetchone()["saldo_actual"] == 225.0  # 200 restante + 25 nueva venta


def test_rechazo_venta_credito_cupo_excedido_y_cupo_cero(db_conn):
    """
    Verifica la salvaguarda de cupo (RF-CXC-06) en el POS:
    1. Rechazo a clientes recién creados con cupo $0.0 por defecto.
    2. Rechazo si nuevo_saldo > limite_credito.
    """
    # 1. Cliente nuevo sin cupo asignado (0.0)
    cli_cero = crear_cliente(nombre="Cliente Sin Cupo", conn=db_conn)
    items = [LineaVentaInput(producto_id=1, cantidad=1.0, precio_unitario=25.0)]

    with pytest.raises(ValueError, match="El cargo excede el límite de crédito"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=cli_cero.id,
        )

    # 2. Cliente con cupo de 100.0 pero compra de 125.0
    asignar_limite_credito(cliente_id=cli_cero.id, nuevo_limite=100.0, conn=db_conn)
    items_grande = [LineaVentaInput(producto_id=1, cantidad=5.0, precio_unitario=25.0)]  # 125.0

    with pytest.raises(ValueError, match="El cargo excede el límite de crédito"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items_grande,
            conn=db_conn,
            cliente_id=cli_cero.id,
        )


def test_rechazo_venta_credito_sin_cliente_id(db_conn):
    """Verifica que no se permita registrar ventas a crédito sin cliente asociado."""
    items = [LineaVentaInput(producto_id=1, cantidad=1.0, precio_unitario=25.0)]
    with pytest.raises(ValueError, match="Las ventas a crédito requieren asociar un cliente obligatorio"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=None,
        )


def test_atomicidad_post_cargo_fallo_en_snapshot(db_conn, monkeypatch):
    """
    Test Crítico de Atomicidad Post-Cargo solicitado por la auditoría técnica:
    Simula una excepción forzada específicamente en scoring_service.registrar_snapshot,
    la cual ocurre inmediatamente después de ejecutar cxc_service.registrar_cargo(..., auto_commit=False).
    Verifica que el rollback general del orquestador pos_service.registrar_venta
    revierta TODO:
    - Sin registros en ventas ni en venta_detalle.
    - El stock del producto no se descuenta (permanece intacto).
    - Sin registros huérfanos en cuentas_por_cobrar.
    - El saldo_actual del cliente permanece inalterado.
    - Sin registros en scoring_historial.
    """
    cursor = db_conn.cursor()
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    stock_inicial = cursor.fetchone()["stock"]  # 100

    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = 1")
    saldo_inicial = cursor.fetchone()["saldo_actual"]  # 0.0

    items = [LineaVentaInput(producto_id=1, cantidad=3.0, precio_unitario=25.0)]  # Total: 75.0

    # Inyectar fallo simulado en registrar_snapshot
    def mock_snapshot_error(*args, **kwargs):
        raise RuntimeError("Fallo forzado en snapshot tras registrar cargo CxC para prueba de atomicidad")

    monkeypatch.setattr("services.scoring_service.registrar_snapshot", mock_snapshot_error)

    # La venta a crédito debe fallar con RuntimeError
    with pytest.raises(RuntimeError, match="Fallo forzado en snapshot tras registrar cargo CxC"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=1,
        )

    # Verificación exhaustiva de atomicidad (Rollback 100% verificado)
    cursor.execute("SELECT COUNT(*) AS total FROM ventas")
    assert cursor.fetchone()["total"] == 0

    cursor.execute("SELECT COUNT(*) AS total FROM venta_detalle")
    assert cursor.fetchone()["total"] == 0

    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    assert cursor.fetchone()["stock"] == stock_inicial

    cursor.execute("SELECT COUNT(*) AS total FROM cuentas_por_cobrar")
    assert cursor.fetchone()["total"] == 0

    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = 1")
    assert cursor.fetchone()["saldo_actual"] == saldo_inicial

    cursor.execute("SELECT COUNT(*) AS total FROM scoring_historial")
    assert cursor.fetchone()["total"] == 0


def test_venta_credito_con_abono_inicial_registra_solo_saldo_pendiente(db_conn):
    """
    Verifica que en una venta a crédito con abono inicial en efectivo:
    - Se valida 0 <= monto_pagado < total.
    - Se rechaza si monto_pagado >= total (debe ser contado).
    - Se descuenta el stock completo de los productos.
    - La venta registra total completo y monto_pagado entregado.
    - CxC registra como cargo ÚNICAMENTE el saldo neto financiado (total - monto_pagado).
    - El saldo_actual del cliente se incrementa solo por el monto neto financiado.
    """
    cursor = db_conn.cursor()
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    stock_inicial = cursor.fetchone()["stock"]  # 100

    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = 1")
    saldo_inicial = cursor.fetchone()["saldo_actual"]  # 0.0

    # Total de la venta = 4 * 25.0 = 100.0
    items = [LineaVentaInput(producto_id=1, cantidad=4.0, precio_unitario=25.0)]

    # 1. Rechazo si monto_pagado < 0
    with pytest.raises(ValueError, match="El monto pagado no puede ser negativo"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=1,
            monto_pagado=-10.0,
        )

    # 2. Rechazo si monto_pagado >= total (cubre toda la venta, debe ser contado)
    with pytest.raises(ValueError, match="cubre la totalidad de la venta.*utilice un tipo de pago de contado"):
        registrar_venta(
            usuario_id=1,
            tipo_pago="credito",
            items=items,
            conn=db_conn,
            cliente_id=1,
            monto_pagado=100.0,
        )

    # 3. Venta a crédito con abono inicial de $35.0 (Financiado neto = $65.0)
    venta = registrar_venta(
        usuario_id=1,
        tipo_pago="credito",
        items=items,
        conn=db_conn,
        cliente_id=1,
        monto_pagado=35.0,
    )

    assert venta.id is not None
    assert venta.total == 100.0
    assert venta.monto_pagado == 35.0
    assert venta.tipo_pago == "credito"

    # Stock descontado por la cantidad total comprada (4 unidades)
    cursor.execute("SELECT stock FROM productos WHERE id = 1")
    assert cursor.fetchone()["stock"] == stock_inicial - 4

    # Cargo en CxC debe ser exactamente $65.0 (100.0 - 35.0), NO los $100.0
    cursor.execute("SELECT * FROM cuentas_por_cobrar WHERE venta_id = ?", (venta.id,))
    cxc = cursor.fetchone()
    assert cxc is not None
    assert cxc["usuario_id"] == 1
    assert cxc["tipo_movimiento"] == "cargo"
    assert cxc["monto"] == 65.0
    assert cxc["saldo_resultante"] == 65.0

    # Saldo del cliente debe incrementarse solo en $65.0
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = 1")
    assert cursor.fetchone()["saldo_actual"] == saldo_inicial + 65.0

