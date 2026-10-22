import pytest
from services.auth_service import (
    autenticar_usuario,
    crear_usuario,
    generar_password_hash,
    verificar_password,
    obtener_usuario_por_id,
    obtener_usuario_por_username,
    listar_usuarios,
    cambiar_estado_usuario,
    restablecer_password,
    cambiar_password,
    usa_contrasena_inicial,
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


def test_listar_usuarios_incluye_semillas_ordenados(db_conn):
    """Verifica que listar_usuarios incluya a los usuarios semilla ordenados por username."""
    usuarios = listar_usuarios(db_conn)
    usernames = [u.username for u in usuarios]
    assert "admin" in usernames
    assert "vendedor" in usernames
    assert usernames == sorted(usernames)


def test_crear_usuario_rechaza_password_corta(db_conn):
    """Verifica que crear_usuario rechace contraseñas de menos de 6 caracteres."""
    with pytest.raises(ValueError, match="al menos 6"):
        crear_usuario(
            username="test_corta",
            password="abc",
            nombre="Usuario Clave Corta",
            conn=db_conn,
        )


def test_cambiar_estado_usuario_desactiva_y_reactiva(db_conn):
    """Verifica que cambiar_estado_usuario desactive y reactive correctamente a un usuario."""
    vendedor = crear_usuario(
        username="vend_estado_test",
        password="password123",
        nombre="Vendedor Estado Test",
        conn=db_conn,
    )
    # Desactivar usuario
    actualizado = cambiar_estado_usuario(vendedor.id, False, db_conn)
    assert actualizado.activo is False
    assert autenticar_usuario("vend_estado_test", "password123", db_conn) is None

    # Reactivar usuario
    reactivado = cambiar_estado_usuario(vendedor.id, True, db_conn)
    assert reactivado.activo is True
    auth = autenticar_usuario("vend_estado_test", "password123", db_conn)
    assert auth is not None
    assert auth.id == vendedor.id


def test_no_se_puede_desactivar_ultimo_admin(db_conn):
    """Verifica la protección que impide desactivar al único administrador activo."""
    # Desactivar al admin 1 (único administrador activo de las semillas)
    with pytest.raises(ValueError, match="último administrador activo"):
        cambiar_estado_usuario(1, False, db_conn)

    # Verificar que sigue activo en la base de datos
    admin_bd = obtener_usuario_por_id(1, db_conn)
    assert admin_bd.activo is True

    # Crear un segundo administrador activo
    admin_dos = crear_usuario(
        username="admin_dos_test",
        password="password123",
        nombre="Segundo Admin",
        rol="admin",
        conn=db_conn,
    )

    # Ahora desactivar al admin 1 sí debe permitirse
    admin1_desactivado = cambiar_estado_usuario(1, False, db_conn)
    assert admin1_desactivado.activo is False

    # Desactivar al segundo admin (que ahora es el único activo) debe fallar
    with pytest.raises(ValueError, match="último administrador activo"):
        cambiar_estado_usuario(admin_dos.id, False, db_conn)


def test_cambiar_estado_usuario_inexistente(db_conn):
    """Verifica que intentar cambiar el estado de un usuario que no existe lance ValueError."""
    with pytest.raises(ValueError, match="no encontrado"):
        cambiar_estado_usuario(99999, False, db_conn)


def test_restablecer_password(db_conn):
    """Verifica la función administrativa de restablecimiento de contraseña."""
    vendedor = crear_usuario(
        username="vend_restablecer_test",
        password="clave_original",
        nombre="Vendedor Restablecer",
        conn=db_conn,
    )

    # Restablecer contraseña a 'temporal1'
    restablecer_password(vendedor.id, "temporal1", db_conn)

    # Con la clave vieja ya no autentica, con la nueva sí
    assert autenticar_usuario("vend_restablecer_test", "clave_original", db_conn) is None
    nuevo_auth = autenticar_usuario("vend_restablecer_test", "temporal1", db_conn)
    assert nuevo_auth is not None
    assert nuevo_auth.id == vendedor.id

    # El password_hash guardado empieza por 'sha256$' y no contiene la clave en plano
    cur = db_conn.cursor()
    cur.execute("SELECT password_hash FROM usuarios WHERE id = ?", (vendedor.id,))
    pw_hash = cur.fetchone()["password_hash"]
    assert pw_hash.startswith("sha256$")
    assert "temporal1" not in pw_hash

    # Restablecer con contraseña de menos de 6 caracteres debe fallar
    with pytest.raises(ValueError, match="al menos 6"):
        restablecer_password(vendedor.id, "abc", db_conn)


def test_cambiar_password_propia(db_conn):
    """Verifica el flujo de cambio de contraseña por parte del usuario autenticado."""
    user = crear_usuario(
        username="user_cambio_pw_test",
        password="clave_inicial",
        nombre="Usuario Cambio PW",
        conn=db_conn,
    )

    # 1. Contraseña actual incorrecta
    with pytest.raises(ValueError, match="actual no es correcta"):
        cambiar_password(user.id, "clave_falsa", "nueva_clave_123", db_conn)
    assert autenticar_usuario("user_cambio_pw_test", "clave_inicial", db_conn) is not None

    # 2. Nueva contraseña igual a la actual
    with pytest.raises(ValueError, match="diferente de la actual"):
        cambiar_password(user.id, "clave_inicial", "clave_inicial", db_conn)

    # 3. Nueva contraseña demasiado corta
    with pytest.raises(ValueError, match="al menos 6"):
        cambiar_password(user.id, "clave_inicial", "abc", db_conn)

    # 4. Flujo correcto
    cambiar_password(user.id, "clave_inicial", "clave_nueva_valida", db_conn)
    assert autenticar_usuario("user_cambio_pw_test", "clave_nueva_valida", db_conn) is not None
    assert autenticar_usuario("user_cambio_pw_test", "clave_inicial", db_conn) is None


def test_usa_contrasena_inicial():
    """
    Verifica que usa_contrasena_inicial devuelva True únicamente con la contraseña
    inicial de tienda ('tienda123'), y False con 'admin123' o cualquier otra clave.
    """
    assert usa_contrasena_inicial("tienda123") is True
    assert usa_contrasena_inicial("admin123") is False
    assert usa_contrasena_inicial("otra_cualquiera") is False
    assert usa_contrasena_inicial("") is False


def test_crear_usuario_con_contrasena_inicial_tienda(db_conn):
    """
    Verifica que crear_usuario con la contraseña inicial de tienda ('tienda123')
    genere un hash SHA-256 válido y permita autenticar al usuario correctamente.
    """
    user = crear_usuario(
        username="admin_tienda_inicial",
        password="tienda123",
        nombre="Admin Tienda",
        rol="admin",
        conn=db_conn,
    )
    assert user.id is not None
    cur = db_conn.cursor()
    cur.execute("SELECT password_hash FROM usuarios WHERE id = ?", (user.id,))
    pw_hash = cur.fetchone()["password_hash"]
    assert pw_hash.startswith("sha256$")
    assert "tienda123" not in pw_hash

    auth = autenticar_usuario("admin_tienda_inicial", "tienda123", db_conn)
    assert auth is not None
    assert auth.id == user.id


