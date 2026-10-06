import sqlite3
from typing import Optional, List
from models.cliente import Cliente
from models.cuenta_por_cobrar import CuentaPorCobrar

NIVELES_VINCULO_VALIDOS = ("registro_completo", "conocido_referido", "solo_apodo")


def _row_to_cliente(row: sqlite3.Row) -> Cliente:
    """Mapea una fila de sqlite3.Row al dataclass Cliente."""
    return Cliente(
        id=row["id"],
        nombre=row["nombre"],
        telefono=row["telefono"],
        direccion=row["direccion"],
        limite_credito=float(row["limite_credito"]),
        saldo_actual=float(row["saldo_actual"]),
        score_crediticio=int(row["score_crediticio"]),
        categoria_riesgo=row["categoria_riesgo"],
        nivel_vinculo=row["nivel_vinculo"],
        activo=bool(row["activo"]),
    )


def _row_to_cxc(row: sqlite3.Row) -> CuentaPorCobrar:
    """Mapea una fila de sqlite3.Row al DTO CuentaPorCobrar."""
    usuario_id = row["usuario_id"] if "usuario_id" in row.keys() else None
    return CuentaPorCobrar(
        id=row["id"],
        cliente_id=row["cliente_id"],
        venta_id=row["venta_id"],
        usuario_id=usuario_id,
        tipo_movimiento=row["tipo_movimiento"],
        monto=float(row["monto"]),
        saldo_resultante=float(row["saldo_resultante"]),
        descripcion=row["descripcion"],
        fecha_movimiento=row["fecha_movimiento"],
    )


def crear_cliente(
    nombre: str,
    conn: sqlite3.Connection,
    telefono: Optional[str] = None,
    direccion: Optional[str] = None,
    nivel_vinculo: str = "solo_apodo",
    limite_credito: float = 0.0,
) -> Cliente:
    """
    Crea y persiste un nuevo cliente en la base de datos (RF-CXC-02).
    Valida campos obligatorios y reglas de integridad.
    """
    if not nombre or not nombre.strip():
        raise ValueError("El nombre del cliente no puede estar vacío.")
    if nivel_vinculo not in NIVELES_VINCULO_VALIDOS:
        raise ValueError(
            f"Nivel de vínculo '{nivel_vinculo}' no válido. Debe ser uno de: {NIVELES_VINCULO_VALIDOS}."
        )
    if limite_credito < 0:
        raise ValueError(f"El límite de crédito no puede ser negativo ({limite_credito}).")

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO clientes (
                nombre, telefono, direccion, limite_credito, saldo_actual,
                score_crediticio, categoria_riesgo, nivel_vinculo, activo
            )
            VALUES (?, ?, ?, ?, 0.0, 60, 'B', ?, 1)
            """,
            (nombre.strip(), telefono, direccion, limite_credito, nivel_vinculo),
        )
        nuevo_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return Cliente(
        id=nuevo_id,
        nombre=nombre.strip(),
        telefono=telefono,
        direccion=direccion,
        limite_credito=limite_credito,
        saldo_actual=0.0,
        score_crediticio=60,
        categoria_riesgo="B",
        nivel_vinculo=nivel_vinculo,
        activo=True,
    )


def obtener_cliente(cliente_id: int, conn: sqlite3.Connection) -> Optional[Cliente]:
    """
    Obtiene un cliente por su ID. Retorna None si no existe o no está activo.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM clientes WHERE id = ? AND activo = 1", (cliente_id,)
    )
    row = cursor.fetchone()
    return _row_to_cliente(row) if row else None


def listar_clientes(conn: sqlite3.Connection, solo_activos: bool = True) -> List[Cliente]:
    """
    Lista todos los clientes registrados. Por defecto retorna solo los activos.
    """
    cursor = conn.cursor()
    if solo_activos:
        cursor.execute("SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre ASC")
    else:
        cursor.execute("SELECT * FROM clientes ORDER BY nombre ASC")
    return [_row_to_cliente(row) for row in cursor.fetchall()]


