import sqlite3
import pytest
from services.cxc_service import (
    crear_cliente,
    obtener_cliente,
    listar_clientes,
    buscar_clientes,
    actualizar_cliente,
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
    Verifica que al registrar un cargo dentro del límite de crédito:
    1. Se inserte el registro inmutable en cuentas_por_cobrar con tipo_movimiento='cargo'.
    2. Se incremente clientes.saldo_actual atómicamente.
    """
    cliente = crear_cliente(
        nombre="Carmen Rodríguez", limite_credito=50000.0, conn=db_conn
    )
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
    cliente = crear_cliente(
        nombre="Luis Martínez", limite_credito=100000.0, conn=db_conn
    )
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
    cliente = crear_cliente(
        nombre="Marcos Peña", limite_credito=50000.0, conn=db_conn
    )
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
    cliente = crear_cliente(
        nombre="Ana Torres", limite_credito=50000.0, conn=db_conn
    )
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
    cliente = crear_cliente(
        nombre="Sofía Herrera", limite_credito=100000.0, conn=db_conn
    )

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
    cliente = crear_cliente(
        nombre="Roberto Gómez Fallo", limite_credito=50000.0, conn=db_conn
    )
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
    cursor.execute(
        "SELECT count(*) as total FROM cuentas_por_cobrar WHERE cliente_id = ?",
        (cliente.id,),
    )
    assert cursor.fetchone()["total"] == 0

    # Verificar que el saldo del cliente se mantiene intacto en 0.0
    assert consultar_saldo(cliente.id, db_conn) == 0.0


def test_registrar_cargo_excede_limite_credito(db_conn):
    """
    Verifica que registrar_cargo rechace transacciones que superen el límite
    de crédito asignado al cliente.
    """
    cliente = crear_cliente(
        nombre="Fabián Castro",
        limite_credito=50000.0,
        conn=db_conn,
    )

    # Cargo permitido dentro del cupo (30.000 <= 50.000)
    registrar_cargo(cliente.id, 30000.0, db_conn)
    assert consultar_saldo(cliente.id, db_conn) == 30000.0

    # Cargo que excede el cupo (30.000 + 25.000 = 55.000 > 50.000)
    with pytest.raises(ValueError, match="El cargo excede el límite de crédito del cliente"):
        registrar_cargo(cliente.id, 25000.0, db_conn)

    # El saldo no debe haber cambiado
    assert consultar_saldo(cliente.id, db_conn) == 30000.0


def test_registrar_cargo_cliente_sin_cupo_asignado_rechaza_cualquier_cargo(db_conn):
    """
    Verifica que un cliente recién creado con límite de crédito por defecto (0.0)
    no pueda recibir ningún cargo, rechazando incluso montos mínimos (ej. $1.000).
    """
    cliente = crear_cliente(nombre="Cliente Sin Cupo", conn=db_conn)  # limite_credito=0.0 por defecto
    with pytest.raises(ValueError, match="El cargo excede el límite de crédito del cliente"):
        registrar_cargo(cliente.id, 1000.0, db_conn)
    assert consultar_saldo(cliente.id, db_conn) == 0.0


def test_actualizar_cliente_exitoso_y_validaciones(db_conn):
    """
    Verifica la actualización de datos de un cliente (RF-CXC-01), incluyendo
    la evolución del nivel_vinculo y el cambio de estado activo.
    Confirma que limite_credito y saldo_actual permanezcan inalterados.
    """
    cliente = crear_cliente(
        nombre="Carlos Vecino Inicial",
        telefono="3000000000",
        direccion="Cra 1 # 2-3",
        nivel_vinculo="solo_apodo",
        conn=db_conn,
    )
    assert cliente.nivel_vinculo == "solo_apodo"
    assert cliente.activo is True

    # 1. Actualización exitosa evolucionando nivel_vinculo a conocido_referido
    cli_actualizado = actualizar_cliente(
        cliente_id=cliente.id,
        conn=db_conn,
        nombre="Carlos Alberto Vecino",
        telefono="3119998877",
        direccion="Cra 10 # 20-30",
        nivel_vinculo="conocido_referido",
    )

    assert cli_actualizado.nombre == "Carlos Alberto Vecino"
    assert cli_actualizado.telefono == "3119998877"
    assert cli_actualizado.direccion == "Cra 10 # 20-30"
    assert cli_actualizado.nivel_vinculo == "conocido_referido"
    assert cli_actualizado.limite_credito == 0.0  # Inmutable en esta función
    assert cli_actualizado.saldo_actual == 0.0    # Inmutable en esta función

    # 2. Desactivación (baja lógica)
    cli_inactivo = actualizar_cliente(cliente_id=cliente.id, conn=db_conn, activo=0)
    assert cli_inactivo.activo is False

    # 3. Rechazo de nivel_vinculo inválido
    with pytest.raises(ValueError, match="Nivel de vínculo 'amigo_intimo' no válido"):
        actualizar_cliente(cliente_id=cliente.id, conn=db_conn, nivel_vinculo="amigo_intimo")

    # 4. Rechazo de nombre vacío
    with pytest.raises(ValueError, match="El nombre del cliente no puede estar vacío"):
        actualizar_cliente(cliente_id=cliente.id, conn=db_conn, nombre="   ")

    # 5. Rechazo de activo inválido
    with pytest.raises(ValueError, match="El estado activo debe ser 0 o 1"):
        actualizar_cliente(cliente_id=cliente.id, conn=db_conn, activo=2)

    # 6. Rechazo de cliente inexistente
    with pytest.raises(ValueError, match="Cliente ID 9999 no encontrado"):
        actualizar_cliente(cliente_id=9999, conn=db_conn, nombre="Fantasma")


def test_buscar_y_listar_clientes_seguro(db_conn):
    """
    Verifica listar_clientes y buscar_clientes con parameter binding seguro.
    Confirma que solo_activos=True excluya clientes inactivos por defecto.
    """
    # Crear clientes de prueba
    c1 = crear_cliente(nombre="Beatriz Helena Pinzón", telefono="3205551122", direccion="Barrio Boston", conn=db_conn)
    c2 = crear_cliente(nombre="Armando Mendoza Sáenz", telefono="3159994433", direccion="Barrio El Prado", conn=db_conn)
    c3 = crear_cliente(nombre="Nicolás Mora Cifuentes", telefono="3017778899", direccion="Soledad 2000", conn=db_conn)

    # Inactivar a Nicolás
    actualizar_cliente(cliente_id=c3.id, conn=db_conn, activo=0)

    # 1. listar_clientes solo activos
    activos = listar_clientes(db_conn, solo_activos=True)
    ids_activos = [c.id for c in activos]
    assert c1.id in ids_activos
    assert c2.id in ids_activos
    assert c3.id not in ids_activos

    # 2. buscar_clientes por nombre
    res_nombre = buscar_clientes("Beatriz", db_conn)
    assert len(res_nombre) == 1
    assert res_nombre[0].id == c1.id

    # 3. buscar_clientes por teléfono
    res_tel = buscar_clientes("99944", db_conn)
    assert len(res_tel) == 1
    assert res_tel[0].id == c2.id

    # 4. buscar_clientes por dirección
    res_dir = buscar_clientes("Prado", db_conn)
    assert len(res_dir) == 1
    assert res_dir[0].id == c2.id

    # 5. buscar cliente inactivo con solo_activos=True no debe aparecer
    assert len(buscar_clientes("Nicolás", db_conn, solo_activos=True)) == 0

    # 6. buscar cliente inactivo con solo_activos=False sí aparece
    res_inactivo = buscar_clientes("Nicolás", db_conn, solo_activos=False)
    assert len(res_inactivo) == 1
    assert res_inactivo[0].id == c3.id

    # 7. Término vacío retorna listado completo
    assert len(buscar_clientes("", db_conn, solo_activos=True)) == len(activos)


def test_cliente_property_cupo_disponible(db_conn):
    """
    Verifica que la propiedad calculada cupo_disponible calcule exactamente
    max(0.0, round(limite_credito - saldo_actual, 2)).
    """
    cliente = crear_cliente(nombre="Doña Carmen", limite_credito=100000.0, conn=db_conn)
    assert cliente.cupo_disponible == 100000.0

    # Registrar un cargo de $40.000
    registrar_cargo(cliente.id, 40000.0, db_conn)
    cli_actualizado = obtener_cliente(cliente.id, db_conn)
    assert cli_actualizado.saldo_actual == 40000.0
    assert cli_actualizado.cupo_disponible == 60000.0

    # Si el saldo iguala o excede el cupo, cupo_disponible no es negativo
    cli_tope = crear_cliente(nombre="Don José Cupo Cero", limite_credito=0.0, conn=db_conn)
    assert cli_tope.cupo_disponible == 0.0


def test_cxc_persistencia_usuario_id_en_cargos_y_abonos(db_conn):
    """
    RF-CXC-04: Verifica que registrar_cargo y registrar_abono persistan
    el usuario_id en la tabla inmutable cuentas_por_cobrar para auditoría de cajero.
    """
    cliente = crear_cliente(nombre="Ana Auditada", limite_credito=80000.0, conn=db_conn)

    cargo = registrar_cargo(
        cliente_id=cliente.id,
        monto=30000.0,
        conn=db_conn,
        descripcion="Cargo a crédito auditado",
        usuario_id=1,
    )
    assert cargo.usuario_id == 1

    # Validar persistencia directa en SQLite
    cur = db_conn.cursor()
    cur.execute("SELECT usuario_id FROM cuentas_por_cobrar WHERE id = ?", (cargo.id,))
    row_cargo = cur.fetchone()
    assert row_cargo["usuario_id"] == 1

    abono = registrar_abono(
        cliente_id=cliente.id,
        monto=10000.0,
        conn=db_conn,
        descripcion="Abono recibido por cajero 2",
        usuario_id=2,
    )
    assert abono.usuario_id == 2

    cur.execute("SELECT usuario_id FROM cuentas_por_cobrar WHERE id = ?", (abono.id,))
    row_abono = cur.fetchone()
    assert row_abono["usuario_id"] == 2

