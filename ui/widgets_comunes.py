import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from models.cliente import Cliente
from services import cxc_service
from ui.estilos import (
    COLOR_BARRA_SUPERIOR,
    COLOR_BARRA_BORDE,
    COLOR_ERROR_BG,
    COLOR_ERROR_BORDE,
    COLOR_ERROR_TEXTO,
    COLOR_FONDO_APP,
    COLOR_TEXTO_PRINCIPAL,
    FUENTE_BASE,
    FUENTE_BASE_BOLD,
    FUENTE_TITULO,
    FUENTE_SUBTITULO,
    FUENTE_BOTON,
    PAD_CAMPOS,
    PAD_INTERNO,
)
from ui.sesion import SesionActual



class AreaError(tk.Frame):
    """
    Componente visual para despliegue de mensajes de error de negocio (ValueError).
    Presenta un recuadro de alerta con fondo rojo claro, borde rojo y tipografía de advertencia.
    Permanece oculto cuando no hay mensajes activos.
    """

    def __init__(self, parent: tk.Widget, *args, **kwargs):
        super().__init__(
            parent,
            background=COLOR_ERROR_BG,
            highlightbackground=COLOR_ERROR_BORDE,
            highlightcolor=COLOR_ERROR_BORDE,
            highlightthickness=1,
            padx=10,
            pady=8,
            *args,
            **kwargs,
        )
        self._mensaje_actual = ""
        self._tiene_error = False

        self.lbl_icono = tk.Label(
            self,
            text="⚠️",
            background=COLOR_ERROR_BG,
            foreground=COLOR_ERROR_TEXTO,
            font=("Segoe UI", 11, "bold"),
        )
        self.lbl_icono.pack(side=tk.LEFT, padx=(0, 8))

        self.lbl_texto = tk.Label(
            self,
            text="",
            background=COLOR_ERROR_BG,
            foreground=COLOR_ERROR_TEXTO,
            font=FUENTE_BASE_BOLD,
            wraplength=450,
            justify=tk.LEFT,
        )
        self.lbl_texto.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Oculto por defecto
        self.limpiar()

    def mostrar_error(self, texto: str) -> None:
        """Configura el texto de error y hace visible el marco de alerta."""
        self._mensaje_actual = texto.strip()
        self._tiene_error = True
        self.lbl_texto.config(text=self._mensaje_actual)
        self.pack(fill=tk.X, padx=PAD_INTERNO, pady=(0, 10))

    def limpiar(self) -> None:
        """Limpia el mensaje y oculta el componente."""
        self._mensaje_actual = ""
        self._tiene_error = False
        self.lbl_texto.config(text="")
        self.pack_forget()

    def tiene_error(self) -> bool:
        """Retorna True si el área de error está actualmente desplegada con un mensaje."""
        return self._tiene_error


class BotonRestringidoPorRol(ttk.Button):
    """
    Botón ttk que autogestiona su disponibilidad operacional según el rol del usuario en sesión.
    Si el rol del usuario actual no está dentro de roles_permitidos, se deshabilita (state='disabled').
    """

    def __init__(
        self,
        parent: tk.Widget,
        sesion: SesionActual,
        roles_permitidos: Optional[List[str]] = None,
        *args,
        **kwargs,
    ):
        super().__init__(parent, *args, **kwargs)
        self.sesion = sesion
        self.roles_permitidos = roles_permitidos or ["admin"]
        self.actualizar_estado()

    def actualizar_estado(self) -> None:
        """Habilita o deshabilita el botón según el rol de la sesión activa."""
        if (
            self.sesion.esta_autenticado
            and self.sesion.usuario_actual.rol in self.roles_permitidos
        ):
            self.config(state="normal")
        else:
            self.config(state="disabled")


