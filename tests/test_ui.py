import os
import sys
import sqlite3
import pytest
import tkinter as tk
from tkinter import font
from datetime import datetime, timezone

from models.usuario import Usuario
from ui.sesion import SesionActual
from ui.widgets_comunes import (
    AreaError,
    BotonRestringidoPorRol,
    BarraSuperior,
    DialogoNuevoCliente,
    MarcoDesplazable,
)
from ui.estilos import FUENTE_BASE_BOLD
from ui.app import App
from ui.pantallas.login import PantallaLogin
from ui.pantallas.pos import PantallaPOS
from ui.pantallas.perfil_cliente import PantallaPerfilCliente
from ui.pantallas.inventario import PantallaInventario
from ui.pantallas.reportes import PantallaReportes
from ui.pantallas.usuarios import PantallaUsuarios
from services import (
    cxc_service,
    pos_service,
    scoring_service,
    inventario_service,
    reportes_service,
    auth_service,
)


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

    # Limpiar para los siguientes tests
    ui_app.cerrar_sesion()


def test_cambio_de_usuario_actualiza_permisos_en_caliente(ui_app):
    """
    Verifica que al alternar entre usuarios (admin -> logout -> vendedor)
    los permisos en BotonRestringidoPorRol y la BarraSuperior se actualicen
    dinámicamente en caliente sin necesidad de reiniciar la aplicación.
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    ui_app.navegar_a("login")

    # 1. Login como admin
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    assert ui_app.sesion.esta_autenticado is True
    assert ui_app.sesion.es_admin is True

    # Botón restringido exclusivamente para admin
    btn_admin = BotonRestringidoPorRol(
        ui_app, sesion=ui_app.sesion, roles_permitidos=["admin"], text="Sólo Admin"
    )
    assert str(btn_admin["state"]) == "normal"

    # Barra superior refleja admin
    ui_app.navegar_a("pos")
    assert "Administrador" in ui_app.barra_superior.lbl_usuario.cget("text")

    # 2. Cierre de sesión
    ui_app.cerrar_sesion()
    assert ui_app.sesion.esta_autenticado is False
    btn_admin.actualizar_estado()
    assert str(btn_admin["state"]) == "disabled"

    # 3. Login como vendedor
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "vendedor")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "vend123")
    login_frame._procesar_login()

    assert ui_app.sesion.esta_autenticado is True
    assert ui_app.sesion.es_admin is False
    assert ui_app.sesion.rol_actual == "vendedor"

    # En caliente, el botón admin debe mantenerse deshabilitado
    btn_admin.actualizar_estado()
    assert str(btn_admin["state"]) == "disabled"

    # Barra superior refleja Vendedor
    ui_app.navegar_a("pos")
    assert "Vendedor" in ui_app.barra_superior.lbl_usuario.cget("text")


def test_pos_catalogo_busqueda_y_carrito(ui_app):
    """
    Verifica la búsqueda y filtrado de catálogo, agregado al carrito en memoria,
    modificación de cantidades y soporte de venta por monto global (RF-POS-02).
    """
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]

    # 1. Catálogo inicial cargado desde semillas
    items_cat = pos.tree_catalogo.get_children()
    assert len(items_cat) >= 3

    # 2. Búsqueda de productos
    pos.entry_busqueda_prod.delete(0, tk.END)
    pos.entry_busqueda_prod.insert(0, "Arroz")
    pos._filtrar_productos()
    assert len(pos.tree_catalogo.get_children()) == 1

    # Limpiar búsqueda
    pos._limpiar_busqueda_prod()
    assert len(pos.tree_catalogo.get_children()) >= 3

    # 3. Carrito en memoria (vacío inicialmente)
    pos._vaciar_carrito()
    assert len(pos._carrito) == 0
    assert pos._obtener_total_carrito() == 0.0

    # 4. Agregar producto catalogado
    primer_item = pos.tree_catalogo.get_children()[0]
    pos.tree_catalogo.selection_set(primer_item)
    pos.spin_cant_agregar.set(1)
    pos._agregar_producto_seleccionado()

    assert len(pos._carrito) == 1
    item_carrito = pos._carrito[0]
    assert item_carrito["cantidad"] == 1.0
    assert item_carrito["subtotal"] > 0

    # 5. Modificar cantidad (+1)
    primer_item_car = pos.tree_carrito.get_children()[0]
    pos.tree_carrito.selection_set(primer_item_car)
    pos._modificar_cantidad_seleccion(1)
    assert pos._carrito[0]["cantidad"] == 2.0

    # 6. Agregar venta por monto global (producto_id=None) (RF-POS-02)
    pos.entry_monto_directo.delete(0, tk.END)
    pos.entry_monto_directo.insert(0, "150.0")
    pos.entry_desc_directo.delete(0, tk.END)
    pos.entry_desc_directo.insert(0, "Artículos varios")
    pos._agregar_monto_global()

    assert len(pos._carrito) == 2
    item_global = pos._carrito[1]
    assert item_global["producto_id"] is None
    assert item_global["descripcion"] == "Artículos varios"
    assert item_global["precio_unitario"] == 150.0
    assert item_global["subtotal"] == 150.0

    # 7. Quitar ítem y vaciar
    ultimo_item_car = pos.tree_carrito.get_children()[1]
    pos.tree_carrito.selection_set(ultimo_item_car)
    pos._quitar_item_seleccionado()
    assert len(pos._carrito) == 1

    pos._vaciar_carrito()
    assert len(pos._carrito) == 0
    assert pos._obtener_total_carrito() == 0.0


def test_pos_venta_efectivo_y_nequi(ui_app):
    """Verifica el flujo transaccional de ventas de contado (Efectivo y Nequi)."""
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos._vaciar_carrito()

    # Agregar ítem por monto directo para prueba controlada ($50.00)
    pos.entry_monto_directo.delete(0, tk.END)
    pos.entry_monto_directo.insert(0, "50.00")
    pos._agregar_monto_global()
    assert pos._obtener_total_carrito() == 50.00

    # 1. Efectivo con monto insuficiente -> Rechazo
    pos.var_tipo_pago.set("efectivo")
    pos._on_tipo_pago_cambiado()
    pos.entry_monto_recibido.delete(0, tk.END)
    pos.entry_monto_recibido.insert(0, "30.00")
    pos._confirmar_venta()
    assert pos.area_error.tiene_error() is True
    assert "insuficiente" in pos.area_error.lbl_texto.cget("text").lower()

    # 2. Efectivo con monto suficiente ($100.00) -> Éxito y cambio
    pos.entry_monto_recibido.delete(0, tk.END)
    pos.entry_monto_recibido.insert(0, "100.00")
    pos._confirmar_venta()
    assert pos.area_error.tiene_error() is False
    assert len(pos._carrito) == 0
    assert "completada (Efectivo)" in pos.lbl_exito.cget("text")
    assert "Cambio: $50.00" in pos.lbl_exito.cget("text")

    # 3. Venta por Nequi
    pos.entry_monto_directo.delete(0, tk.END)
    pos.entry_monto_directo.insert(0, "75.00")
    pos._agregar_monto_global()

    pos.var_tipo_pago.set("nequi")
    pos._on_tipo_pago_cambiado()
    assert pos.entry_monto_recibido.get() == "75.00"

    pos._confirmar_venta()
    assert pos.area_error.tiene_error() is False
    assert len(pos._carrito) == 0
    assert "completada (Nequi)" in pos.lbl_exito.cget("text")


def test_pos_venta_credito_validaciones_y_actualizacion_kpi(ui_app):
    """
    Verifica las validaciones de ventas a crédito:
    - Exigencia de cliente seleccionado
    - Tarjeta reactiva de crédito y límites
    - Despacho a crédito exitoso y actualización inmediata de KPIs.
    """
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos._vaciar_carrito()

    # Agregar ítem por monto ($100.00)
    pos.entry_monto_directo.delete(0, tk.END)
    pos.entry_monto_directo.insert(0, "100.00")
    pos._agregar_monto_global()

    pos.var_tipo_pago.set("credito")
    pos._on_tipo_pago_cambiado()

    # 1. Intento sin cliente seleccionado -> Error
    pos.combo_clientes.current(0)  # Mostrador
    pos._on_cliente_seleccionado()
    pos._confirmar_venta()
    assert pos.area_error.tiene_error() is True
    assert "Debe seleccionar un cliente" in pos.area_error.lbl_texto.cget("text")

    # 2. Seleccionar cliente de prueba (Doña María, límite 1500, saldo inicial 0)
    pos.combo_clientes.current(1)
    pos._on_cliente_seleccionado()
    assert pos._cliente_actual is not None
    assert pos._cliente_actual.nombre == "Abarrotes y Novedades Doña María"
    assert "1,500.00" in pos.lbl_card_limite.cget("text")

    cupo_antes = pos._cliente_actual.cupo_disponible
    saldo_antes = pos._cliente_actual.saldo_actual

    # 3. Venta a crédito con anticipo de $20.00 (Saldo a fiar = $80.00)
    pos.entry_monto_recibido.delete(0, tk.END)
    pos.entry_monto_recibido.insert(0, "20.00")
    pos._confirmar_venta()

    assert pos.area_error.tiene_error() is False
    assert len(pos._carrito) == 0
    assert "Venta a crédito" in pos.lbl_exito.cget("text")
    assert "Saldo financiado: $80.00" in pos.lbl_exito.cget("text")

    # 4. Verificar que la tarjeta de crédito se actualizó inmediatamente
    assert pos._cliente_actual.saldo_actual == round(saldo_antes + 80.0, 2)
    assert pos._cliente_actual.cupo_disponible == round(cupo_antes - 80.0, 2)
    assert f"{pos._cliente_actual.saldo_actual:,.2f}" in pos.lbl_card_saldo.cget("text")
    assert f"{pos._cliente_actual.cupo_disponible:,.2f}" in pos.lbl_card_cupo.cget("text")


def test_pos_boton_confirmar_activo_y_rechazo_clase_d_backend(ui_app):
    """
    Verifica la directriz estricta de arquitectura:
    El botón 'Confirmar Venta' en la UI NUNCA se deshabilita por clase de riesgo;
    permanece interactivo (state='normal') y el rechazo de crédito a un cliente
    en Clase D es dictado por pos_service.registrar_venta() en el backend,
    siendo capturado por el bloque try/except y desplegado en AreaError.
    """
    conn = ui_app.sesion.conn
    cli_d = cxc_service.crear_cliente(
        nombre="Cliente Moroso Bloqueado",
        conn=conn,
        nivel_vinculo="solo_apodo",
        limite_credito=1000.0,
    )
    # Insertar cargo vencido con más de 30 días de mora
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cuentas_por_cobrar (cliente_id, venta_id, tipo_movimiento, monto, saldo_resultante, descripcion, fecha_movimiento)
        VALUES (?, NULL, 'cargo', 800.0, 800.0, 'Fiado antiguo vencido', datetime('now', '-35 days'))
        """,
        (cli_d.id,),
    )
    cursor.execute("UPDATE clientes SET saldo_actual = 800.0 WHERE id = ?", (cli_d.id,))
    conn.commit()

    # Verificar que el scoring del backend lo categoriza en Clase D
    score, cat = scoring_service.calcular_score(cli_d.id, conn)
    assert cat == "D"

    # Navegar a POS y cargar cliente
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos.al_mostrar()

    # Seleccionar al cliente moroso
    etiqueta = f"{cli_d.nombre} (ID: {cli_d.id})"
    assert etiqueta in pos._clientes_map
    pos.combo_clientes.set(etiqueta)
    pos._on_cliente_seleccionado()

    # Agregar ítem al carrito y seleccionar crédito
    pos._vaciar_carrito()
    pos.entry_monto_directo.delete(0, tk.END)
    pos.entry_monto_directo.insert(0, "50.00")
    pos._agregar_monto_global()

    pos.var_tipo_pago.set("credito")
    pos._on_tipo_pago_cambiado()

    # El botón 'Confirmar Venta' DEBE permanecer interactivo / habilitado
    assert str(pos.btn_confirmar_venta["state"]) == "normal"

    # Al confirmar, el rechazo proviene del backend capturado por try/except
    pos._confirmar_venta()
    assert pos.area_error.tiene_error() is True
    assert "Clase D" in pos.area_error.lbl_texto.cget("text")
    assert "bloqueado" in pos.area_error.lbl_texto.cget("text").lower()


