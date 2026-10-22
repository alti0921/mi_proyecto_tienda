import os
import sqlite3
import pytest
from scripts.inicializar_base_tienda import inicializar_base_tienda
from services.auth_service import autenticar_usuario
from db.migraciones import aplicar_migraciones


def test_crea_base_limpia_con_un_admin(tmp_path):
    """
    Verifica que inicializar_base_tienda cree una base completamente limpia:
    0 productos, 0 clientes, 0 ventas, 0 movimientos de cartera; exactamente
    un usuario ('admin', rol 'admin') autenticable con 'tienda123', y sin usuario 'vendedor'.
    """
    db_file = str(tmp_path / "tienda_real.db")
    inicializar_base_tienda(db_file)

    assert os.path.exists(db_file)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row

    # Tablas vacías
    assert conn.execute("SELECT COUNT(*) as c FROM productos").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) as c FROM clientes").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) as c FROM ventas").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) as c FROM cuentas_por_cobrar").fetchone()["c"] == 0

    # Exactamente 1 usuario: admin
    usuarios = conn.execute("SELECT * FROM usuarios").fetchall()
    assert len(usuarios) == 1
    u = usuarios[0]
    assert u["username"] == "admin"
    assert u["rol"] == "admin"
    assert u["nombre"] == "Administrador"

    # Autenticación con contraseña inicial de tienda
    admin_auth = autenticar_usuario("admin", "tienda123", conn)
    assert admin_auth is not None
    assert admin_auth.username == "admin"
    assert admin_auth.rol == "admin"

    # No existe vendedor
    assert autenticar_usuario("vendedor", "vend123", conn) is None
    assert conn.execute("SELECT COUNT(*) as c FROM usuarios WHERE username = 'vendedor'").fetchone()["c"] == 0

    conn.close()


def test_no_sobrescribe_base_existente(tmp_path):
    """
    Verifica que si el archivo de base de datos ya existe, inicializar_base_tienda
    lance ValueError y preserve intacto el contenido previo del archivo sin modificarlo.
    """
    db_file = str(tmp_path / "existente.db")
    contenido_previo = b"DATOS_EXISTENTES_NO_SOBRESCRIBIR"
    with open(db_file, "wb") as f:
        f.write(contenido_previo)

    with pytest.raises(ValueError, match="La base ya existe; no se reinicializa."):
        inicializar_base_tienda(db_file)

    with open(db_file, "rb") as f:
        contenido_despues = f.read()

    assert contenido_despues == contenido_previo


def test_migraciones_al_dia(tmp_path):
    """
    Verifica que tras inicializar la base limpia, el esquema contenga todas las columnas
    requeridas (incluyendo plazo_pactado_dias) y aplicar_migraciones no aplique ninguna migración adicional.
    """
    db_file = str(tmp_path / "tienda_migrada.db")
    inicializar_base_tienda(db_file)

    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clientes)")
    cols = [col["name"] for col in cursor.fetchall()]
    assert "plazo_pactado_dias" in cols

    migraciones = aplicar_migraciones(conn, db_file)
    assert len(migraciones) == 0

    conn.close()


def test_falla_no_deja_archivo(tmp_path, monkeypatch):
    """
    Verifica que si la inicialización falla durante la creación del administrador,
    la excepción se propaga y el archivo de base de datos no queda creado en disco.
    """
    db_file = str(tmp_path / "tienda_fallida.db")

    def _fallar_crear_admin(*args, **kwargs):
        raise RuntimeError("Fallo simulado en creación de admin")

    monkeypatch.setattr("scripts.inicializar_base_tienda.crear_usuario", _fallar_crear_admin)

    with pytest.raises(RuntimeError, match="Fallo simulado en creación de admin"):
        inicializar_base_tienda(db_file)

    assert not os.path.exists(db_file)


def test_preparar_base_datos_crea_y_no_sobrescribe(tmp_path):
    """
    Verifica que preparar_base_datos cree la base limpia en la primera llamada devolviendo True,
    y que en la segunda llamada devuelva False preservando idéntico el contenido del archivo.
    """
    from scripts.inicializar_base_tienda import preparar_base_datos

    db_file = str(tmp_path / "tienda_preparada.db")

    # Primera llamada: debe crear la base limpia y retornar True
    creada = preparar_base_datos(db_file)
    assert creada is True
    assert os.path.exists(db_file)

    with open(db_file, "rb") as f:
        bytes_primera = f.read()

    # Segunda llamada: la base ya existe, debe retornar False y no alterar el archivo
    segunda = preparar_base_datos(db_file)
    assert segunda is False

    with open(db_file, "rb") as f:
        bytes_segunda = f.read()

    assert bytes_segunda == bytes_primera


