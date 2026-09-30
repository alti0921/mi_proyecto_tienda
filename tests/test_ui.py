import sqlite3
import pytest
import tkinter as tk

from models.usuario import Usuario
from ui.sesion import SesionActual
from ui.widgets_comunes import AreaError, BotonRestringidoPorRol, BarraSuperior
from ui.app import App
from ui.pantallas.login import PantallaLogin


def test_sesion_actual_ciclo_de_vida(db_conn):
    """Verifica el ciclo de vida de SesionActual (iniciar sesión, permisos y cierre)."""
    sesion = SesionActual(db_conn)
    assert sesion.esta_autenticado is False
    assert sesion.es_admin is False
    assert sesion.rol_actual is None
    assert sesion.nombre_usuario == ""

    # Iniciar sesión como vendedor
    vendedor = Usuario(id=2, username="vendedor1", nombre="Carlos Vendedor", rol="vendedor", activo=True)
    sesion.iniciar_sesion(vendedor)
    assert sesion.esta_autenticado is True
    assert sesion.es_admin is False
    assert sesion.rol_actual == "vendedor"
    assert sesion.nombre_usuario == "Carlos Vendedor"

    # Iniciar sesión como admin
    admin = Usuario(id=1, username="admin", nombre="Administrador", rol="admin", activo=True)
    sesion.iniciar_sesion(admin)
    assert sesion.esta_autenticado is True
    assert sesion.es_admin is True
    assert sesion.rol_actual == "admin"
    assert sesion.nombre_usuario == "Administrador"

    # Cerrar sesión
    sesion.cerrar_sesion()
    assert sesion.esta_autenticado is False
    assert sesion.es_admin is False
    assert sesion.usuario_actual is None


@pytest.fixture(scope="module")
def ui_app():
    """Fixture que provee una única instancia de App para toda la suite de pruebas UI."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    with open("db/schema.sql", encoding="utf-8") as f:
        conn.executescript(f.read())
    with open("db/seeds_test.sql", encoding="utf-8") as f:
        conn.executescript(f.read())

    app = App(conn=conn)
    app.withdraw()
    yield app
    try:
        app.destroy()
    except Exception:
        pass


def test_area_error_comportamiento(ui_app):
    """Verifica que AreaError muestre y limpie mensajes de error correctamente."""
    container = tk.Frame(ui_app)
    area = AreaError(container)
    assert area.tiene_error() is False

    # Mostrar error
    area.mostrar_error("Credenciales inválidas.")
    assert area.tiene_error() is True
    assert area.lbl_texto.cget("text") == "Credenciales inválidas."

    # Limpiar error
    area.limpiar()
    assert area.tiene_error() is False
    assert area.lbl_texto.cget("text") == ""


def test_boton_restringido_por_rol(ui_app):
    """Verifica que BotonRestringidoPorRol se habilite/deshabilite según el rol en sesión."""
    sesion = ui_app.sesion
    btn = BotonRestringidoPorRol(ui_app, sesion=sesion, roles_permitidos=["admin"], text="Acción Admin")

    # Sin autenticar -> deshabilitado
    assert str(btn["state"]) == "disabled"

    # Autenticado como vendedor -> sigue deshabilitado
    vendedor = Usuario(id=2, username="vendedor", nombre="Vendedor", rol="vendedor")
    sesion.iniciar_sesion(vendedor)
    btn.actualizar_estado()
    assert str(btn["state"]) == "disabled"

    # Autenticado como admin -> habilitado normal
    admin = Usuario(id=1, username="admin", nombre="Admin", rol="admin")
    sesion.iniciar_sesion(admin)
    btn.actualizar_estado()
    assert str(btn["state"]) == "normal"

    # Limpiar sesión para siguientes pruebas
    sesion.cerrar_sesion()


def test_app_inicializacion_y_navegacion(ui_app):
    """Verifica que App inicialice sus componentes, contenedores y permita navegar entre pantallas."""
    assert "login" in ui_app.pantallas
    assert "pos" in ui_app.pantallas
    assert "cxc" in ui_app.pantallas
    assert "inventario" in ui_app.pantallas
    assert "reportes" in ui_app.pantallas

    # Inicia en login
    assert ui_app.sesion.esta_autenticado is False

    # Navegar a pantalla provisional
    ui_app.navegar_a("pos")
    ui_app.update_idletasks()

    # Error al navegar a pantalla inexistente
    with pytest.raises(ValueError, match="Pantalla 'inexistente' no registrada"):
        ui_app.navegar_a("inexistente")

    # Cerrar sesión regresa a login
    ui_app.cerrar_sesion()
    ui_app.update_idletasks()
    assert ui_app.sesion.esta_autenticado is False


def test_pantalla_login_flujo_completo(ui_app):
    """Verifica el flujo interactivo de PantallaLogin ante credenciales erróneas y correctas."""
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    ui_app.navegar_a("login")
    ui_app.update_idletasks()

    # 1. Campos vacíos -> Error
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_password.delete(0, tk.END)
    login_frame._procesar_login()
    assert login_frame.area_error.tiene_error() is True
    assert "ingrese su usuario y contraseña" in login_frame.area_error.lbl_texto.cget("text")

    # 2. Credenciales incorrectas -> Error genérico
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.insert(0, "password_incorrecto")
    login_frame._procesar_login()
    assert login_frame.area_error.tiene_error() is True
    assert "Usuario o contraseña incorrectos" in login_frame.area_error.lbl_texto.cget("text")
    assert ui_app.sesion.esta_autenticado is False

    # 3. Credenciales correctas (admin / admin123 de db/schema.sql)
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    # Autenticación exitosa
    assert ui_app.sesion.esta_autenticado is True
    assert ui_app.sesion.usuario_actual.username == "admin"
    assert ui_app.sesion.es_admin is True
    assert login_frame.area_error.tiene_error() is False