def test_perfil_cliente_cargar_y_editar_datos(ui_app):
    """
    Verifica la carga de ficha de cliente y la actualización independiente
    de datos demográficos y nivel de vínculo (cxc_service.actualizar_cliente).
    """
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]

    # Cargar primer cliente (Doña María)
    assert cxc_frame._cliente_actual is not None
    cliente_id = cxc_frame._cliente_actual.id

    # Modificar teléfono y dirección
    cxc_frame.entry_telefono.delete(0, tk.END)
    cxc_frame.entry_telefono.insert(0, "555-999-8877")
    cxc_frame.entry_direccion.delete(0, tk.END)
    cxc_frame.entry_direccion.insert(0, "Calle Nueva #456")
    cxc_frame.combo_vinculo.set("registro_completo")

    # Guardar cambios
    cxc_frame._guardar_datos_cliente()

    assert cxc_frame.area_error_datos.tiene_error() is False
    assert "guardados exitosamente" in cxc_frame.lbl_exito_datos.cget("text")

    # Verificar persistencia en base de datos
    cli_bd = cxc_service.obtener_cliente(cliente_id, ui_app.sesion.conn)
    assert cli_bd.telefono == "555-999-8877"
    assert cli_bd.direccion == "Calle Nueva #456"
    assert cli_bd.nivel_vinculo == "registro_completo"


def test_perfil_cliente_asignacion_cupo_rol_admin_vs_vendedor(ui_app):
    """
    Verifica la asignación de límite de crédito con separación de formulario
    y restricción estricta de rol (admin habilitado vs vendedor deshabilitado).
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]

    # 1. Como Administrador
    ui_app.navegar_a("login")
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    ui_app.navegar_a("cxc")
    assert ui_app.sesion.es_admin is True
    assert str(cxc_frame.btn_asignar_cupo["state"]) == "normal"

    # Asignar nuevo cupo de 3500.00
    cxc_frame.entry_nuevo_cupo.delete(0, tk.END)
    cxc_frame.entry_nuevo_cupo.insert(0, "3500.00")
    cxc_frame._asignar_cupo()

    assert cxc_frame.area_error_cupo.tiene_error() is False
    assert "actualizado a $3,500.00" in cxc_frame.lbl_exito_cupo.cget("text")
    assert cxc_frame._cliente_actual.limite_credito == 3500.00

    # 2. Como Vendedor (El botón debe inhabilitarse)
    ui_app.cerrar_sesion()
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "vendedor")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "vend123")
    login_frame._procesar_login()

    ui_app.navegar_a("cxc")
    assert ui_app.sesion.es_admin is False
    assert str(cxc_frame.btn_asignar_cupo["state"]) == "disabled"


def test_perfil_cliente_cold_start_sugerencia_no_persistida_automaticamente(ui_app):
    """
    Verifica que el protocolo Cold-Start funcione como sugerencia informativa:
    se precarga en el entry pero NO se persiste en la BD hasta confirmación explícita.
    """
    conn = ui_app.sesion.conn
    cli_nuevo = cxc_service.crear_cliente(
        nombre="Cliente Cold Start Test",
        conn=conn,
        nivel_vinculo="conocido_referido",
        limite_credito=0.0,
    )
    assert cli_nuevo.limite_credito == 0.0

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli_nuevo.id)

    # Verificar que el entry de cupo sugiere el cupo semilla ($40,000 para conocido_referido)
    assert "40000.00" in cxc_frame.entry_nuevo_cupo.get()
    assert "Sugerencia Cold-Start" in cxc_frame.lbl_sugerencia_cupo.cget("text")

    # Verificar que en la base de datos SIGUE teniendo limite_credito = 0.0 (no se autoguardó)
    cli_bd = cxc_service.obtener_cliente(cli_nuevo.id, conn)
    assert cli_bd.limite_credito == 0.0


def test_perfil_cliente_historial_inmutable_y_cascada_abono(ui_app):
    """
    Verifica que:
    1. El historial CxC no tenga bindings de mutación (inmutable append-only).
    2. Al registrar un abono, se dispare la actualización en cascada sin recargar pantalla:
       (a) Nueva fila en Treeview de historial.
       (b) Actualización de saldo_actual y cupo_disponible.
       (c) Recálculo fresco de score y clase de riesgo.
    3. Emisión del comprobante digital.
    """
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    conn = ui_app.sesion.conn

    # 1. Inmutabilidad en Treeview: no contiene bindings de doble clic ni menú de edición
    bindings = cxc_frame.tree_historial.bind()
    assert "<Double-1>" not in bindings
    assert "<Button-3>" not in bindings

    # 2. Preparar cliente con saldo deudor
    cli_test = cxc_service.crear_cliente(
        nombre="Cliente Deudor Test Cascada",
        conn=conn,
        nivel_vinculo="registro_completo",
        limite_credito=1000.0,
    )
    cxc_service.registrar_cargo(
        cliente_id=cli_test.id,
        monto=500.0,
        conn=conn,
        descripcion="Cargo para prueba de abono",
    )

    cxc_frame._cargar_selector_clientes(mantener_id=cli_test.id)
    assert cxc_frame._cliente_actual.saldo_actual == 500.0
    filas_antes = len(cxc_frame.tree_historial.get_children())

    # 3. Registrar Abono de $200.00
    cxc_frame.entry_monto_abono.delete(0, tk.END)
    cxc_frame.entry_monto_abono.insert(0, "200.00")
    cxc_frame._registrar_abono()

    assert cxc_frame.area_error_abono.tiene_error() is False
    assert "Abono #" in cxc_frame.lbl_exito_abono.cget("text")

    # (a) Verificación de nueva fila en historial
    filas_despues = len(cxc_frame.tree_historial.get_children())
    assert filas_despues == filas_antes + 1

    # (b) Verificación de saldo y cupo actualizados
    assert cxc_frame._cliente_actual.saldo_actual == 300.00
    assert cxc_frame._cliente_actual.cupo_disponible == 700.00
    assert "300.00" in cxc_frame.lbl_saldo_actual.cget("text")
    assert "700.00" in cxc_frame.lbl_cupo_disp.cget("text")

    # (c) Verificación de recálculo fresco de scoring
    assert "Score:" in cxc_frame.lbl_score_valor.cget("text")
    assert cxc_frame.lbl_badge_clase.cget("text") != "Clase: --"

    # 4. Comprobante digital en PDF 80mm (RF-CXC-04)
    archivos_abiertos = []
    cxc_frame._abrir_pdf_sistema = lambda ruta: archivos_abiertos.append(ruta)
    cxc_frame._ver_comprobante()
    assert len(archivos_abiertos) == 1
    assert os.path.exists(archivos_abiertos[0])
    assert archivos_abiertos[0].endswith(".pdf")


def test_perfil_cliente_cambio_vinculo_recalcula_score_en_caliente(ui_app):
    """
    Verifica que al editar el nivel_vinculo de un cliente (ej. de solo_apodo a registro_completo),
    _guardar_datos_cliente() recalcula inmediatamente el Score y la Clase de Riesgo en caliente
    sin necesidad de reiniciar o recargar la pantalla.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Vinculo Dinamico",
        conn=conn,
        nivel_vinculo="solo_apodo",
        limite_credito=1000.0,
    )

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    # 1. Con solo_apodo en Cold-Start, sw3 = 20 pts y clase C
    assert "Score: 20 / 100" in cxc_frame.lbl_score_valor.cget("text")
    assert "Clase C" in cxc_frame.lbl_badge_clase.cget("text")

    # 2. Modificar vínculo a registro_completo
    cxc_frame.combo_vinculo.set("registro_completo")
    cxc_frame._guardar_datos_cliente()

    # 3. El Score se actualiza de inmediato en caliente a 100 pts y Clase A
    assert cxc_frame.area_error_datos.tiene_error() is False
    assert "Score: 100 / 100" in cxc_frame.lbl_score_valor.cget("text")
    assert "Clase A" in cxc_frame.lbl_badge_clase.cget("text")

    # Verificar persistencia en base de datos
    cli_bd = cxc_service.obtener_cliente(cli.id, conn)
    assert cli_bd.nivel_vinculo == "registro_completo"


def test_inventario_maestro_detalle_y_seleccion(ui_app):
    """
    Verifica el patrón Maestro-Detalle de PantallaInventario:
    al seleccionar una fila en el catálogo, se cargan automáticamente
    los datos en los formularios de edición y ajuste sin modales invasivos.
    """
    ui_app.navegar_a("inventario")
    inv: PantallaInventario = ui_app.pantallas["inventario"]

    # Catálogo cargado con productos semilla
    items = inv.tree_catalogo.get_children()
    assert len(items) >= 3

    # Seleccionar el primer producto del catálogo ordenado
    primer_item = items[0]
    valores = inv.tree_catalogo.item(primer_item, "values")
    nombre_esperado = valores[2]
    cat_esperada = valores[3]

    inv.tree_catalogo.selection_set(primer_item)
    inv._on_producto_seleccionado()

    assert inv._producto_seleccionado is not None
    assert inv._producto_seleccionado.nombre == nombre_esperado

    # Verificar que el formulario de edición y ajuste se poblaron
    assert inv.entry_edit_nombre.get() == nombre_esperado
    assert inv.combo_edit_cat.get() == cat_esperada
    assert nombre_esperado in inv.lbl_info_prod_ajuste.cget("text")


