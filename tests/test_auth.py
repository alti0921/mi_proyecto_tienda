import pytest
from services.auth_service import (
    autenticar_usuario,
    crear_usuario,
    generar_password_hash,
    verificar_password,
    obtener_usuario_por_id,
    obtener_usuario_por_username,
)
from models.usuario import Usuario


def test_hashing_sha256_salted():
    """Verifica que el hashing genere salts únicos y verifique contraseñas correctamente."""
    pw = "ClaveSecreta123*"
    hash1 = generar_password_hash(pw)
    hash2 = generar_password_hash(pw)

    # Salts aleatorios deben producir hashes diferentes para la misma clave
    assert hash1 != hash2
    assert hash1.startswith("sha256$")
    assert hash2.startswith("sha256$")

    # Verificación de coincidencia
    assert verificar_password(pw, hash1) is True
    assert verificar_password(pw, hash2) is True
    assert verificar_password("ClaveErronea", hash1) is False
    assert verificar_password("", hash1) is False
    assert verificar_password(pw, "formato_invalido") is False


def test_autenticacion_admin_por_defecto(db_conn):
    """Verifica la autenticación exitosa del usuario administrador inicial de schema.sql."""
    # El usuario 'admin' viene sembrado con la clave por defecto 'admin123'
    usuario = autenticar_usuario(username="admin", password="admin123", conn=db_conn)

    assert usuario is not None
    assert isinstance(usuario, Usuario)
    assert usuario.id == 1
    assert usuario.username == "admin"
    assert usuario.rol == "admin"
    assert usuario.activo is True


def test_creacion_y_autenticacion_vendedor(db_conn):
    """Verifica la creación y autenticación exitosa de un usuario con rol 'vendedor'."""
    nuevo_user = crear_usuario(
        username="carlos_vendedor",
        password="vendedor_pass_2026",
        nombre="Carlos Andrés Mendoza",
        rol="vendedor",
        conn=db_conn,
    )

    assert nuevo_user.id is not None
    assert nuevo_user.username == "carlos_vendedor"
    assert nuevo_user.rol == "vendedor"
    assert nuevo_user.activo is True

    # Autenticar con credenciales correctas (insensible a mayúsculas/minúsculas en username)
    auth_user = autenticar_usuario(
        username="CARLOS_VENDEDOR",
        password="vendedor_pass_2026",
        conn=db_conn,
    )
    assert auth_user is not None
    assert auth_user.id == nuevo_user.id
    assert auth_user.nombre == "Carlos Andrés Mendoza"
    assert auth_user.rol == "vendedor"


def test_rechazo_por_contrasena_incorrecta(db_conn):
    """Verifica que una contraseña errónea retorne None sin revelar información."""
    # Clave incorrecta para usuario existente
    resultado = autenticar_usuario(username="admin", password="password_falsa_999", conn=db_conn)
    assert resultado is None


def test_rechazo_por_usuario_inexistente(db_conn):
    """Verifica que un usuario no registrado retorne None."""
    resultado = autenticar_usuario(username="usuario_fantasma_xyz", password="cualquier_password", conn=db_conn)
    assert resultado is None


def test_rechazo_por_usuario_inactivo(db_conn):
    """Verifica que un usuario deshabilitado (activo = 0) no pueda autenticarse aunque la clave sea correcta."""
    user_bloqueado = crear_usuario(
        username="lucia_inactiva",
        password="password_valida_123",
        nombre="Lucía Gómez",
        rol="vendedor",
        activo=0,
        conn=db_conn,
    )
    assert user_bloqueado.activo is False

    # Intentar autenticar con la clave correcta
    resultado = autenticar_usuario(username="lucia_inactiva", password="password_valida_123", conn=db_conn)
    assert resultado is None


def test_validaciones_creacion_usuario(db_conn):
    """Verifica las validaciones de negocio e integridad en la creación de usuarios."""
    # 1. Nombre de usuario duplicado
    with pytest.raises(ValueError, match="Ya existe un usuario con el nombre de usuario"):
        crear_usuario(
            username="admin",
            password="otra_password",
            nombre="Duplicado Admin",
            conn=db_conn,
        )

    # 2. Rol inválido
    with pytest.raises(ValueError, match="Rol no válido"):
        crear_usuario(
            username="super_user",
            password="password123",
            nombre="Super",
            rol="superadmin",
            conn=db_conn,
        )

    # 3. Campos vacíos
    with pytest.raises(ValueError, match="nombre de usuario no puede estar vacío"):
        crear_usuario(username="", password="password123", nombre="Sin Username", conn=db_conn)

    with pytest.raises(ValueError, match="nombre real del usuario no puede estar vacío"):
        crear_usuario(username="alguien", password="password123", nombre="   ", conn=db_conn)


def test_obtener_usuario_por_id_y_username(db_conn):
    """Verifica las funciones de consulta de usuarios."""
    user = obtener_usuario_por_id(1, db_conn)
    assert user is not None
    assert user.username == "admin"

    user_by_name = obtener_usuario_por_username("ADMIN", db_conn)
    assert user_by_name is not None
    assert user_by_name.id == 1

    assert obtener_usuario_por_id(9999, db_conn) is None
    assert obtener_usuario_por_username("no_existe", db_conn) is None
