import sqlite3
import pytest
from services.cxc_service import (
    crear_cliente,
    obtener_cliente,
    registrar_cargo,
    registrar_abono,
    consultar_saldo,
    obtener_historial_cxc,
)


def test_crear_y_obtener_cliente(db_conn):
    """Verifica la creación y consulta de clientes en la base de datos."""
    cliente = crear_cliente(
        nombre="Don Pedro Gómez",
        telefono="3001234567",
        direccion="Calle 45 # 10-20",
        nivel_vinculo="conocido_referido",
        limite_credito=150000.0,
        conn=db_conn,
    )

    assert cliente.id is not None
    assert cliente.nombre == "Don Pedro Gómez"
    assert cliente.saldo_actual == 0.0
    assert cliente.nivel_vinculo == "conocido_referido"
    assert cliente.activo is True

    # Consultar cliente existente
    obtenido = obtener_cliente(cliente.id, db_conn)
    assert obtenido is not None
    assert obtenido.id == cliente.id
    assert obtenido.nombre == "Don Pedro Gómez"

    # Inexistente
    assert obtener_cliente(9999, db_conn) is None


def test_registrar_cargo_exitoso_incremento_saldo(db_conn):
    """
    Verifica que al registrar un cargo:
    1. Se inserte el registro inmutable en cuentas_por_cobrar con tipo_movimiento='cargo'.
    2. Se incremente clientes.saldo_actual atómicamente.
    """
    cliente = crear_cliente(nombre="Carmen Rodríguez", conn=db_conn)
    assert cliente.saldo_actual == 0.0

    cargo = registrar_cargo(
        cliente_id=cliente.id,
        monto=25000.0,
        conn=db_conn,
        descripcion="Compra a crédito de víveres",
    )

    assert cargo.id is not None
    assert cargo.cliente_id == cliente.id
    assert cargo.tipo_movimiento == "cargo"
    assert cargo.monto == 25000.0
    assert cargo.saldo_resultante == 25000.0

    # Verificar saldo actualizado en tabla clientes
    saldo_actual = consultar_saldo(cliente.id, db_conn)
    assert saldo_actual == 25000.0


def test_registrar_abono_exitoso_decremento_saldo(db_conn):
    """
    Verifica que al registrar un abono:
    1. Se inserte en cuentas_por_cobrar con tipo_movimiento='abono'.
    2. Se reduzca clientes.saldo_actual de manera atómica.
    """
    cliente = crear_cliente(nombre="Luis Martínez", conn=db_conn)
    registrar_cargo(cliente_id=cliente.id, monto=50000.0, conn=db_conn)

    # Abono parcial de 20.000
    abono = registrar_abono(
        cliente_id=cliente.id,
        monto=20000.0,
        conn=db_conn,
        descripcion="Abono semanal",
    )

    assert abono.id is not None
    assert abono.tipo_movimiento == "abono"
    assert abono.monto == 20000.0
    assert abono.saldo_resultante == 30000.0

    # Verificar saldo restante
    saldo_actual = consultar_saldo(cliente.id, db_conn)
    assert saldo_actual == 30000.0


def test_rechazo_abonos_monto_invalido_o_superior(db_conn):
    """
    Verifica las reglas de negocio en abonos:
    - Monto <= 0 debe ser rechazado.
    - Monto > saldo_actual debe ser rechazado para evitar saldos a favor o negativos.
    """
    cliente = crear_cliente(nombre="Marcos Peña", conn=db_conn)
    registrar_cargo(cliente_id=cliente.id, monto=15000.0, conn=db_conn)

    # Monto cero o negativo
    with pytest.raises(ValueError, match="mayor a cero"):
        registrar_abono(cliente_id=cliente.id, monto=0.0, conn=db_conn)

    with pytest.raises(ValueError, match="mayor a cero"):
        registrar_abono(cliente_id=cliente.id, monto=-500.0, conn=db_conn)

    # Monto superior al saldo pendiente
    with pytest.raises(ValueError, match="no puede ser superior al saldo pendiente"):
        registrar_abono(cliente_id=cliente.id, monto=20000.0, conn=db_conn)

    # El saldo no debió alterarse
    assert consultar_saldo(cliente.id, db_conn) == 15000.0