def test_inventario_creacion_edicion_y_desactivacion_admin_only(ui_app):
    """
    Verifica los permisos por rol en PantallaInventario:
    - Admin: Habilitado para crear, editar y desactivar.
    - Vendedor: Inhabilitado (disabled) para crear, editar y desactivar.
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    inv: PantallaInventario = ui_app.pantallas["inventario"]

    # 1. Sesión como Administrador
    ui_app.navegar_a("login")
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    ui_app.navegar_a("inventario")
    assert str(inv.btn_guardar_crear["state"]) == "normal"
    assert str(inv.btn_guardar_edit["state"]) == "normal"
    assert str(inv.btn_desactivar["state"]) == "normal"

    # Crear producto nuevo como Admin
    inv.entry_crear_nombre.delete(0, tk.END)
    inv.entry_crear_nombre.insert(0, "Pan Integral de Centeno")
    inv.combo_crear_cat.set("canasta_basica")
    inv.entry_crear_precio.delete(0, tk.END)
    inv.entry_crear_precio.insert(0, "32.00")
    inv.entry_crear_costo.delete(0, tk.END)
    inv.entry_crear_costo.insert(0, "20.00")
    inv.entry_crear_stock.delete(0, tk.END)
    inv.entry_crear_stock.insert(0, "25")
    inv.entry_crear_stock_min.delete(0, tk.END)
    inv.entry_crear_stock_min.insert(0, "5")

    inv._crear_producto()
    assert inv.area_error_crear.tiene_error() is False
    assert "creado exitosamente" in inv.lbl_exito_crear.cget("text")

    # Editar el producto recién creado
    assert inv._producto_seleccionado is not None
    nuevo_id = inv._producto_seleccionado.id
    inv.entry_edit_precio.delete(0, tk.END)
    inv.entry_edit_precio.insert(0, "38.50")
    inv._guardar_edicion()

    assert inv.area_error_edit.tiene_error() is False
    assert "actualizado" in inv.lbl_exito_edit.cget("text")
    prod_bd = inventario_service.obtener_producto(nuevo_id, ui_app.sesion.conn)
    assert prod_bd.precio_venta == 38.50

    # Desactivar producto como Admin (Baja Lógica)
    inv._desactivar_producto()
    assert inv.area_error_edit.tiene_error() is False
    assert "desactivado" in inv.lbl_exito_edit.cget("text")
    assert inventario_service.obtener_producto(nuevo_id, ui_app.sesion.conn) is None

    # 2. Sesión como Vendedor (Botones de Admin se inhabilitan)
    ui_app.cerrar_sesion()
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "vendedor")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "vend123")
    login_frame._procesar_login()

    ui_app.navegar_a("inventario")
    assert str(inv.btn_guardar_crear["state"]) == "disabled"
    assert str(inv.btn_guardar_edit["state"]) == "disabled"
    assert str(inv.btn_desactivar["state"]) == "disabled"


def test_inventario_ajuste_stock_vendedor_y_admin_stepper_con_signo(ui_app):
    """
    Verifica el flujo de ajuste de stock (RS-05):
    - Habilitado para rol Vendedor (y Admin).
    - Combinación de dirección y magnitud entera con signo.
    - Rechazo delegado al backend en salidas que superan el stock.
    """
    ui_app.navegar_a("inventario")
    inv: PantallaInventario = ui_app.pantallas["inventario"]

    # El botón de ajuste de stock permanece SIEMPRE habilitado para vendedores
    assert str(inv.btn_confirmar_ajuste["state"]) == "normal"

    # Seleccionar Aceite Vegetal (Stock inicial = 50)
    items = inv.tree_catalogo.get_children()
    item_aceite = next(i for i in items if "Aceite" in inv.tree_catalogo.item(i, "values")[2])
    inv.tree_catalogo.selection_set(item_aceite)
    inv._on_producto_seleccionado()

    aceite_id = inv._producto_seleccionado.id
    stock_inicial = inv._producto_seleccionado.stock

    # 1. Ajuste de Entrada (+10)
    inv.var_direccion_ajuste.set("entrada")
    inv.spin_magnitud.set(10)
    inv._confirmar_ajuste_stock()

    assert inv.area_error_ajuste.tiene_error() is False
    assert inv._producto_seleccionado.stock == stock_inicial + 10

    # 2. Ajuste de Salida (-15)
    inv.var_direccion_ajuste.set("salida")
    inv.spin_magnitud.set(15)
    inv._confirmar_ajuste_stock()

    assert inv.area_error_ajuste.tiene_error() is False
    assert inv._producto_seleccionado.stock == stock_inicial + 10 - 15

    # 3. Ajuste de Salida que supera el stock -> Rechazo del backend
    inv.var_direccion_ajuste.set("salida")
    inv.spin_magnitud.set(999)
    inv._confirmar_ajuste_stock()

    assert inv.area_error_ajuste.tiene_error() is True
    assert "insuficiente" in inv.area_error_ajuste.lbl_texto.cget("text").lower()


def test_inventario_badge_global_y_resaltado_ambar_stock_bajo(ui_app):
    """
    Verifica:
    - Resaltado en fila ámbar (#fff3cd) cuando stock <= stock_minimo.
    - Badge global numérico en la cabecera.
    - Filtro de catálogo por solo productos en stock bajo.
    """
    ui_app.navegar_a("inventario")
    inv: PantallaInventario = ui_app.pantallas["inventario"]
    conn = ui_app.sesion.conn

    # Crear producto en alerta de stock (stock=2, stock_minimo=5)
    prod_alerta = inventario_service.crear_producto(
        nombre="Leche Deslactosada 1L",
        categoria="canasta_basica",
        precio_venta=28.0,
        costo=18.0,
        conn=conn,
        stock=2,
        stock_minimo=5,
    )

    inv._refrescar_todo(mantener_id=prod_alerta.id)

    # 1. Badge global refleja alertas activas
    assert "Stock Bajo" in inv.lbl_badge_alerta.cget("text")
    assert "0" not in inv.lbl_badge_alerta.cget("text")

    # 2. Resaltado en tag 'alerta_stock' (#fff3cd) en la fila del producto
    seleccion = inv.tree_catalogo.selection()
    assert seleccion
    tags_fila = inv.tree_catalogo.item(seleccion[0], "tags")
    assert "alerta_stock" in tags_fila

    # 3. Filtro por 'alerta'
    inv.var_filtro_stock.set("alerta")
    inv._filtrar_catalogo()

    filas_filtradas = inv.tree_catalogo.get_children()
    assert len(filas_filtradas) >= 1
    for f in filas_filtradas:
        assert "alerta_stock" in inv.tree_catalogo.item(f, "tags")

    # Restaurar filtro a 'todos'
    inv.var_filtro_stock.set("todos")
    inv._filtrar_catalogo()
    assert len(inv.tree_catalogo.get_children()) > len(filas_filtradas)


def test_reportes_bloqueo_reactivo_pestana_cartera_admin_vs_vendedor(ui_app):
    """
    Verifica que la Pestaña 2 (Cartera / CxC) se bloquee reactivamente en caliente
    para usuarios vendedores (state='disabled') y fuerce la selección a la Pestaña 1,
    mientras que para administradores conmute a state='normal'.
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    rep: PantallaReportes = ui_app.pantallas["reportes"]

    # 1. Sesión como Admin
    ui_app.navegar_a("login")
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    ui_app.navegar_a("reportes")
    # Para Admin, la pestaña de cartera debe estar habilitada
    assert str(rep.notebook.tab(rep.tab_cartera, "state")) == "normal"
    # Admin puede seleccionar la pestaña de cartera
    rep.notebook.select(rep.tab_cartera)
    assert rep.notebook.select() == str(rep.tab_cartera)

    # 2. Cierre de sesión y login como Vendedor
    ui_app.cerrar_sesion()
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "vendedor")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "vend123")
    login_frame._procesar_login()

    ui_app.navegar_a("reportes")
    # Para Vendedor, la pestaña de cartera debe bloquearse en caliente
    assert str(rep.notebook.tab(rep.tab_cartera, "state")) == "disabled"
    # La selección debe haberse forzado a la Pestaña 1 (Arqueo Diario)
    assert rep.notebook.select() == str(rep.tab_arqueo)


def test_reportes_arqueo_diario_calculo_caja_fisica_y_kpis(ui_app):
    """
    Verifica el cálculo y despliegue del Arqueo Diario (RF-REP-01):
    Fórmula de caja física: ventas_efectivo + anticipos_credito + abonos_cxc.
    """
    conn = ui_app.sesion.conn
    rep: PantallaReportes = ui_app.pantallas["reportes"]

    # Iniciar sesión como admin para registrar operaciones si es necesario
    if not ui_app.sesion.esta_autenticado:
        admin_user = Usuario(id=1, username="admin", nombre="Administrador", rol="admin", activo=True)
        ui_app.sesion.iniciar_sesion(admin_user)

    # Crear cliente para operaciones
    cli = cxc_service.crear_cliente(
        nombre="Cliente Prueba Arqueo",
        conn=conn,
        limite_credito=1500.0,
    )

    # Medir estado previo del día para aislar la prueba de tests anteriores en el mismo fixture
    datos_previos = reportes_service.obtener_arqueo_diario("now", conn)
    efectivo_ant = datos_previos["ventas_efectivo"]
    nequi_ant = datos_previos["ventas_nequi"]
    credito_ant = datos_previos["ventas_credito"]
    abonos_ant = datos_previos["abonos_cxc"]
    caja_ant = datos_previos["total_efectivo_en_caja"]

    # 1. Registrar venta contado en efectivo ($100.00)
    pos_service.registrar_venta(
        usuario_id=1,
        tipo_pago="efectivo",
        items=[pos_service.LineaVentaInput(cantidad=1.0, precio_unitario=100.0, descripcion="Venta Ef")],
        conn=conn,
        monto_pagado=100.0,
    )

    # 2. Registrar venta contado Nequi ($50.00)
    pos_service.registrar_venta(
        usuario_id=1,
        tipo_pago="nequi",
        items=[pos_service.LineaVentaInput(cantidad=1.0, precio_unitario=50.0, descripcion="Venta Nequi")],
        conn=conn,
        monto_pagado=50.0,
    )

    # 3. Registrar venta a crédito ($200.00 con anticipo de $60.00 en efectivo)
    pos_service.registrar_venta(
        usuario_id=1,
        tipo_pago="credito",
        items=[pos_service.LineaVentaInput(cantidad=1.0, precio_unitario=200.0, descripcion="Venta Cred")],
        conn=conn,
        cliente_id=cli.id,
        monto_pagado=60.0,
    )

    # 4. Registrar abono a cartera de $40.00 en efectivo
    cxc_service.registrar_abono(
        cliente_id=cli.id,
        monto=40.0,
        conn=conn,
        descripcion="Abono prueba arqueo",
    )

    # Efectivo esperado en caja física: anticipo ($60) + efectivo ($100) + abono ($40) = +$200.00
    ui_app.navegar_a("reportes")
    rep._establecer_fecha_hoy()

    assert f"${efectivo_ant + 100.0:,.2f}" in rep.lbl_kpi_v_efectivo.cget("text")
    assert f"${nequi_ant + 50.0:,.2f}" in rep.lbl_kpi_v_nequi.cget("text")
    assert f"${credito_ant + 140.0:,.2f}" in rep.lbl_kpi_v_credito.cget("text")  # 200 - 60 neto financiado
    assert f"${abonos_ant + 40.0:,.2f}" in rep.lbl_kpi_abonos.cget("text")
    assert f"${caja_ant + 200.0:,.2f}" in rep.lbl_kpi_total_caja.cget("text")

    # Verificar que el Treeview contiene las transacciones
    items_tree = rep.tree_arqueo.get_children()
    assert len(items_tree) >= 4


