import sqlite3
import hashlib
import secrets
import hmac
from typing import Optional, List
from models.usuario import Usuario

ROLES_PERMITIDOS = ("admin", "vendedor")
LONGITUD_MINIMA_PASSWORD = 6
CONTRASENA_INICIAL_TIENDA = "tienda123"


def usa_contrasena_inicial(password: str) -> bool:
    """Devuelve True solo si password coincide con la contraseña inicial de tienda."""
    return password == CONTRASENA_INICIAL_TIENDA


def _validar_password_nueva(password: str) -> None:
    """Valida la longitud mínima obligatoria para contraseñas en el sistema."""
    if not password or len(password) < LONGITUD_MINIMA_PASSWORD:
        raise ValueError("La contraseña debe tener al menos 6 caracteres.")


def generar_password_hash(password: str, salt: Optional[str] = None) -> str:
    """
    Genera un hash seguro utilizando SHA-256 con salt criptográfico aleatorio.
    Formato estándar: sha256$<salt_hex>$<hash_hex>
    """
    if not password:
        raise ValueError("La contraseña no puede estar vacía.")
    if not salt:
        salt = secrets.token_hex(16)
    hash_obj = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256${salt}${hash_obj}"


def verificar_password(password: str, hash_almacenado: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con el hash almacenado.
    Utiliza hmac.compare_digest para mitigar ataques de temporización (timing attacks).
    """
    if not password or not hash_almacenado:
        return False
    try:
        partes = hash_almacenado.split("$")
        if len(partes) != 3 or partes[0] != "sha256":
            return False
        salt = partes[1]
        hash_esperado = partes[2]
        hash_calculado = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(hash_calculado, hash_esperado)
    except Exception:
        return False


def _row_to_usuario(row: sqlite3.Row) -> Usuario:
    """Mapea una fila de sqlite3.Row al dataclass Usuario."""
    return Usuario(
        id=row["id"],
        username=row["username"],
        nombre=row["nombre"],
        rol=row["rol"],
        activo=bool(row["activo"]),
        created_at=row["created_at"] if "created_at" in row.keys() else None,
    )


def crear_usuario(
    username: str,
    password: str,
    nombre: str,
    conn: sqlite3.Connection,
    rol: str = "vendedor",
    activo: int = 1,
) -> Usuario:
    """
    Crea y persiste un nuevo usuario en la base de datos con contraseña hasheada.
    Valida roles permitidos y unicidad del nombre de usuario.
    """
    if not username or not username.strip():
        raise ValueError("El nombre de usuario no puede estar vacío.")
    if not nombre or not nombre.strip():
        raise ValueError("El nombre real del usuario no puede estar vacío.")
    if rol not in ROLES_PERMITIDOS:
        raise ValueError(f"Rol no válido: '{rol}'. Debe ser uno de {ROLES_PERMITIDOS}.")
    if activo not in (0, 1):
        raise ValueError("El estado activo debe ser 0 o 1.")

    username_limpio = username.strip().lower()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE username = ?", (username_limpio,))
    if cursor.fetchone():
        raise ValueError(f"Ya existe un usuario con el nombre de usuario '{username_limpio}'.")

    _validar_password_nueva(password)
    pw_hash = generar_password_hash(password)

    try:
        cursor.execute(
            """
            INSERT INTO usuarios (username, password_hash, nombre, rol, activo)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username_limpio, pw_hash, nombre.strip(), rol, activo),
        )
        nuevo_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return Usuario(
        id=nuevo_id,
        username=username_limpio,
        nombre=nombre.strip(),
        rol=rol,
        activo=bool(activo),
    )