def buscar_clientes(
    termino: str,
    conn: sqlite3.Connection,
    solo_activos: bool = True,
) -> List[Cliente]:
    """
    Busca clientes por coincidencia parcial en nombre, teléfono o dirección (RF-CXC-01 / RF-POS-01).
    Utiliza parámetros seguros (?) para prevenir inyecciones SQL.
    Por defecto filtra solo clientes activos (activo = 1).
    """
    if not termino or not termino.strip():
        return listar_clientes(conn, solo_activos=solo_activos)

    cursor = conn.cursor()
    patron = f"%{termino.strip()}%"
    if solo_activos:
        cursor.execute(
            """
            SELECT * FROM clientes
            WHERE activo = 1 AND (nombre LIKE ? OR telefono LIKE ? OR direccion LIKE ?)
            ORDER BY nombre ASC
            """,
            (patron, patron, patron),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM clientes
            WHERE (nombre LIKE ? OR telefono LIKE ? OR direccion LIKE ?)
            ORDER BY nombre ASC
            """,
            (patron, patron, patron),
        )
    return [_row_to_cliente(row) for row in cursor.fetchall()]


def actualizar_cliente(
    cliente_id: int,
    conn: sqlite3.Connection,
    nombre: Optional[str] = None,
    telefono: Optional[str] = None,
    direccion: Optional[str] = None,
    nivel_vinculo: Optional[str] = None,
    activo: Optional[int] = None,
) -> Cliente:
    """
    Actualiza los datos modificables del cliente.
    Valida que nivel_vinculo pertenezca a NIVELES_VINCULO_VALIDOS si se proporciona.
    Valida activo in (0, 1) si se proporciona.
    Retorna el dataclass Cliente actualizado.
    NOTA: limite_credito NO se actualiza aquí (se gestiona exclusivamente vía pos_service.asignar_limite_credito).
    saldo_actual NO se actualiza aquí (inmutable, solo vía cargos y abonos).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Cliente ID {cliente_id} no encontrado.")

    nuevo_nombre = nombre.strip() if nombre is not None else row["nombre"]
    if not nuevo_nombre:
        raise ValueError("El nombre del cliente no puede estar vacío.")

    nuevo_telefono = telefono.strip() if telefono is not None and telefono.strip() else (telefono if telefono is None else None)
    if telefono is not None and not telefono.strip():
        nuevo_telefono = None
    elif telefono is None:
        nuevo_telefono = row["telefono"]

    nueva_direccion = direccion.strip() if direccion is not None and direccion.strip() else (direccion if direccion is None else None)
    if direccion is not None and not direccion.strip():
        nueva_direccion = None
    elif direccion is None:
        nueva_direccion = row["direccion"]

    nuevo_nivel_vinculo = nivel_vinculo if nivel_vinculo is not None else row["nivel_vinculo"]
    if nuevo_nivel_vinculo not in NIVELES_VINCULO_VALIDOS:
        raise ValueError(
            f"Nivel de vínculo '{nuevo_nivel_vinculo}' no válido. Debe ser uno de: {NIVELES_VINCULO_VALIDOS}."
        )

    nuevo_activo = activo if activo is not None else row["activo"]
    if nuevo_activo not in (0, 1):
        raise ValueError("El estado activo debe ser 0 o 1.")

    try:
        cursor.execute(
            """
            UPDATE clientes
            SET nombre = ?, telefono = ?, direccion = ?, nivel_vinculo = ?, activo = ?
            WHERE id = ?
            """,
            (nuevo_nombre, nuevo_telefono, nueva_direccion, nuevo_nivel_vinculo, nuevo_activo, cliente_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    cursor.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,))
    row_actualizada = cursor.fetchone()
    return _row_to_cliente(row_actualizada)



def registrar_cargo(
    cliente_id: int,
    monto: float,
    conn: sqlite3.Connection,
    venta_id: Optional[int] = None,
    descripcion: Optional[str] = None,
    auto_commit: bool = True,
    usuario_id: Optional[int] = None,
) -> CuentaPorCobrar:
    """
    Registra un cargo a la cuenta por cobrar del cliente (RF-CXC-01).
    Garantiza atomicidad transaccional:
    1. Inserta el movimiento inmutable en cuentas_por_cobrar con usuario_id opcional.
    2. Actualiza clientes.saldo_actual = saldo_actual + monto.
    Si auto_commit es True, confirma o revierte la transacción internamente.
    Si es False, delega el control transaccional al orquestador.
    """
    if monto <= 0:
        raise ValueError(f"El monto del cargo debe ser mayor a cero (recibido: {monto}).")

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, saldo_actual, limite_credito, activo FROM clientes WHERE id = ?", (cliente_id,)
    )
    row = cursor.fetchone()
    if not row or not row["activo"]:
        raise ValueError(f"Cliente ID {cliente_id} no encontrado o inactivo.")

    saldo_actual = float(row["saldo_actual"] or 0.0)
    limite_credito = float(row["limite_credito"] or 0.0)
    nuevo_saldo = round(saldo_actual + monto, 2)

    if nuevo_saldo > limite_credito:
        raise ValueError(
            f"El cargo excede el límite de crédito del cliente (Cupo: {limite_credito}, Saldo resultante: {nuevo_saldo})."
        )

    try:
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar (
                cliente_id, venta_id, usuario_id, tipo_movimiento, monto, saldo_resultante, descripcion
            )
            VALUES (?, ?, ?, 'cargo', ?, ?, ?)
            """,
            (cliente_id, venta_id, usuario_id, monto, nuevo_saldo, descripcion),
        )
        cxc_id = cursor.lastrowid

        cursor.execute(
            "UPDATE clientes SET saldo_actual = ? WHERE id = ?",
            (nuevo_saldo, cliente_id),
        )
        if auto_commit:
            conn.commit()
    except Exception as e:
        if auto_commit:
            conn.rollback()
        raise e

    # Consultar fecha_movimiento asignada por SQLite
    cursor.execute(
        "SELECT fecha_movimiento FROM cuentas_por_cobrar WHERE id = ?", (cxc_id,)
    )
    cxc_row = cursor.fetchone()
    fecha_mov = cxc_row["fecha_movimiento"] if cxc_row else None

    return CuentaPorCobrar(
        id=cxc_id,
        cliente_id=cliente_id,
        venta_id=venta_id,
        usuario_id=usuario_id,
        tipo_movimiento="cargo",
        monto=monto,
        saldo_resultante=nuevo_saldo,
        descripcion=descripcion,
        fecha_movimiento=fecha_mov,
    )


def registrar_abono(
    cliente_id: int,
    monto: float,
    conn: sqlite3.Connection,
    venta_id: Optional[int] = None,
    descripcion: Optional[str] = None,
    auto_commit: bool = True,
    usuario_id: Optional[int] = None,
) -> CuentaPorCobrar:
    """
    Registra un abono a la cuenta del cliente (RF-CXC-01).
    Valida que el abono no supere el saldo pendiente (impide saldo negativo/a favor).
    Garantiza atomicidad transaccional:
    1. Inserta el movimiento inmutable en cuentas_por_cobrar con usuario_id opcional.
    2. Actualiza clientes.saldo_actual = saldo_actual - monto.
    Si auto_commit es True, confirma o revierte la transacción internamente.
    Si es False, delega el control transaccional al orquestador.
    """
    if monto <= 0:
        raise ValueError(f"El monto del abono debe ser mayor a cero (recibido: {monto}).")

    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, saldo_actual, activo FROM clientes WHERE id = ?", (cliente_id,)
    )
    row = cursor.fetchone()
    if not row or not row["activo"]:
        raise ValueError(f"Cliente ID {cliente_id} no encontrado o inactivo.")

    saldo_actual = float(row["saldo_actual"] or 0.0)
    if monto > saldo_actual:
        raise ValueError(
            f"El monto del abono ({monto}) no puede ser superior al saldo pendiente ({saldo_actual})."
        )

    nuevo_saldo = round(saldo_actual - monto, 2)

    try:
        cursor.execute(
            """
            INSERT INTO cuentas_por_cobrar (
                cliente_id, venta_id, usuario_id, tipo_movimiento, monto, saldo_resultante, descripcion
            )
            VALUES (?, ?, ?, 'abono', ?, ?, ?)
            """,
            (cliente_id, venta_id, usuario_id, monto, nuevo_saldo, descripcion),
        )
        cxc_id = cursor.lastrowid

        cursor.execute(
            "UPDATE clientes SET saldo_actual = ? WHERE id = ?",
            (nuevo_saldo, cliente_id),
        )
        if auto_commit:
            conn.commit()
    except Exception as e:
        if auto_commit:
            conn.rollback()
        raise e

    # Consultar fecha_movimiento asignada por SQLite
    cursor.execute(
        "SELECT fecha_movimiento FROM cuentas_por_cobrar WHERE id = ?", (cxc_id,)
    )
    cxc_row = cursor.fetchone()
    fecha_mov = cxc_row["fecha_movimiento"] if cxc_row else None

    return CuentaPorCobrar(
        id=cxc_id,
        cliente_id=cliente_id,
        venta_id=venta_id,
        usuario_id=usuario_id,
        tipo_movimiento="abono",
        monto=monto,
        saldo_resultante=nuevo_saldo,
        descripcion=descripcion,
        fecha_movimiento=fecha_mov,
    )


def consultar_saldo(cliente_id: int, conn: sqlite3.Connection) -> float:
    """
    Consulta el saldo pendiente actual de un cliente.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Cliente ID {cliente_id} no encontrado.")
    return float(row["saldo_actual"] or 0.0)


def obtener_historial_cxc(
    cliente_id: int, conn: sqlite3.Connection
) -> List[CuentaPorCobrar]:
    """
    Retorna el historial completo inmutable de cargos y abonos del cliente,
    ordenados cronológicamente.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM cuentas_por_cobrar
        WHERE cliente_id = ?
        ORDER BY fecha_movimiento ASC, id ASC
        """,
        (cliente_id,),
    )
    return [_row_to_cxc(row) for row in cursor.fetchall()]