def test_reportes_consolidado_cartera_filtros_memoria_y_colores(ui_app):
    """
    Verifica el consolidado de cartera (RF-REP-02):
    - Carga de tarjetas de resumen por banda reutilizando COLORES_SCORING.
    - Filtros en memoria por clase y por rango de mora sin peticiones SQL adicionales.
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    rep: PantallaReportes = ui_app.pantallas["reportes"]

    # Iniciar sesión como Admin
    ui_app.navegar_a("login")
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "admin")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "admin123")
    login_frame._procesar_login()

    ui_app.navegar_a("reportes")
    rep.notebook.select(rep.tab_cartera)
    rep._cargar_consolidado_cartera()

    # Verificar tarjetas de banda
    assert "$" in rep.lbl_b_vigente.cget("text")
    assert "$" in rep.lbl_b_preventiva.cget("text")
    assert "$" in rep.lbl_b_congelada.cget("text")
    assert "$" in rep.lbl_b_critica.cget("text")
    assert "$" in rep.lbl_b_total.cget("text")

    # Verificar que existen deudores en caché
    assert len(rep._deudores_cache) >= 1

    # Filtro en memoria por Clase D
    rep.combo_filtro_clase.set("Clase D")
    rep._aplicar_filtros_cartera_en_memoria()
    for row in rep.tree_cartera.get_children():
        valores = rep.tree_cartera.item(row, "values")
        assert valores[3] == "D"  # Columna clase

    # Filtro en memoria por Mora
    rep.combo_filtro_clase.set("Todas")
    rep.combo_filtro_mora.set("> 10 días")
    rep._aplicar_filtros_cartera_en_memoria()
    for row in rep.tree_cartera.get_children():
        valores = rep.tree_cartera.item(row, "values")
        assert "días" in valores[2]

    # Restaurar filtros
    rep.combo_filtro_clase.set("Todas")
    rep.combo_filtro_mora.set("Todos")
    rep._aplicar_filtros_cartera_en_memoria()
    assert len(rep.tree_cartera.get_children()) == len(rep._deudores_cache)


def test_ui_pos_visualizacion_veto_r1(ui_app, crear_cliente_score_alto):
    """
    Verifica que en la pantalla POS, al seleccionar un cliente con veto R1
    (16 días de cargo pendiente -> 8 días de mora efectiva), la tarjeta de scoring
    muestre 'Veto R1: 8 días de mora' y 'Requiere abono previo >= 50%'.
    """
    conn = ui_app.sesion.conn
    cid = crear_cliente_score_alto(conn, dias_cargo_pendiente=16)
    cliente = cxc_service.obtener_cliente(cid, conn)

    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos.al_mostrar()

    etiqueta = f"{cliente.nombre} (ID: {cliente.id})"
    pos.combo_clientes.set(etiqueta)
    pos._on_cliente_seleccionado()

    texto_scoring = pos.lbl_card_scoring.cget("text")
    assert "Veto R1: 8 días de mora" in texto_scoring
    assert "Requiere abono previo >= 50%" in texto_scoring


def test_ui_perfil_cliente_visualizacion_veto_r1(ui_app, crear_cliente_score_alto):
    """
    Verifica que en la pantalla Perfil de Cliente, al cargar un cliente con veto R1,
    el desglose de factores muestre la transición 'Clase por puntaje: ... → Clase final: C (veto R1)'
    y el badge de clase refleje 'Clase C'.
    """
    conn = ui_app.sesion.conn
    cid = crear_cliente_score_alto(conn, dias_cargo_pendiente=16)

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cid)

    factores_texto = cxc_frame.lbl_factores.cget("text")
    assert "veto R1" in factores_texto
    assert "Clase final: C" in factores_texto
    assert "Clase C" in cxc_frame.lbl_badge_clase.cget("text")
    assert "Regla de veto R1" in cxc_frame.lbl_decision_accion.cget("text")


def test_ui_pos_cold_start_clase_c_sin_exigencia_abono(ui_app):
    """
    Verifica que en la pantalla POS, al seleccionar un cliente en cold-start con clase indicativa C,
    la tarjeta muestre 'Cold-start' y NO contenga 'Requiere abono previo'.
    """
    conn = ui_app.sesion.conn
    cliente = cxc_service.crear_cliente(
        nombre="Cliente CS Solo Apodo",
        nivel_vinculo="solo_apodo",
        conn=conn,
    )

    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos.al_mostrar()

    etiqueta = f"{cliente.nombre} (ID: {cliente.id})"
    pos.combo_clientes.set(etiqueta)
    pos._on_cliente_seleccionado()

    texto_scoring = pos.lbl_card_scoring.cget("text")
    assert "Cold-start" in texto_scoring
    assert "Requiere abono previo" not in texto_scoring


def test_perfil_cliente_asigna_plazo_quincenal_admin_y_bloqueo_vendedor(ui_app):
    """
    Verifica la asignación de plazo pactado (8 vs 15 días) desde la UI por un admin,
    la persistencia en BD y el bloqueo estricto del selector para el rol vendedor.
    """
    ui_app.geometry("1280x950")
    ui_app.deiconify()
    try:
        login_frame: PantallaLogin = ui_app.pantallas["login"]
        cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]

        # 1. Como Administrador
        ui_app.navegar_a("login")
        login_frame.entry_usuario.delete(0, tk.END)
        login_frame.entry_usuario.insert(0, "admin")
        login_frame.entry_password.delete(0, tk.END)
        login_frame.entry_password.insert(0, "admin123")
        login_frame._procesar_login()

        ui_app.navegar_a("cxc")
        ui_app.update()
        assert ui_app.sesion.es_admin is True
        assert str(cxc_frame.combo_plazo["state"]) == "readonly"
        assert not cxc_frame.lbl_solo_admin_cupo.winfo_ismapped()

        cliente_id = cxc_frame._cliente_actual.id
        cxc_frame.combo_plazo.set("15 días (quincenal)")
        cxc_frame.entry_nuevo_cupo.delete(0, tk.END)
        cxc_frame.entry_nuevo_cupo.insert(0, "40000")
        cxc_frame._asignar_cupo()

        assert cxc_frame.area_error_cupo.tiene_error() is False
        assert "plazo pactado de 15 días" in cxc_frame.lbl_exito_cupo.cget("text")
        cli_bd = cxc_service.obtener_cliente(cliente_id, ui_app.sesion.conn)
        assert cli_bd.plazo_pactado_dias == 15
        assert cli_bd.limite_credito == 40000.0

        # 2. Como Vendedor
        ui_app.cerrar_sesion()
        login_frame.entry_usuario.delete(0, tk.END)
        login_frame.entry_usuario.insert(0, "vendedor")
        login_frame.entry_password.delete(0, tk.END)
        login_frame.entry_password.insert(0, "vend123")
        login_frame._procesar_login()

        ui_app.navegar_a("cxc")
        ui_app.update()
        assert ui_app.sesion.es_admin is False
        assert str(cxc_frame.combo_plazo["state"]) == "disabled"
        assert cxc_frame.lbl_solo_admin_cupo.winfo_ismapped()
    finally:
        ui_app.geometry("1120x720")
        ui_app.withdraw()


def test_perfil_cliente_cold_start_muestra_plazo_del_cliente(ui_app):
    """
    Verifica que al cargar en Perfil de Cliente un cliente nuevo en cold-start (solo_apodo),
    la sugerencia de cupo muestre '$30,000' y 'plazo pactado de 8 días', y combo_plazo
    se precargue con '8 días (semanal)' (Matriz v2 §6).
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente CS Solo Apodo Plazo",
        nivel_vinculo="solo_apodo",
        conn=conn,
    )

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    sug_txt = cxc_frame.lbl_sugerencia_cupo.cget("text")
    assert "$30,000" in sug_txt
    assert "plazo pactado de 8 días" in sug_txt
    assert cxc_frame.combo_plazo.get() == "8 días (semanal)"


def test_pos_alta_cliente_desde_pos_queda_seleccionado(ui_app):
    """
    Verifica que al dar de alta un cliente desde el diálogo del POS (+ Nuevo),
    el cliente se cree en BD con cupo 0.0 y plazo 8, y quede inmediatamente seleccionado
    en el Combobox del POS con su tarjeta crediticia en estado Cold-start (RF-CXC-01, Wireframes v2).
    """
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos._abrir_dialogo_nuevo_cliente()
    dlg = pos._dialogo_nuevo_cliente

    dlg.entry_nombre.delete(0, tk.END)
    dlg.entry_nombre.insert(0, "Don Pepe Tienda Test")
    dlg.combo_vinculo.set("conocido_referido")
    dlg.guardar()

    clientes = cxc_service.buscar_clientes("Don Pepe Tienda Test", ui_app.sesion.conn)
    assert len(clientes) >= 1
    cli = clientes[0]
    assert cli.limite_credito == 0.0
    assert cli.plazo_pactado_dias == 8

    assert pos._cliente_actual is not None
    assert pos._cliente_actual.nombre == "Don Pepe Tienda Test"
    assert pos.combo_clientes.get() == f"Don Pepe Tienda Test (ID: {cli.id})"
    assert "Cold-start" in pos.lbl_card_scoring.cget("text")
    assert dlg.winfo_exists() == 0


def test_pos_alta_cliente_nombre_vacio_muestra_error(ui_app):
    """
    Verifica que el diálogo común de nuevo cliente valide nombre obligatorio:
    muestra error en AreaError, no cierra la ventana y no crea registros en BD.
    """
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos._abrir_dialogo_nuevo_cliente()
    dlg = pos._dialogo_nuevo_cliente

    total_antes = len(cxc_service.listar_clientes(ui_app.sesion.conn))

    dlg.entry_nombre.delete(0, tk.END)
    dlg.guardar()

    assert dlg.area_error.tiene_error() is True
    assert dlg.winfo_exists() == 1
    total_despues = len(cxc_service.listar_clientes(ui_app.sesion.conn))
    assert total_despues == total_antes

    dlg.destroy()


def test_pos_alta_cliente_permitida_a_vendedor(ui_app):
    """
    Verifica que el alta de clientes desde el POS esté disponible tanto para
    administradores como para el rol vendedor (matriz de permisos ERS).
    """
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    ui_app.cerrar_sesion()
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, "vendedor")
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, "vend123")
    login_frame._procesar_login()

    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    pos._abrir_dialogo_nuevo_cliente()
    dlg = pos._dialogo_nuevo_cliente

    dlg.entry_nombre.delete(0, tk.END)
    dlg.entry_nombre.insert(0, "Cliente Creado Por Vendedor")
    dlg.guardar()

    encontrados = cxc_service.buscar_clientes("Cliente Creado Por Vendedor", ui_app.sesion.conn)
    assert len(encontrados) >= 1
    assert encontrados[0].nombre == "Cliente Creado Por Vendedor"


def test_perfil_alta_cliente_usa_dialogo_comun(ui_app):
    """
    Verifica que la pantalla de Perfil de Cliente utilice la clase compartida DialogoNuevoCliente
    y cargue inmediatamente la ficha del cliente recién creado al guardar.
    """
    ui_app.navegar_a("cxc")
    cxc: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc._abrir_modal_nuevo_cliente()

    assert isinstance(cxc._dialogo_nuevo_cliente, DialogoNuevoCliente)
    dlg = cxc._dialogo_nuevo_cliente

    dlg.entry_nombre.delete(0, tk.END)
    dlg.entry_nombre.insert(0, "Cliente Perfil Dialogo")
    dlg.guardar()

    assert cxc._cliente_actual is not None
    assert cxc._cliente_actual.nombre == "Cliente Perfil Dialogo"


