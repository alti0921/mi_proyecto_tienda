import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ui.estilos import (
    COLOR_BARRA_SUPERIOR,
    COLOR_BARRA_BORDE,
    COLOR_ERROR_BG,
    COLOR_ERROR_BORDE,
    COLOR_ERROR_TEXTO,
    FUENTE_BASE,
    FUENTE_BASE_BOLD,
    FUENTE_TITULO,
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

        # 1. Título a la izquierda
        self.lbl_titulo = tk.Label(
            self,
            text=titulo,
            font=FUENTE_TITULO,
            background=COLOR_BARRA_SUPERIOR,
            foreground="#2d3436",
        )
        self.lbl_titulo.pack(side=tk.LEFT)

        # 2. Botones de navegación central (si hay callback disponible)
        self.frame_nav = tk.Frame(self, background=COLOR_BARRA_SUPERIOR)
        self.frame_nav.pack(side=tk.LEFT, padx=25)

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

        # 3. Lado derecho: Información del usuario y Botón de Cierre
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

    def _navegar(self, pantalla: str) -> None:
        if self.on_navegar:
            self.on_navegar(pantalla)

    def actualizar_datos(self) -> None:
        """Actualiza la etiqueta con los datos del usuario en sesión y recalcula permisos."""
        if self.sesion.esta_autenticado:
            u = self.sesion.usuario_actual
            rol_etiqueta = "Administrador" if u.rol == "admin" else "Vendedor"
            self.lbl_usuario.config(
                text=f"👤 {u.nombre} ({rol_etiqueta})"
            )
        else:
            self.lbl_usuario.config(text="Usuario: No autenticado")

        # Refrescar botones restringidos
        self.btn_rep.actualizar_estado()