class BarraSuperior(tk.Frame):
    """
    Barra superior horizontal persistente para navegación y control de sesión (Wireframes 2 a 5).
    Despliega el título del sistema, la información dinámica del usuario en sesión y el botón para cerrar sesión.
    Adaptable a diferentes anchos de pantalla mediante modo compacto automático.
    """

    def __init__(
        self,
        parent: tk.Widget,
        sesion: SesionActual,
        on_cerrar_sesion: Callable[[], None],
        on_navegar: Optional[Callable[[str], None]] = None,
        titulo: str = "Mi Tienda — Sistema POS & Scoring",
        *args,
        **kwargs,
    ):
        super().__init__(
            parent,
            background=COLOR_BARRA_SUPERIOR,
            highlightbackground=COLOR_BARRA_BORDE,
            highlightthickness=1,
            height=48,
            padx=14,
            pady=6,
            *args,
            **kwargs,
        )
        self.sesion = sesion
        self.on_cerrar_sesion = on_cerrar_sesion
        self.on_navegar = on_navegar

        # 1. Lado derecho: Información del usuario y Botón de Cierre
        # Se empaqueta PRIMERO (side=RIGHT) para garantizar que 'Cerrar sesión' siempre tenga espacio y se vea
        self.frame_derecho = tk.Frame(self, background=COLOR_BARRA_SUPERIOR)
        self.frame_derecho.pack(side=tk.RIGHT)

        self.lbl_usuario = tk.Label(
            self.frame_derecho,
            text="Usuario: No autenticado",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BARRA_SUPERIOR,
            foreground="#2c3e50",
        )
        self.lbl_usuario.pack(side=tk.LEFT, padx=(0, 15))

        self.btn_logout = ttk.Button(
            self.frame_derecho,
            text="Cerrar sesión",
            command=self.on_cerrar_sesion,
        )
        self.btn_logout.pack(side=tk.LEFT)

        # 2. Título a la izquierda
        self.lbl_titulo = tk.Label(
            self,
            text=titulo,
            font=FUENTE_TITULO,
            background=COLOR_BARRA_SUPERIOR,
            foreground="#2d3436",
        )
        self.lbl_titulo.pack(side=tk.LEFT)

        # 3. Botones de navegación central
        self.frame_nav = tk.Frame(self, background=COLOR_BARRA_SUPERIOR)
        self.frame_nav.pack(side=tk.LEFT, padx=15)

        self.btn_pos = ttk.Button(
            self.frame_nav, text="🛒 POS", command=lambda: self._navegar("pos")
        )
        self.btn_pos.pack(side=tk.LEFT, padx=3)

        self.btn_cxc = ttk.Button(
            self.frame_nav, text="👤 Clientes / CxC", command=lambda: self._navegar("cxc")
        )
        self.btn_cxc.pack(side=tk.LEFT, padx=3)

        self.btn_inv = ttk.Button(
            self.frame_nav, text="📦 Inventario", command=lambda: self._navegar("inventario")
        )
        self.btn_inv.pack(side=tk.LEFT, padx=3)

        self.btn_rep = BotonRestringidoPorRol(
            self.frame_nav,
            sesion=self.sesion,
            roles_permitidos=["admin", "vendedor"],
            text="📊 Reportes",
            command=lambda: self._navegar("reportes"),
        )
        self.btn_rep.pack(side=tk.LEFT, padx=3)

        self.btn_usuarios = ttk.Button(
            self.frame_nav,
            text="🔑 Usuarios",
            command=lambda: self._navegar("usuarios"),
        )
        self.btn_usuarios.pack(side=tk.LEFT, padx=3)

        # Textos completos y compactos para preservación exacta
        self._es_compacto: bool = False
        self._texto_titulo_completo = titulo
        self._texto_titulo_compacto = "Mi Tienda"

        self._nav_textos_completos = {
            self.btn_pos: "🛒 POS",
            self.btn_cxc: "👤 Clientes / CxC",
            self.btn_inv: "📦 Inventario",
            self.btn_rep: "📊 Reportes",
            self.btn_usuarios: "🔑 Usuarios",
        }
        self._nav_textos_compactos = {
            self.btn_pos: "POS",
            self.btn_cxc: "Clientes",
            self.btn_inv: "Inventario",
            self.btn_rep: "Reportes",
            self.btn_usuarios: "Usuarios",
        }

        self._texto_usuario_completo = "Usuario: No autenticado"
        self._texto_usuario_compacto = "👤 No autenticado"

        self._ancho_requerido_completo: int = 0

        # Enlazar evento <Configure> para modo compacto automático
        self.bind("<Configure>", self._al_redimensionar)

    @property
    def es_compacto(self) -> bool:
        """Indica si la barra superior se encuentra actualmente en modo compacto."""
        return self._es_compacto

    def aplicar_modo_compacto(self, compacto: bool) -> None:
        """
        Aplica o desactiva el modo compacto de la barra superior restaurando o
        abreviando textos sin reconstruir elementos.
        """
        self._es_compacto = bool(compacto)
        if self._es_compacto:
            self.lbl_titulo.config(text=self._texto_titulo_compacto)
            for btn, txt in self._nav_textos_compactos.items():
                btn.config(text=txt)
            self.lbl_usuario.config(text=self._texto_usuario_compacto)
        else:
            self.lbl_titulo.config(text=self._texto_titulo_completo)
            for btn, txt in self._nav_textos_completos.items():
                btn.config(text=txt)
            self.lbl_usuario.config(text=self._texto_usuario_completo)

        self.btn_rep.actualizar_estado()

    def _al_redimensionar(self, event) -> None:
        """Detecta cambios de ancho de la barra superior y conmuta el modo compacto si no cabe."""
        if event.widget is not self:
            return
        ancho_disp = event.width
        if not self._es_compacto:
            ancho_req = (
                self.lbl_titulo.winfo_reqwidth()
                + self.frame_nav.winfo_reqwidth()
                + self.frame_derecho.winfo_reqwidth()
                + 40
            )
            self._ancho_requerido_completo = max(self._ancho_requerido_completo, ancho_req)
            if ancho_req > ancho_disp:
                self.aplicar_modo_compacto(True)
        else:
            umbral = getattr(self, "_ancho_requerido_completo", 1040)
            if ancho_disp >= umbral + 10:
                self.aplicar_modo_compacto(False)

    def _navegar(self, pantalla: str) -> None:
        if self.on_navegar:
            self.on_navegar(pantalla)

    def actualizar_datos(self) -> None:
        """Actualiza la etiqueta con los datos del usuario en sesión y recalcula permisos."""
        if self.sesion.esta_autenticado:
            u = self.sesion.usuario_actual
            rol_etiqueta = "Administrador" if u.rol == "admin" else "Vendedor"
            self._texto_usuario_completo = f"👤 {u.nombre} · {rol_etiqueta}"
            self._texto_usuario_compacto = f"👤 {rol_etiqueta}"
        else:
            self._texto_usuario_completo = "Usuario: No autenticado"
            self._texto_usuario_compacto = "👤 No autenticado"

        self.lbl_usuario.config(
            text=self._texto_usuario_compacto if self._es_compacto else self._texto_usuario_completo
        )

        # Refrescar botones restringidos
        self.btn_rep.actualizar_estado()