def test_perfil_historial_muestra_columna_cajero(ui_app):
    """
    Verifica que la pantalla de Perfil de Cliente muestre el nombre del cajero
    en la columna 'cajero' del historial de movimientos.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Vista Cajero",
        conn=conn,
        limite_credito=50000.0,
    )
    cxc_service.registrar_cargo(
        cliente_id=cli.id,
        monto=15000.0,
        conn=conn,
        usuario_id=1,
    )

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    children = cxc_frame.tree_historial.get_children()
    assert len(children) >= 1
    item = cxc_frame.tree_historial.item(children[0])
    valores = item["values"]
    assert valores[5] == "Administrador del Sistema"


def test_perfil_comprobante_usa_el_movimiento_seleccionado(ui_app, monkeypatch):
    """
    Verifica que al presionar el botón de comprobante se utilice estrictamente
    el ID del movimiento seleccionado en la tabla de historial.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Seleccion Comprobante",
        conn=conn,
        limite_credito=50000.0,
    )
    cargo = cxc_service.registrar_cargo(
        cliente_id=cli.id,
        monto=20000.0,
        conn=conn,
        usuario_id=1,
    )
    abono = cxc_service.registrar_abono(
        cliente_id=cli.id,
        monto=5000.0,
        conn=conn,
        usuario_id=1,
    )

    llamadas_pdf = []

    def mock_generar_pdf(movimiento_id, conn):
        llamadas_pdf.append(movimiento_id)
        return "comprobante_dummy.pdf"

    monkeypatch.setattr(reportes_service, "generar_comprobante_pdf", mock_generar_pdf)

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    monkeypatch.setattr(cxc_frame, "_abrir_pdf_sistema", lambda path: None)

    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    # Seleccionar primer movimiento (cargo)
    cxc_frame.tree_historial.selection_set(str(cargo.id))
    cxc_frame.btn_comprobante.invoke()
    assert llamadas_pdf == [cargo.id]

    # Seleccionar segundo movimiento (abono)
    cxc_frame.tree_historial.selection_set(str(abono.id))
    cxc_frame.btn_comprobante.invoke()
    assert llamadas_pdf == [cargo.id, abono.id]


def test_perfil_comprobante_sin_seleccion_no_genera_pdf(ui_app, monkeypatch):
    """
    Verifica que si no hay ninguna fila seleccionada en el historial,
    no se genere ningún PDF y se muestre el mensaje de error correspondiente.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Sin Seleccion",
        conn=conn,
        limite_credito=50000.0,
    )
    cxc_service.registrar_cargo(
        cliente_id=cli.id,
        monto=10000.0,
        conn=conn,
        usuario_id=1,
    )

    llamado = False

    def mock_generar_pdf(movimiento_id, conn):
        nonlocal llamado
        llamado = True
        return "dummy.pdf"

    monkeypatch.setattr(reportes_service, "generar_comprobante_pdf", mock_generar_pdf)

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    monkeypatch.setattr(cxc_frame, "_abrir_pdf_sistema", lambda path: None)

    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    # Deseleccionar cualquier fila
    for item in cxc_frame.tree_historial.selection():
        cxc_frame.tree_historial.selection_remove(item)

    cxc_frame.btn_comprobante.invoke()

    assert llamado is False
    assert cxc_frame.area_error_abono.tiene_error() is True
    assert (
        "Seleccione en el historial el movimiento del que quiere el comprobante."
        in cxc_frame.area_error_abono._mensaje_actual
    )


def test_perfil_abono_queda_seleccionado_para_comprobante(ui_app):
    """
    Verifica que al registrar un abono en el perfil de cliente,
    la fila recién agregada en el historial quede seleccionada y enfocada.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Abono Seleccionado",
        conn=conn,
        limite_credito=50000.0,
    )
    cxc_service.registrar_cargo(
        cliente_id=cli.id,
        monto=20000.0,
        conn=conn,
        usuario_id=1,
    )

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    cxc_frame.entry_monto_abono.delete(0, tk.END)
    cxc_frame.entry_monto_abono.insert(0, "5000.00")
    cxc_frame.entry_desc_abono.delete(0, tk.END)
    cxc_frame.entry_desc_abono.insert(0, "Abono para test de seleccion")

    cxc_frame.btn_registrar_abono.invoke()

    seleccion = cxc_frame.tree_historial.selection()
    assert len(seleccion) == 1
    hist = cxc_service.obtener_historial_cxc(cli.id, conn)
    abono_reciente = hist[-1]
    assert seleccion[0] == str(abono_reciente.id)


def _login_como(ui_app, username: str, password: str) -> None:
    login_frame: PantallaLogin = ui_app.pantallas["login"]
    ui_app.cerrar_sesion()
    login_frame.entry_usuario.delete(0, tk.END)
    login_frame.entry_usuario.insert(0, username)
    login_frame.entry_password.delete(0, tk.END)
    login_frame.entry_password.insert(0, password)
    login_frame._procesar_login()


def test_usuarios_admin_ve_panel_completo_y_crea_usuario(ui_app):
    """
    Verifica que el rol administrador tenga acceso al panel_admin completo
    y pueda dar de alta nuevos usuarios con visibilidad inmediata en el Treeview y persistencia en BD.
    """
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("usuarios")
    usuarios_frame: PantallaUsuarios = ui_app.pantallas["usuarios"]

    # panel_admin.grid_info() no está vacío
    assert bool(usuarios_frame.panel_admin.grid_info()) is True

    # Crea un usuario con nombre único
    username_unico = "user_admin_ui_test_01"
    usuarios_frame.entry_nuevo_username.delete(0, tk.END)
    usuarios_frame.entry_nuevo_username.insert(0, username_unico)
    usuarios_frame.entry_nuevo_nombre.delete(0, tk.END)
    usuarios_frame.entry_nuevo_nombre.insert(0, "Usuario Creado Desde UI")
    usuarios_frame.combo_nuevo_rol.set("vendedor")
    usuarios_frame.entry_nuevo_password.delete(0, tk.END)
    usuarios_frame.entry_nuevo_password.insert(0, "clave123456")

    usuarios_frame._crear_usuario()

    assert usuarios_frame.area_error_admin.tiene_error() is False
    assert "creado con éxito" in usuarios_frame.lbl_exito_admin.cget("text")

    # Aparece en la base de datos
    u_bd = auth_service.obtener_usuario_por_username(username_unico, ui_app.sesion.conn)
    assert u_bd is not None
    assert u_bd.nombre == "Usuario Creado Desde UI"
    assert u_bd.rol == "vendedor"

    # Aparece en el tree_usuarios
    hijos = usuarios_frame.tree_usuarios.get_children()
    assert str(u_bd.id) in hijos

    _login_como(ui_app, "admin", "admin123")


def test_usuarios_vendedor_solo_ve_cambio_de_password(ui_app):
    """
    Verifica que el rol vendedor solo tenga visible el panel de autoservicio de contraseña,
    con panel_admin completamente retirado de la cuadrícula.
    """
    _login_como(ui_app, "vendedor", "vend123")
    ui_app.navegar_a("usuarios")
    usuarios_frame: PantallaUsuarios = ui_app.pantallas["usuarios"]

    assert usuarios_frame.panel_admin.grid_info() == {}
    assert bool(usuarios_frame.panel_mi_password.grid_info()) is True

    _login_como(ui_app, "admin", "admin123")


def test_usuarios_permisos_reactivos_admin_luego_vendedor(ui_app):
    """
    Verifica que los permisos y visibilidad de paneles se ajusten reactivamente
    en la misma instancia de App al alternar entre admin y vendedor.
    """
    usuarios_frame: PantallaUsuarios = ui_app.pantallas["usuarios"]

    # 1. Sesión como Admin: panel visible
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("usuarios")
    assert bool(usuarios_frame.panel_admin.grid_info()) is True

    # 2. Cerrar sesión y entrar como Vendedor: panel oculto
    _login_como(ui_app, "vendedor", "vend123")
    ui_app.navegar_a("usuarios")
    assert usuarios_frame.panel_admin.grid_info() == {}
    assert bool(usuarios_frame.panel_mi_password.grid_info()) is True

    # Restaurar sesión admin
    _login_como(ui_app, "admin", "admin123")


def test_usuarios_ui_no_permite_desactivar_ultimo_admin(ui_app):
    """
    Verifica que la UI impida desactivar al último administrador activo,
    mostrando el error correspondiente y preservando el estado activo en la BD.
    """
    _login_como(ui_app, "admin", "admin123")
    conn = ui_app.sesion.conn

    # Si hay otros administradores activos creados por tests previos, desactivarlos para asegurar la condición
    cur = conn.cursor()
    cur.execute("SELECT id FROM usuarios WHERE rol = 'admin' AND activo = 1 AND id != 1")
    for r in cur.fetchall():
        auth_service.cambiar_estado_usuario(r["id"], False, conn)

    ui_app.navegar_a("usuarios")
    usuarios_frame: PantallaUsuarios = ui_app.pantallas["usuarios"]

    # Selecciona la fila del admin semilla (id 1)
    usuarios_frame.tree_usuarios.selection_set("1")
    usuarios_frame._cambiar_estado_seleccionado()

    assert usuarios_frame.area_error_admin.tiene_error() is True
    assert "último administrador activo" in usuarios_frame.area_error_admin._mensaje_actual

    admin_semilla = auth_service.obtener_usuario_por_id(1, conn)
    assert admin_semilla.activo is True

    _login_como(ui_app, "admin", "admin123")


def test_usuarios_cambiar_mi_password_confirmacion_y_exito(ui_app):
    """
    Verifica la validación de coincidencia de contraseña nueva y confirmación,
    así como el cambio exitoso de contraseña para el usuario en sesión.
    """
    conn = ui_app.sesion.conn
    username_test = "pw_test_ui_user_unique"
    auth_service.crear_usuario(
        username=username_test,
        password="clave_ui_1",
        nombre="Usuario Test PW UI",
        rol="vendedor",
        conn=conn,
    )

    _login_como(ui_app, username_test, "clave_ui_1")
    ui_app.navegar_a("usuarios")
    usuarios_frame: PantallaUsuarios = ui_app.pantallas["usuarios"]

    # 1. Nueva contraseña y confirmación no coinciden
    usuarios_frame.entry_pw_actual.delete(0, tk.END)
    usuarios_frame.entry_pw_actual.insert(0, "clave_ui_1")
    usuarios_frame.entry_pw_nueva.delete(0, tk.END)
    usuarios_frame.entry_pw_nueva.insert(0, "clave_ui_2")
    usuarios_frame.entry_pw_confirmar.delete(0, tk.END)
    usuarios_frame.entry_pw_confirmar.insert(0, "clave_ui_distinta")

    usuarios_frame._cambiar_mi_password()

    assert usuarios_frame.area_error_mi_password.tiene_error() is True
    assert "no coinciden" in usuarios_frame.area_error_mi_password._mensaje_actual
    assert auth_service.autenticar_usuario(username_test, "clave_ui_1", conn) is not None

    # 2. Flujo correcto con confirmación idéntica
    usuarios_frame.entry_pw_confirmar.delete(0, tk.END)
    usuarios_frame.entry_pw_confirmar.insert(0, "clave_ui_2")

    usuarios_frame._cambiar_mi_password()

    assert usuarios_frame.area_error_mi_password.tiene_error() is False
    assert "actualizada con éxito" in usuarios_frame.lbl_exito_mi_password.cget("text")
    assert auth_service.autenticar_usuario(username_test, "clave_ui_2", conn) is not None
    assert auth_service.autenticar_usuario(username_test, "clave_ui_1", conn) is None

    # Restaurar sesión admin
    _login_como(ui_app, "admin", "admin123")


