import os
import sqlite3
import pytest
import tkinter as tk

from models.usuario import Usuario
from ui.sesion import SesionActual
from ui.widgets_comunes import AreaError, BotonRestringidoPorRol, BarraSuperior
from ui.app import App
from ui.pantallas.login import PantallaLogin
from ui.pantallas.pos import PantallaPOS
from ui.pantallas.perfil_cliente import PantallaPerfilCliente
from ui.pantallas.inventario import PantallaInventario
from ui.pantallas.reportes import PantallaReportes
from services import cxc_service, pos_service, scoring_service, inventario_service, reportes_service


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