class DialogoNuevoCliente(tk.Toplevel):
    """
    Diálogo modal reutilizable para registrar un nuevo cliente (RF-CXC-01, Wireframes v2).
    Disponible tanto desde la pantalla de Clientes/CxC como directamente desde el POS.
    """

    def __init__(
        self,
        parent: tk.Widget,
        conn: sqlite3.Connection,
        al_crear: Callable[[Cliente], None],
        *args,
        **kwargs,
    ):
        super().__init__(parent, *args, **kwargs)
        self.conn = conn
        self.al_crear = al_crear

        self.title("Registrar Nuevo Cliente")
        self.geometry("420x360")
        try:
            self.transient(parent)
            self.grab_set()
        except tk.TclError:
            pass

        self.configure(background=COLOR_FONDO_APP)

        frame = tk.Frame(self, background=COLOR_FONDO_APP, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text="➕ Alta de Cliente",
            font=FUENTE_SUBTITULO,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w", pady=(0, 10))

        # Campos
        tk.Label(
            frame,
            text="Nombre o apodo (*):",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w")
        self.entry_nombre = ttk.Entry(frame, width=35)
        self.entry_nombre.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            frame,
            text="Teléfono:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w")
        self.entry_telefono = ttk.Entry(frame, width=35)
        self.entry_telefono.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            frame,
            text="Dirección:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w")
        self.entry_direccion = ttk.Entry(frame, width=35)
        self.entry_direccion.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            frame,
            text="Nivel de vínculo:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w")
        self.combo_vinculo = ttk.Combobox(
            frame,
            values=["solo_apodo", "conocido_referido", "registro_completo"],
            state="readonly",
        )
        self.combo_vinculo.set("solo_apodo")
        self.combo_vinculo.pack(fill=tk.X, pady=(2, 10))

        self.area_error = AreaError(frame)

        self.btn_crear = ttk.Button(
            frame,
            text="Crear Cliente",
            style="Primary.TButton",
            command=self.guardar,
        )
        self.btn_crear.pack(fill=tk.X, pady=(10, 0))

        # Keybindings: Enter en entry_nombre guarda; Escape cierra diálogo
        self.entry_nombre.bind("<Return>", lambda e: self.guardar())
        self.bind("<Escape>", lambda e: self.destroy())

        self.entry_nombre.focus_set()

    def guardar(self) -> None:
        """
        Valida y persiste el nuevo cliente con cupo 0.0 (RF-CXC-07).
        Si tiene éxito, destruye la ventana e invoca al_crear(cliente_nuevo).
        Si hay ValueError, lo despliega en self.area_error manteniendo la ventana abierta.
        """
        self.area_error.limpiar()
        nom = self.entry_nombre.get().strip()
        tel = self.entry_telefono.get().strip() or None
        dire = self.entry_direccion.get().strip() or None
        vinc = self.combo_vinculo.get()

        try:
            nuevo = cxc_service.crear_cliente(
                nombre=nom,
                conn=self.conn,
                telefono=tel,
                direccion=dire,
                nivel_vinculo=vinc,
                limite_credito=0.0,
            )
            self.destroy()
            if self.al_crear:
                self.al_crear(nuevo)
        except ValueError as e:
            self.area_error.mostrar_error(str(e))