def test_perfil_historial_muestra_no_registrado(ui_app):
    """
    Verifica que en el historial de la ficha del cliente, si un movimiento no tiene usuario_id
    registrado (None), la columna Cajero muestre 'No registrado'.
    """
    conn = ui_app.sesion.conn
    cli = cxc_service.crear_cliente(
        nombre="Cliente Sin Cajero Registrado",
        conn=conn,
        limite_credito=30000.0,
    )
    cxc_service.registrar_cargo(
        cliente_id=cli.id,
        monto=5000.0,
        conn=conn,
        usuario_id=None,
    )

    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    children = cxc_frame.tree_historial.get_children()
    assert len(children) >= 1
    item = cxc_frame.tree_historial.item(children[0])
    valores = item["values"]
    assert valores[5] == "No registrado"

    _login_como(ui_app, "admin", "admin123")


def test_perfil_sugerencia_20_pct_solo_se_aplica_al_confirmar(ui_app, crear_cliente_score_alto):
    """
    Verifica que la sugerencia de aumento de cupo (+20%) para clientes Clase A
    se muestre de manera informativa y solo se aplique a la BD cuando el administrador confirma.
    """
    conn = ui_app.sesion.conn
    cid = crear_cliente_score_alto(conn)
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cid)

    assert "20 %" in cxc_frame.lbl_sugerencia_cupo.cget("text")
    assert cxc_frame.entry_nuevo_cupo.get() == "600000.00"

    # Verificar que en BD sigue en 500.000 antes de confirmar
    cur = conn.cursor()
    cur.execute("SELECT limite_credito FROM clientes WHERE id = ?", (cid,))
    assert cur.fetchone()["limite_credito"] == 500000.0

    # Confirmar cupo
    cxc_frame._asignar_cupo()
    cur.execute("SELECT limite_credito FROM clientes WHERE id = ?", (cid,))
    assert cur.fetchone()["limite_credito"] == 600000.0

    _login_como(ui_app, "admin", "admin123")


def test_pos_enter_con_codigo_exacto_agrega(ui_app):
    """
    Verifica que al presionar Enter con un código de barras exacto, el producto
    se agregue directamente al carrito en una sola interacción (RF-POS-01).
    """
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    pos_frame: PantallaPOS = ui_app.pantallas["pos"]
    pos_frame._vaciar_carrito()

    pos_frame.entry_busqueda_prod.delete(0, tk.END)
    pos_frame.entry_busqueda_prod.insert(0, "7501000100011")
    pos_frame._on_enter_busqueda()

    assert len(pos_frame._carrito) == 1
    assert pos_frame._carrito[0]["descripcion"] == "Arroz Superior 1kg"
    assert pos_frame.entry_busqueda_prod.get() == ""
    assert len(pos_frame.tree_catalogo.get_children()) >= 3

    _login_como(ui_app, "admin", "admin123")


def test_pos_enter_con_nombre_unico_agrega(ui_app):
    """
    Verifica que al ingresar el nombre exacto de un producto con resultado único
    y presionar Enter, se agregue al carrito directamente.
    """
    conn = ui_app.sesion.conn
    prod = inventario_service.crear_producto(
        nombre="Panela Unica Test 7",
        categoria="canasta_basica",
        precio_venta=3500.0,
        costo=2500.0,
        conn=conn,
        stock=20,
    )
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    pos_frame: PantallaPOS = ui_app.pantallas["pos"]
    pos_frame._vaciar_carrito()

    pos_frame.entry_busqueda_prod.delete(0, tk.END)
    pos_frame.entry_busqueda_prod.insert(0, "Panela Unica Test 7")
    pos_frame._on_enter_busqueda()

    assert len(pos_frame._carrito) == 1
    assert pos_frame._carrito[0]["producto_id"] == prod.id
    assert pos_frame._carrito[0]["descripcion"] == "Panela Unica Test 7"

    _login_como(ui_app, "admin", "admin123")


def test_pos_enter_con_varios_resultados_solo_filtra(ui_app):
    """
    Verifica que si la búsqueda arroja 2 o más resultados coincidentes, Enter
    solamente filtre el catálogo visual sin agregar ítems al carrito.
    """
    conn = ui_app.sesion.conn
    inventario_service.crear_producto(
        nombre="Galleta Test Siete Uno",
        categoria="canasta_basica",
        precio_venta=1200.0,
        costo=800.0,
        conn=conn,
        stock=15,
    )
    inventario_service.crear_producto(
        nombre="Galleta Test Siete Dos",
        categoria="canasta_basica",
        precio_venta=1500.0,
        costo=1000.0,
        conn=conn,
        stock=15,
    )
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    pos_frame: PantallaPOS = ui_app.pantallas["pos"]
    pos_frame._vaciar_carrito()
    carrito_antes = len(pos_frame._carrito)

    pos_frame.entry_busqueda_prod.delete(0, tk.END)
    pos_frame.entry_busqueda_prod.insert(0, "Galleta Test Siete")
    pos_frame._on_enter_busqueda()

    assert len(pos_frame._carrito) == carrito_antes
    assert len(pos_frame.tree_catalogo.get_children()) == 2

    _login_como(ui_app, "admin", "admin123")


def test_pos_enter_sin_resultados_muestra_error(ui_app):
    """
    Verifica que al no encontrar ningún producto coincidente con el término,
    se muestre el mensaje de error en AreaError y el carrito permanezca intacto.
    """
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    pos_frame: PantallaPOS = ui_app.pantallas["pos"]
    pos_frame._vaciar_carrito()
    carrito_antes = len(pos_frame._carrito)

    pos_frame.entry_busqueda_prod.delete(0, tk.END)
    pos_frame.entry_busqueda_prod.insert(0, "zzz_no_existe")
    pos_frame._on_enter_busqueda()

    assert len(pos_frame._carrito) == carrito_antes
    assert pos_frame.area_error.tiene_error() is True
    assert "No se encontró" in pos_frame.area_error._mensaje_actual

    _login_como(ui_app, "admin", "admin123")


def test_pos_enter_codigo_de_producto_inactivo_no_agrega(ui_app):
    """
    Verifica que el código de barras de un producto inactivo no permita agregarlo al carrito.
    """
    conn = ui_app.sesion.conn
    codigo_inactivo = "9998887770001"
    prod = inventario_service.crear_producto(
        nombre="Producto Inactivo Barcode",
        categoria="canasta_basica",
        precio_venta=2000.0,
        costo=1500.0,
        codigo_barras=codigo_inactivo,
        conn=conn,
        stock=10,
    )
    inventario_service.desactivar_producto(prod.id, conn)

    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    pos_frame: PantallaPOS = ui_app.pantallas["pos"]
    pos_frame._vaciar_carrito()
    carrito_antes = len(pos_frame._carrito)

    pos_frame.entry_busqueda_prod.delete(0, tk.END)
    pos_frame.entry_busqueda_prod.insert(0, codigo_inactivo)
    pos_frame._on_enter_busqueda()

    assert len(pos_frame._carrito) == carrito_antes

    _login_como(ui_app, "admin", "admin123")