def obtener_usuario_por_id(usuario_id: int, conn: sqlite3.Connection) -> Optional[Usuario]:
    """Obtiene un usuario por su ID primario."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    return _row_to_usuario(row) if row else None


def obtener_usuario_por_username(username: str, conn: sqlite3.Connection) -> Optional[Usuario]:
    """Obtiene un usuario por su nombre de usuario."""
    if not username:
        return None
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = ?", (username.strip().lower(),))
    row = cursor.fetchone()
    return _row_to_usuario(row) if row else None


def autenticar_usuario(
    username: str,
    password: str,
    conn: sqlite3.Connection,
) -> Optional[Usuario]:
    """
    Verifica credenciales contra usuarios.password_hash y usuarios.activo = 1 (RF-AUT-01).
    Retorna el dataclass Usuario (con id, username, nombre, rol, activo) si es exitoso.
    Retorna None si las credenciales son incorrectas o si el usuario está inactivo.

    Seguridad:
    - No revela en mensajes si falló el usuario o la contraseña para prevenir la enumeración de cuentas.
    - Rechaza inmediatamente si activo == 0.
    - Utiliza comparación en tiempo constante para mitigar timing attacks.
    """
    if not username or not password:
        return None

    username_limpio = username.strip().lower()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, password_hash, nombre, rol, activo, created_at FROM usuarios WHERE username = ?",
        (username_limpio,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    # Usuario inactivo (activo == 0) -> rechazo silencioso
    if not row["activo"]:
        return None

    # Validación de hash
    if not verificar_password(password, row["password_hash"]):
        return None

    return _row_to_usuario(row)


def listar_usuarios(conn: sqlite3.Connection) -> List[Usuario]:
    """
    Lista todos los usuarios (activos e inactivos) registrados en el sistema,
    ordenados alfabéticamente por username. Nunca expone password_hash.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, nombre, rol, activo, created_at FROM usuarios ORDER BY username ASC"
    )
    return [_row_to_usuario(row) for row in cursor.fetchall()]


def cambiar_estado_usuario(usuario_id: int, activo: bool, conn: sqlite3.Connection) -> Usuario:
    """
    Modifica el estado activo/inactivo de un usuario.
    Impide desactivar al último administrador activo del sistema (RF-AUT-02).
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, nombre, rol, activo, created_at FROM usuarios WHERE id = ?",
        (usuario_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Usuario con ID {usuario_id} no encontrado.")

    usuario_actual = _row_to_usuario(row)

    if not activo and usuario_actual.rol == "admin" and usuario_actual.activo:
        cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE rol = 'admin' AND activo = 1")
        total_admins_activos = cursor.fetchone()["total"]
        if total_admins_activos <= 1:
            raise ValueError("No se puede desactivar al último administrador activo.")

    nuevo_activo_int = 1 if activo else 0
    try:
        cursor.execute(
            "UPDATE usuarios SET activo = ? WHERE id = ?",
            (nuevo_activo_int, usuario_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return obtener_usuario_por_id(usuario_id, conn)


def restablecer_password(usuario_id: int, nueva_password: str, conn: sqlite3.Connection) -> None:
    """
    Restablece la contraseña de un usuario (función administrativa).
    Valida la longitud mínima y almacena únicamente el hash seguro.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE id = ?", (usuario_id,))
    if not cursor.fetchone():
        raise ValueError(f"Usuario con ID {usuario_id} no encontrado.")

    _validar_password_nueva(nueva_password)
    pw_hash = generar_password_hash(nueva_password)

    try:
        cursor.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id = ?",
            (pw_hash, usuario_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def cambiar_password(
    usuario_id: int, password_actual: str, password_nueva: str, conn: sqlite3.Connection
) -> None:
    """
    Permite a un usuario autenticado cambiar su propia contraseña.
    Valida la contraseña actual, longitud mínima de la nueva y que sea diferente de la actual.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Usuario con ID {usuario_id} no encontrado.")

    if not verificar_password(password_actual, row["password_hash"]):
        raise ValueError("La contraseña actual no es correcta.")

    _validar_password_nueva(password_nueva)

    if password_actual == password_nueva:
        raise ValueError("La nueva contraseña debe ser diferente de la actual.")

    pw_hash = generar_password_hash(password_nueva)

    try:
        cursor.execute(
            "UPDATE usuarios SET password_hash = ? WHERE id = ?",
            (pw_hash, usuario_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

