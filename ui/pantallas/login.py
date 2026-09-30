import tkinter as tk
from tkinter import ttk
from typing import Any

from services.auth_service import autenticar_usuario
from ui.estilos import (
    COLOR_BLANCO,
    COLOR_FONDO_APP,
    COLOR_TEXTO_PRINCIPAL,
    COLOR_TEXTO_SECUNDARIO,
    COLOR_BORDE_NEUTRAL,
    FUENTE_TITULO_GRANDE,
    FUENTE_SUBTITULO,
    FUENTE_BASE,
    FUENTE_BASE_BOLD,
    PAD_CAMPOS,
    PAD_INTERNO,
)
from ui.sesion import SesionActual
from ui.widgets_comunes import AreaError


class PantallaLogin(tk.Frame):
    """
    Pantalla 1 — Login / Autenticación de Usuarios (RF-AUT-01).
    Proporciona acceso seguro al sistema según el rol del usuario ('admin' o 'vendedor').
    Diseñada como una tarjeta centralizada de baja carga cognitiva con manejo unificado de errores.
    """

    def __init__(self, parent: tk.Widget, app: Any, sesion: SesionActual, *args, **kwargs):
        super().__init__(parent, background=COLOR_FONDO_APP, *args, **kwargs)
        self.app = app
        self.sesion = sesion
        self.mostrar_password_var = tk.BooleanVar(value=False)

        self._construir_ui()

    def _construir_ui(self) -> None:
        """Construye la interfaz visual centrada de la pantalla de login."""
        # Contenedor centrado (Tarjeta de Login)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.card = tk.Frame(
            self,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightcolor=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=32,
            pady=30,
        )
        self.card.grid(row=0, column=0)

        # 1. Cabecera de la Tarjeta
        lbl_icono = tk.Label(
            self.card,
            text="🏪",
            font=("Segoe UI", 32),
            background=COLOR_BLANCO,
        )
        lbl_icono.pack(pady=(0, 4))

        lbl_titulo = tk.Label(
            self.card,
            text="Sistema de Tienda",
            font=FUENTE_TITULO_GRANDE,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_titulo.pack()

        lbl_subtitulo = tk.Label(
            self.card,
            text="Punto de Venta & Motor de Scoring Crediticio",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_SECUNDARIO,
        )
        lbl_subtitulo.pack(pady=(2, 18))

        # 2. Área de Errores (oculta por defecto)
        self.area_error = AreaError(self.card)
        # Nota: area_error se muestra vía pack(fill=X) cuando se invoque mostrar_error()

        # 3. Formulario de Credenciales
        form_frame = tk.Frame(self.card, background=COLOR_BLANCO)
        form_frame.pack(fill=tk.X, pady=(0, 15))

        # Campo: Usuario
        lbl_user = tk.Label(
            form_frame,
            text="Usuario:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
            anchor="w",
        )
        lbl_user.pack(fill=tk.X, pady=(0, 4))

        self.entry_usuario = ttk.Entry(form_frame, font=FUENTE_BASE)
        self.entry_usuario.pack(fill=tk.X, pady=(0, 14), ipady=3)
        self.entry_usuario.focus_set()

        # Campo: Contraseña
        lbl_pass = tk.Label(
            form_frame,
            text="Contraseña:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
            anchor="w",
        )
        lbl_pass.pack(fill=tk.X, pady=(0, 4))

        self.entry_password = ttk.Entry(
            form_frame, font=FUENTE_BASE, show="*"
        )
        self.entry_password.pack(fill=tk.X, pady=(0, 6), ipady=3)

        # Alternador Mostrar / Ocultar Contraseña
        chk_mostrar = ttk.Checkbutton(
            form_frame,
            text="Mostrar contraseña",
            variable=self.mostrar_password_var,
            command=self._alternar_visibilidad_password,
        )
        chk_mostrar.pack(anchor="w", pady=(0, 10))

        # 4. Botón de Acción Principal
        self.btn_login = ttk.Button(
            self.card,
            text="Iniciar sesión",
            style="Primary.TButton",
            command=self._procesar_login,
        )
        self.btn_login.pack(fill=tk.X, pady=(8, 4))

        # 5. Pie informativo de credenciales iniciales
        lbl_ayuda = tk.Label(
            self.card,
            text="Credencial inicial por defecto: admin / admin123",
            font=("Segoe UI", 8),
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_SECUNDARIO,
        )
        lbl_ayuda.pack(pady=(12, 0))

        # Atajo de teclado: Enter ejecuta el login
        self.entry_usuario.bind("<Return>", lambda e: self._procesar_login())
        self.entry_password.bind("<Return>", lambda e: self._procesar_login())

    def _alternar_visibilidad_password(self) -> None:
        """Alterna el carácter de máscara '*' en el campo de contraseña."""
        if self.mostrar_password_var.get():
            self.entry_password.config(show="")
        else:
            self.entry_password.config(show="*")

    def _procesar_login(self) -> None:
        """
        Valida las entradas y ejecuta la autenticación contra auth_service (RF-AUT-01).
        En caso de error, muestra mensaje genérico sin distinguir causa.
        En caso de éxito, registra la sesión y navega a la pantalla principal.
        """
        username = self.entry_usuario.get().strip()
        password = self.entry_password.get()

        self.area_error.limpiar()

        if not username or not password:
            self.area_error.mostrar_error("Por favor ingrese su usuario y contraseña.")
            if not username:
                self.entry_usuario.focus_set()
            else:
                self.entry_password.focus_set()
            return

        usuario = autenticar_usuario(
            username=username,
            password=password,
            conn=self.sesion.conn,
        )

        if usuario is None:
            # Mensaje genérico de seguridad: previene enumeración de usuarios
            self.area_error.mostrar_error("Usuario o contraseña incorrectos.")
            self.entry_password.delete(0, tk.END)
            self.entry_password.focus_set()
            return

        # Autenticación exitosa
        self.sesion.iniciar_sesion(usuario)
        self.limpiar_campos()
        self.app.navegar_a("pos")

    def limpiar_campos(self) -> None:
        """Restablece los campos de entrada y oculta errores."""
        self.entry_usuario.delete(0, tk.END)
        self.entry_password.delete(0, tk.END)
        self.mostrar_password_var.set(False)
        self.entry_password.config(show="*")
        self.area_error.limpiar()

    def al_mostrar(self) -> None:
        """Callback invocado por el contenedor de navegación al proyectar esta pantalla."""
        self.limpiar_campos()
        self.entry_usuario.focus_set()