def test_perfil_historial_muestra_hora_local(ui_app):
    """
    Verifica que en la pantalla de Perfil de Cliente la columna de fecha
    en el historial de CxC muestre la fecha convertida a la hora local del sistema.
    """
    conn = ui_app.sesion.conn
    dt_local = datetime(2026, 10, 13, 20, 0, 0)
    dt_utc = dt_local.astimezone(timezone.utc)
    fecha_utc_txt = dt_utc.strftime("%Y-%m-%d %H:%M:%S")

    cli = cxc_service.crear_cliente(
        nombre="Cliente Historial Hora Local",
        conn=conn,
        limite_credito=100000.0,
    )

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento, descripcion, usuario_id)
        VALUES (?, 'cargo', 25000.0, 25000.0, ?, 'Cargo prueba hora local', 1)
    """, (cli.id, fecha_utc_txt))
    cargo_id = cur.lastrowid
    cur.execute("UPDATE clientes SET saldo_actual = 25000.0 WHERE id = ?", (cli.id,))
    conn.commit()

    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli.id)

    item = cxc_frame.tree_historial.item(str(cargo_id))
    valores = item["values"]
    assert valores[1] == "2026-10-13 20:00:00"

    _login_como(ui_app, "admin", "admin123")


def test_perfil_muestra_explicacion_clase(ui_app, crear_cliente_score_alto):
    """
    Verifica que en el perfil de cliente se muestre la explicación de la clase en lbl_explicacion_clase
    para clientes en cold-start, con veto R1 y en caso normal fuera de cold-start.
    """
    conn = ui_app.sesion.conn

    # 1. Cliente nuevo en cold-start
    cli_nuevo = cxc_service.crear_cliente(
        nombre="Cliente Explicacion UI Cold",
        nivel_vinculo="conocido_referido",
        conn=conn,
    )

    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    cxc_frame._cargar_selector_clientes(mantener_id=cli_nuevo.id)

    texto_nuevo = cxc_frame.lbl_explicacion_clase.cget("text")
    assert texto_nuevo.startswith("Cliente nuevo")

    # 2. Cliente con regla de veto R1
    cid_veto = crear_cliente_score_alto(conn, dias_cargo_pendiente=16)
    cxc_frame._cargar_selector_clientes(mantener_id=cid_veto)

    texto_veto = cxc_frame.lbl_explicacion_clase.cget("text")
    assert texto_veto.startswith("Clase C por regla R1")

    # 3. Cliente sin veto y fuera de cold-start (cargo pendiente dentro del plazo: 2 días)
    cid_normal = crear_cliente_score_alto(conn, dias_cargo_pendiente=2)
    cxc_frame._cargar_selector_clientes(mantener_id=cid_normal)

    texto_normal = cxc_frame.lbl_explicacion_clase.cget("text")
    assert texto_normal.startswith("Clase ")
    assert "puntaje" in texto_normal
    assert "Cliente nuevo" not in texto_normal

    _login_como(ui_app, "admin", "admin123")


def test_vencimiento_en_cartera_y_perfil(ui_app, crear_cliente_score_alto):
    """
    Verifica que la fecha y días de vencimiento aparezcan correctamente en la
    Treeview de Cartera y en la tarjeta de cupo del Perfil de Cliente.
    """
    conn = ui_app.sesion.conn
    _login_como(ui_app, "admin", "admin123")

    # 1. Cliente deudor (cargo pendiente de 5 días, plazo 8)
    cid_deudor = crear_cliente_score_alto(conn, dias_cargo_pendiente=5)

    # 2. Cliente sin deuda
    cid_sin_deuda = crear_cliente_score_alto(conn, dias_cargo_pendiente=None)

    # A) Pantalla de Reportes / Cartera
    ui_app.navegar_a("reportes")
    rep = ui_app.pantallas["reportes"]
    rep.notebook.select(rep.tab_cartera)
    rep._cargar_consolidado_cartera()

    # Comprobar que en tree_cartera existe la columna 'vence'
    cols = rep.tree_cartera["columns"]
    assert "vence" in cols
    assert cols[-1] == "vence"

    # Encontrar al deudor en tree_cartera
    items = rep.tree_cartera.get_children()
    fila_deudor = None
    for item in items:
        vals = rep.tree_cartera.item(item, "values")
        if "Cliente Alto 5" in vals[0]:
            fila_deudor = vals
            break
    assert fila_deudor is not None, "El deudor debe figurar en la cartera"
    texto_vence_cartera = fila_deudor[-1]
    assert any(sub in texto_vence_cartera for sub in ("faltan", "vence hoy", "vencido"))

    # B) Pantalla de Perfil de Cliente (CxC)
    ui_app.navegar_a("cxc")
    cxc_frame = ui_app.pantallas["cxc"]

    # Deudor en Perfil
    cxc_frame._cargar_selector_clientes(mantener_id=cid_deudor)
    txt_venc_perfil = cxc_frame.lbl_vencimiento.cget("text")
    assert txt_venc_perfil.startswith("Próximo vencimiento:")
    assert any(sub in txt_venc_perfil for sub in ("faltan", "vence hoy", "vencido"))

    # Cliente sin deuda en Perfil
    cxc_frame._cargar_selector_clientes(mantener_id=cid_sin_deuda)
    txt_venc_sin_deuda = cxc_frame.lbl_vencimiento.cget("text")
    assert txt_venc_sin_deuda == "Sin saldo pendiente"

    _login_como(ui_app, "admin", "admin123")


def test_barra_cerrar_sesion_visible_en_ventana_pequena(ui_app):
    """
    Verifica que en el tamaño mínimo de la ventana, el botón 'Cerrar sesión'
    se mantenga visible, completamente mapeado y contenido dentro del borde derecho.
    Verifica además la coherencia del modo compacto.
    """
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")

    geom_original = ui_app.geometry()
    min_w, min_h = ui_app.minsize()

    if sys.platform == "win32":
        try:
            ui_app.state("normal")
        except Exception:
            pass

    ui_app.deiconify()
    ui_app.geometry(f"{min_w}x{min_h}")
    ui_app.update()

    barra = ui_app.barra_superior
    btn_logout = barra.btn_logout

    # Verificar que el botón de cerrar sesión está mapeado
    assert btn_logout.winfo_ismapped() == 1

    # Borde derecho del botón vs borde derecho de la ventana
    borde_derecho_btn = btn_logout.winfo_rootx() + btn_logout.winfo_width()
    borde_derecho_ventana = ui_app.winfo_rootx() + ui_app.winfo_width()
    assert borde_derecho_btn <= borde_derecho_ventana

    # Coherencia del modo compacto
    if barra.es_compacto:
        assert "Administrador" in barra.lbl_usuario.cget("text")

    # Restaurar estado y tamaño original
    barra.aplicar_modo_compacto(False)
    ui_app.geometry(geom_original)
    ui_app.withdraw()
    ui_app.update()
    _login_como(ui_app, "admin", "admin123")


def test_barra_modo_compacto_restaura_textos(ui_app):
    """
    Verifica que al alternar manualmente el modo compacto, los textos completos
    originales de los botones de navegación, el título y lbl_usuario se restauren exactamente.
    """
    _login_como(ui_app, "admin", "admin123")
    ui_app.navegar_a("pos")
    barra = ui_app.barra_superior
    barra.aplicar_modo_compacto(False)

    # Guardar textos originales
    titulo_orig = barra.lbl_titulo.cget("text")
    usuario_orig = barra.lbl_usuario.cget("text")
    nav_orig = {
        barra.btn_pos: barra.btn_pos.cget("text"),
        barra.btn_cxc: barra.btn_cxc.cget("text"),
        barra.btn_inv: barra.btn_inv.cget("text"),
        barra.btn_rep: barra.btn_rep.cget("text"),
        barra.btn_usuarios: barra.btn_usuarios.cget("text"),
    }

    # Aplicar modo compacto
    barra.aplicar_modo_compacto(True)
    assert barra.es_compacto is True
    assert barra.lbl_titulo.cget("text") == "Mi Tienda"
    assert barra.btn_pos.cget("text") == "POS"
    assert barra.btn_cxc.cget("text") == "Clientes"
    assert barra.btn_inv.cget("text") == "Inventario"
    assert barra.btn_rep.cget("text") == "Reportes"
    assert barra.btn_usuarios.cget("text") == "Usuarios"
    assert "Administrador" in barra.lbl_usuario.cget("text")

    # Restaurar modo completo
    barra.aplicar_modo_compacto(False)
    assert barra.es_compacto is False
    assert barra.lbl_titulo.cget("text") == titulo_orig
    assert barra.lbl_usuario.cget("text") == usuario_orig
    for btn, txt in nav_orig.items():
        assert btn.cget("text") == txt

    _login_como(ui_app, "admin", "admin123")


def test_perfil_cupo_alcanzable_en_ventana_pequena(ui_app):
    """
    Verifica que en el tamaño mínimo real (ui_app.minsize()), con un cliente cargado,
    la sección de asignación de cupo (btn_asignar_cupo) quede visible dentro del canvas
    tras desplazar marco_izq al final.
    """
    ui_app.deiconify()
    geom_original = ui_app.geometry()
    try:
        _login_como(ui_app, "admin", "admin123")
        ui_app.navegar_a("cxc")
        cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]

        # Cargar un cliente si no hay uno cargado
        if cxc_frame._cliente_actual is None:
            primer_id = next(iter(cxc_frame._clientes_map.values()), 1)
            cxc_frame._cargar_ficha_cliente(primer_id)
        ui_app.update()

        min_w, min_h = ui_app.minsize()
        ui_app.geometry(f"{min_w}x{min_h}")
        ui_app.update()

        assert hasattr(cxc_frame, "marco_izq")
        assert isinstance(cxc_frame.marco_izq, MarcoDesplazable)

        # Desplazar al final
        cxc_frame.marco_izq.desplazar_al_final()
        ui_app.update()

        btn_top = cxc_frame.btn_asignar_cupo.winfo_rooty()
        btn_bottom = btn_top + cxc_frame.btn_asignar_cupo.winfo_height()
        canvas_top = cxc_frame.marco_izq.canvas.winfo_rooty()
        canvas_bottom = canvas_top + cxc_frame.marco_izq.canvas.winfo_height()

        assert btn_bottom <= canvas_bottom
        assert btn_top >= canvas_top
    finally:
        ui_app.geometry(geom_original)
        ui_app.withdraw()
        ui_app.update()


def test_perfil_textos_usan_el_ancho_disponible(ui_app):
    """
    En el tamaño mínimo de ventana, comprueba que:
    - lbl_explicacion_clase.cget('wraplength') sea >= 60% del ancho de card_scoring.
    - El ancho de marco_izq esté entre 0.8 y 1.25 veces el ancho de la columna derecha (col_der).
    """
    ui_app.deiconify()
    geom_original = ui_app.geometry()
    try:
        _login_como(ui_app, "admin", "admin123")
        ui_app.navegar_a("cxc")
        cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]

        if cxc_frame._cliente_actual is None:
            primer_id = next(iter(cxc_frame._clientes_map.values()), 1)
            cxc_frame._cargar_ficha_cliente(primer_id)

        min_w, min_h = ui_app.minsize()
        ui_app.geometry(f"{min_w}x{min_h}")
        ui_app.update()

        wrap = int(cxc_frame.lbl_explicacion_clase.cget("wraplength"))
        ancho_card = cxc_frame.card_scoring.winfo_width()
        assert wrap >= 0.60 * ancho_card

        ancho_izq = cxc_frame.marco_izq.winfo_width()
        ancho_der = cxc_frame.col_der.winfo_width()
        ratio = ancho_izq / ancho_der
        assert 0.80 <= ratio <= 1.25
    finally:
        ui_app.geometry(geom_original)
        ui_app.withdraw()
        ui_app.update()


def test_tablas_con_columnas_estirables(ui_app):
    """
    Verifica que las tablas principales (tree_historial, tree_cartera, tree_arqueo)
    cuenten con barras de desplazamiento horizontal expuestas y que sus columnas
    estén configuradas con estiramiento (stretch=True) y minwidth >= ancho medido de su encabezado.
    """
    ui_app.deiconify()
    _login_como(ui_app, "admin", "admin123")
    fuente_enc = font.Font(font=FUENTE_BASE_BOLD)

    # 1. Perfil del cliente: tree_historial
    ui_app.navegar_a("cxc")
    cxc_frame: PantallaPerfilCliente = ui_app.pantallas["cxc"]
    ui_app.update()
    assert hasattr(cxc_frame, "scroll_h_historial")
    assert cxc_frame.scroll_h_historial.winfo_exists()
    for col in cxc_frame.tree_historial["columns"]:
        col_info = cxc_frame.tree_historial.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(cxc_frame.tree_historial.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)

    # 2. Reportes: tree_cartera y tree_arqueo
    ui_app.navegar_a("reportes")
    rep_frame: PantallaReportes = ui_app.pantallas["reportes"]
    ui_app.update()

    assert hasattr(rep_frame, "scroll_h_cartera")
    assert rep_frame.scroll_h_cartera.winfo_exists()
    for col in rep_frame.tree_cartera["columns"]:
        col_info = rep_frame.tree_cartera.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(rep_frame.tree_cartera.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)

    assert hasattr(rep_frame, "scroll_h_arqueo")
    assert rep_frame.scroll_h_arqueo.winfo_exists()
    for col in rep_frame.tree_arqueo["columns"]:
        col_info = rep_frame.tree_arqueo.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(rep_frame.tree_arqueo.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)


def _dentro_de(widget, contenedor):
    return (widget.winfo_rootx() >= contenedor.winfo_rootx()
            and widget.winfo_rooty() >= contenedor.winfo_rooty()
            and widget.winfo_rootx() + widget.winfo_width() <= contenedor.winfo_rootx() + contenedor.winfo_width()
            and widget.winfo_rooty() + widget.winfo_height() <= contenedor.winfo_rooty() + contenedor.winfo_height())


def test_pos_controles_visibles_en_ventana_minima(ui_app):
    """
    Verifica que en el tamaño mínimo real de la aplicación, los controles esenciales
    (btn_agregar_cat, btn_agregar_monto, btn_confirmar_venta y r_credito en canvas)
    estén mapeados y contenidos en los límites visibles.
    """
    ui_app.deiconify()
    _login_como(ui_app, "admin", "admin123")
    min_w, min_h = ui_app.minsize()
    geom_orig = ui_app.geometry()
    ui_app.geometry(f"{min_w}x{min_h}")
    ui_app.navegar_a("pos")
    ui_app.update()

    pos: PantallaPOS = ui_app.pantallas["pos"]
    try:
        assert pos.btn_agregar_cat.winfo_ismapped()
        assert _dentro_de(pos.btn_agregar_cat, ui_app)

        assert pos.btn_agregar_monto.winfo_ismapped()
        assert _dentro_de(pos.btn_agregar_monto, ui_app)

        assert pos.btn_confirmar_venta.winfo_ismapped()
        assert _dentro_de(pos.btn_confirmar_venta, ui_app)

        assert _dentro_de(pos.r_credito, pos.marco_der_pos.canvas)

        pos.var_tipo_pago.set("credito")
        pos._on_tipo_pago_cambiado()
        ui_app.update()

        assert _dentro_de(pos.btn_confirmar_venta, ui_app)
    finally:
        pos.var_tipo_pago.set("efectivo")
        pos._on_tipo_pago_cambiado()
        ui_app.geometry(geom_orig)
        ui_app.withdraw()
        ui_app.update()


def test_inventario_controles_visibles_en_ventana_minima(ui_app):
    """
    Verifica que en el tamaño mínimo real, los radiobuttons de filtro estén dentro de
    ui_app y que tras desplazar al final el marco desplazable de detalle, el botón
    btn_desactivar quede dentro del canvas visible.
    """
    ui_app.deiconify()
    _login_como(ui_app, "admin", "admin123")
    min_w, min_h = ui_app.minsize()
    geom_orig = ui_app.geometry()
    ui_app.geometry(f"{min_w}x{min_h}")
    ui_app.navegar_a("inventario")
    ui_app.update()

    inv: PantallaInventario = ui_app.pantallas["inventario"]
    try:
        assert _dentro_de(inv.r_todos, ui_app)
        assert _dentro_de(inv.r_alerta, ui_app)

        inv.marco_der_inv.desplazar_al_final()
        ui_app.update()

        assert _dentro_de(inv.btn_desactivar, inv.marco_der_inv.canvas)
    finally:
        ui_app.geometry(geom_orig)
        ui_app.withdraw()
        ui_app.update()


def test_dialogo_nuevo_cliente_se_ajusta_al_contenido(ui_app):
    """
    Verifica que con la aplicación en su tamaño mínimo real, al abrir DialogoNuevoCliente,
    los controles btn_crear y entry_nombre queden contenidos dentro del diálogo.
    """
    ui_app.deiconify()
    _login_como(ui_app, "admin", "admin123")
    min_w, min_h = ui_app.minsize()
    geom_orig = ui_app.geometry()
    ui_app.geometry(f"{min_w}x{min_h}")
    ui_app.update()

    dlg = DialogoNuevoCliente(ui_app, ui_app.sesion.conn, None)
    ui_app.update()
    try:
        assert _dentro_de(dlg.btn_crear, dlg)
        assert _dentro_de(dlg.entry_nombre, dlg)
    finally:
        dlg.destroy()
        ui_app.geometry(geom_orig)
        ui_app.withdraw()
        ui_app.update()


def test_tablas_pos_inventario_usuarios_estirables(ui_app):
    """
    Verifica que las tablas de POS (catálogo y carrito), Inventario (catálogo maestro)
    y Usuarios (catálogo de usuarios) dispongan de barras de desplazamiento horizontal
    y sus columnas tengan stretch=True y minwidth mayor a cero.
    """
    ui_app.deiconify()
    _login_como(ui_app, "admin", "admin123")
    fuente_enc = font.Font(font=FUENTE_BASE_BOLD)

    # 1. POS: tree_catalogo y tree_carrito
    ui_app.navegar_a("pos")
    pos: PantallaPOS = ui_app.pantallas["pos"]
    ui_app.update()

    assert hasattr(pos, "scroll_h_catalogo_pos")
    assert pos.scroll_h_catalogo_pos.winfo_exists()
    for col in pos.tree_catalogo["columns"]:
        col_info = pos.tree_catalogo.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(pos.tree_catalogo.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)

    assert hasattr(pos, "scroll_h_carrito")
    assert pos.scroll_h_carrito.winfo_exists()
    for col in pos.tree_carrito["columns"]:
        col_info = pos.tree_carrito.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(pos.tree_carrito.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)

    # 2. Inventario: tree_catalogo
    ui_app.navegar_a("inventario")
    inv: PantallaInventario = ui_app.pantallas["inventario"]
    ui_app.update()

    assert hasattr(inv, "scroll_h_catalogo_inv")
    assert inv.scroll_h_catalogo_inv.winfo_exists()
    for col in inv.tree_catalogo["columns"]:
        col_info = inv.tree_catalogo.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(inv.tree_catalogo.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)

    # 3. Usuarios: tree_usuarios
    ui_app.navegar_a("usuarios")
    usr: PantallaUsuarios = ui_app.pantallas["usuarios"]
    ui_app.update()

    assert hasattr(usr, "scroll_h_usuarios")
    assert usr.scroll_h_usuarios.winfo_exists()
    for col in usr.tree_usuarios["columns"]:
        col_info = usr.tree_usuarios.column(col)
        assert bool(col_info["stretch"]) is True
        assert col_info["minwidth"] > 0
        txt = str(usr.tree_usuarios.heading(col, "text") or "")
        if txt:
            assert col_info["minwidth"] >= fuente_enc.measure(txt)


def test_contrasena_inicial_obliga_a_cambiarla(ui_app):
    """
    Verifica que al iniciar sesión con la contraseña inicial 'tienda123',
    el sistema exija obligatoriamente el cambio de clave redirigiendo a la pantalla
    'usuarios', impidiendo navegar a otras pantallas hasta actualizarla con éxito.
    Verifica además que las credenciales regulares (admin/admin123) no exijan dicho cambio.
    """
    conn = ui_app.sesion.conn
    username_test = "admin_tienda_inicial_test"
    auth_service.crear_usuario(
        username=username_test,
        password="tienda123",
        nombre="Admin Tienda Test",
        conn=conn,
        rol="admin",
    )

    try:
        ui_app.deiconify()
        # 1. Login con contraseña inicial
        _login_como(ui_app, username_test, "tienda123")
        ui_app.update()

        assert ui_app.sesion.esta_autenticado is True
        assert ui_app.sesion.debe_cambiar_password is True

        usr: PantallaUsuarios = ui_app.pantallas["usuarios"]
        pos: PantallaPOS = ui_app.pantallas["pos"]
        assert ui_app.pantalla_actual == "usuarios"
        assert ui_app.contenedor.winfo_children()[-1] == usr
        assert usr.lbl_aviso_seguridad.winfo_ismapped()
        assert "Por seguridad, cambie la contraseña inicial antes de continuar." in usr.lbl_aviso_seguridad.cget("text")

        # 2. Intentar navegar a POS -> Bloqueado, se mantiene en usuarios
        ui_app.navegar_a("pos")
        ui_app.update()

        assert ui_app.pantalla_actual == "usuarios"
        assert ui_app.contenedor.winfo_children()[-1] == usr
        assert usr.lbl_aviso_seguridad.winfo_ismapped()

        # Intentar cambiar a la misma contraseña inicial "tienda123" -> Rechazado
        usr.entry_pw_actual.delete(0, tk.END)
        usr.entry_pw_actual.insert(0, "tienda123")
        usr.entry_pw_nueva.delete(0, tk.END)
        usr.entry_pw_nueva.insert(0, "tienda123")
        usr.entry_pw_confirmar.delete(0, tk.END)
        usr.entry_pw_confirmar.insert(0, "tienda123")
        usr._cambiar_mi_password()
        ui_app.update()

        assert usr.area_error_mi_password.tiene_error() is True
        assert usr.area_error_mi_password.winfo_ismapped()
        assert "La nueva contraseña no puede ser la contraseña inicial." in usr.area_error_mi_password.lbl_texto.cget("text")
        assert ui_app.sesion.debe_cambiar_password is True
        assert ui_app.pantalla_actual == "usuarios"

        # 3. Cambiar la contraseña a una válida
        usr.entry_pw_actual.delete(0, tk.END)
        usr.entry_pw_actual.insert(0, "tienda123")
        usr.entry_pw_nueva.delete(0, tk.END)
        usr.entry_pw_nueva.insert(0, "tienda456")
        usr.entry_pw_confirmar.delete(0, tk.END)
        usr.entry_pw_confirmar.insert(0, "tienda456")
        usr._cambiar_mi_password()
        ui_app.update()

        assert ui_app.sesion.debe_cambiar_password is False
        assert ui_app.pantalla_actual == "pos"
        assert ui_app.contenedor.winfo_children()[-1] == pos

        # 4. Navegación libre restaurada
        ui_app.navegar_a("usuarios")
        ui_app.update()
        assert ui_app.pantalla_actual == "usuarios"
        assert not usr.lbl_aviso_seguridad.winfo_ismapped()
        ui_app.navegar_a("pos")
        ui_app.update()
        assert ui_app.pantalla_actual == "pos"

        # 5. Entrada con admin / admin123 no exige cambio
        _login_como(ui_app, "admin", "admin123")
        ui_app.update()
        assert ui_app.sesion.esta_autenticado is True
        assert ui_app.sesion.debe_cambiar_password is False
        assert ui_app.pantalla_actual == "pos"
    finally:
        _login_como(ui_app, "admin", "admin123")
        ui_app.withdraw()
        ui_app.update()


def test_cambio_voluntario_de_contrasena_no_redirige(ui_app):
    """
    Verifica que si un usuario con contraseña no inicial (cambio voluntario)
    actualiza su contraseña en la pantalla de Usuarios, el cambio sea exitoso,
    se muestre el mensaje de confirmación y permanezca en la pantalla de Usuarios (no redirige a POS).
    """
    conn = ui_app.sesion.conn
    username_voluntario = "vendedor_voluntario_test"
    auth_service.crear_usuario(
        username=username_voluntario,
        password="clave_inicial_ok",
        nombre="Vendedor Voluntario",
        conn=conn,
        rol="vendedor",
    )

    try:
        ui_app.deiconify()
        _login_como(ui_app, username_voluntario, "clave_inicial_ok")
        ui_app.update()
        assert ui_app.sesion.esta_autenticado is True
        assert ui_app.sesion.debe_cambiar_password is False

        ui_app.navegar_a("usuarios")
        ui_app.update()
        usr: PantallaUsuarios = ui_app.pantallas["usuarios"]
        assert ui_app.pantalla_actual == "usuarios"
        assert ui_app.contenedor.winfo_children()[-1] == usr

        usr.entry_pw_actual.delete(0, tk.END)
        usr.entry_pw_actual.insert(0, "clave_inicial_ok")
        usr.entry_pw_nueva.delete(0, tk.END)
        usr.entry_pw_nueva.insert(0, "clave_nueva_ok")
        usr.entry_pw_confirmar.delete(0, tk.END)
        usr.entry_pw_confirmar.insert(0, "clave_nueva_ok")
        usr._cambiar_mi_password()
        ui_app.update()

        assert usr.lbl_exito_mi_password.winfo_ismapped()
        assert "actualizada con éxito" in usr.lbl_exito_mi_password.cget("text")
        assert ui_app.pantalla_actual == "usuarios"
        assert ui_app.contenedor.winfo_children()[-1] == usr
    finally:
        _login_como(ui_app, "admin", "admin123")
        ui_app.withdraw()
        ui_app.update()