def test_inmutabilidad_triggers_bloquean_update_delete(db_conn):
    """
    Verifica que los triggers bloquear_edicion_cxc y bloquear_borrado_cxc
    impidan estrictamente cualquier operación UPDATE o DELETE en cuentas_por_cobrar,
    garantizando el patrón Append-Only inmutable (RNF-05 y RF-CXC-01).
    """
    cliente = crear_cliente(nombre="Ana Torres", conn=db_conn)
    cargo = registrar_cargo(cliente_id=cliente.id, monto=10000.0, conn=db_conn)

    cursor = db_conn.cursor()

    # Intento de UPDATE -> Debe ser bloqueado por el trigger
    with pytest.raises(sqlite3.DatabaseError, match="inmutable"):
        cursor.execute(
            "UPDATE cuentas_por_cobrar SET monto = 5000.0 WHERE id = ?",
            (cargo.id,),
        )

    # Intento de DELETE -> Debe ser bloqueado por el trigger
    with pytest.raises(sqlite3.DatabaseError, match="inmutable"):
        cursor.execute(
            "DELETE FROM cuentas_por_cobrar WHERE id = ?",
            (cargo.id,),
        )


def test_consultar_saldo_e_historial_cxc(db_conn):
    """
    Verifica el flujo completo de múltiples cargos y abonos,
    la consulta de saldo y la recuperación cronológica del historial.
    """
    cliente = crear_cliente(nombre="Sofía Herrera", conn=db_conn)

    # Cargo 1: 30.000 (saldo 30.000)
    registrar_cargo(cliente.id, 30000.0, db_conn, descripcion="Cargo 1")
    # Cargo 2: 15.000 (saldo 45.000)
    registrar_cargo(cliente.id, 15000.0, db_conn, descripcion="Cargo 2")
    # Abono 1: 10.000 (saldo 35.000)
    registrar_abono(cliente.id, 10000.0, db_conn, descripcion="Abono 1")

    assert consultar_saldo(cliente.id, db_conn) == 35000.0

    historial = obtener_historial_cxc(cliente.id, db_conn)
    assert len(historial) == 3
    assert historial[0].tipo_movimiento == "cargo"
    assert historial[0].monto == 30000.0
    assert historial[0].saldo_resultante == 30000.0

    assert historial[1].tipo_movimiento == "cargo"
    assert historial[1].monto == 15000.0
    assert historial[1].saldo_resultante == 45000.0

    assert historial[2].tipo_movimiento == "abono"
    assert historial[2].monto == 10000.0
    assert historial[2].saldo_resultante == 35000.0


def test_atomicidad_y_rollback_en_fallo(db_conn):
    """
    Verifica que si ocurre un fallo durante la transacción (por ejemplo, en el UPDATE a clientes),
    se ejecute rollback automático y no queden registros huérfanos en cuentas_por_cobrar ni se altere el saldo.
    """
    cliente = crear_cliente(nombre="Roberto Gómez Fallo", conn=db_conn)
    cursor = db_conn.cursor()

    # Instalar trigger temporal que fuerza abort durante el UPDATE a clientes
    cursor.execute(f"""
        CREATE TRIGGER simular_fallo_update_cliente
        BEFORE UPDATE OF saldo_actual ON clientes
        WHEN NEW.id = {cliente.id}
        BEGIN
            SELECT RAISE(ABORT, 'Simulación de fallo forzado en transacción');
        END;
    """)
    db_conn.commit()

    with pytest.raises(sqlite3.DatabaseError, match="Simulación de fallo forzado"):
        registrar_cargo(cliente.id, 20000.0, db_conn)

    # Verificar que el rollback atómico deshizo la inserción en cuentas_por_cobrar
    cursor.execute("SELECT count(*) as total FROM cuentas_por_cobrar WHERE cliente_id = ?", (cliente.id,))
    assert cursor.fetchone()["total"] == 0

    # Verificar que el saldo del cliente se mantiene intacto en 0.0
    assert consultar_saldo(cliente.id, db_conn) == 0.0

