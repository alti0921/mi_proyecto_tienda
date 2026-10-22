import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Any, List, Optional

from services import auth_service
from ui.estilos import (
    COLOR_BLANCO,
    COLOR_BORDE_NEUTRAL,
    COLOR_EXITO,
    COLOR_FONDO_APP,
    COLOR_TEXTO_MUTED,
    COLOR_TEXTO_PRINCIPAL,
    FUENTE_BASE,
    FUENTE_BASE_BOLD,
    FUENTE_PEQUENA,
    FUENTE_SUBTITULO,
    FUENTE_TITULO,
    PAD_CAMPOS,
    PAD_INTERNO,
)
from ui.sesion import SesionActual
from ui.widgets_comunes import (
    AreaError,
    ajustar_wraplength,
    configurar_columnas,
    agregar_scroll_horizontal,
)


class PantallaUsuarios(tk.Frame):
    """
    Pantalla 6 — Gestión de Usuarios y Seguridad de Accesos (RF-AUT-02, RF-AUT-03).
    Panel Admin: Gestión de catálogo de usuarios, altas, cambio de estado (activo/inactivo)
    y restablecimiento de contraseñas.
    Panel Mi Contraseña: Autoservicio para que cualquier usuario autenticado actualice su clave.
    """

    def __init__(
        self,
        parent: tk.Widget,
        app: Any,
        sesion: SesionActual,
        *args,
        **kwargs,
    ):
        super().__init__(parent, background=COLOR_FONDO_APP, *args, **kwargs)
        self.app = app
        self.sesion = sesion

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3, uniform="usr")
        self.grid_columnconfigure(1, weight=2, uniform="usr")

        # Panel Izquierdo: Gestión de Usuarios (Exclusivo Administrador)
        self.panel_admin = tk.Frame(self, background=COLOR_FONDO_APP)
        self.panel_admin.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=12)
        self.panel_admin.grid_rowconfigure(0, weight=3)  # Tabla y acciones
        self.panel_admin.grid_rowconfigure(1, weight=2)  # Formulario alta
        self.panel_admin.grid_columnconfigure(0, weight=1)

        # Panel Derecho: Cambio de Mi Contraseña (Todos los Roles)
        self.panel_mi_password = tk.Frame(self, background=COLOR_FONDO_APP)
        self.panel_mi_password.grid(row=0, column=1, sticky="nsew", padx=(7, 14), pady=12)
        self.panel_mi_password.grid_rowconfigure(0, weight=1)
        self.panel_mi_password.grid_columnconfigure(0, weight=1)

        self._crear_panel_admin()
        self._crear_panel_mi_password()

    # =========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # =========================================================================

    def _crear_panel_admin(self) -> None:
        """Construye los bloques de gestión de usuarios para el Administrador."""
        # 1. Card Superior: Catálogo y Acciones
        card_catalogo = tk.Frame(
            self.panel_admin,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_catalogo.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        card_catalogo.grid_rowconfigure(1, weight=1)
        card_catalogo.grid_columnconfigure(0, weight=1)

        lbl_tit_catalogo = tk.Label(
            card_catalogo,
            text="👥 Catálogo de Usuarios del Sistema (Admin)",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_catalogo.grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Treeview de Usuarios
        frame_tree = tk.Frame(card_catalogo, background=COLOR_BLANCO)
        frame_tree.grid(row=1, column=0, sticky="nsew")
        frame_tree.grid_rowconfigure(0, weight=1)
        frame_tree.grid_columnconfigure(0, weight=1)

        columnas = ("usuario", "nombre", "rol", "estado")
        self.tree_usuarios = ttk.Treeview(
            frame_tree,
            columns=columnas,
            show="headings",
            selectmode="browse",
        )
        self.tree_usuarios.heading("usuario", text="Usuario")
        self.tree_usuarios.heading("nombre", text="Nombre Real")
        self.tree_usuarios.heading("rol", text="Rol")
        self.tree_usuarios.heading("estado", text="Estado")

        configurar_columnas(
            self.tree_usuarios,
            {
                "usuario": (110, 80),
                "nombre": (160, 110),
                "rol": (80, 60),
                "estado": (80, 60),
            },
        )
        self.tree_usuarios.column("usuario", anchor=tk.W)
        self.tree_usuarios.column("nombre", anchor=tk.W)
        self.tree_usuarios.column("rol", anchor=tk.CENTER)
        self.tree_usuarios.column("estado", anchor=tk.CENTER)

        scroll_tree = ttk.Scrollbar(
            frame_tree, orient="vertical", command=self.tree_usuarios.yview
        )
        self.tree_usuarios.configure(yscrollcommand=scroll_tree.set)
        self.tree_usuarios.grid(row=0, column=0, sticky="nsew")
        scroll_tree.grid(row=0, column=1, sticky="ns")
        self.scroll_h_usuarios = agregar_scroll_horizontal(
            self.tree_usuarios, frame_tree, row=1, column=0
        )

        self.tree_usuarios.bind("<<TreeviewSelect>>", self._on_usuario_seleccionado)

        # Barra de Acciones sobre el Usuario Seleccionado
        frame_acciones = tk.Frame(card_catalogo, background=COLOR_BLANCO)
        frame_acciones.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.btn_cambiar_estado = ttk.Button(
            frame_acciones,
            text="Desactivar",
            command=self._cambiar_estado_seleccionado,
        )
        self.btn_cambiar_estado.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(
            frame_acciones,
            text="Clave temporal:",
            font=FUENTE_BASE,
            background=COLOR_BLANCO,
        ).pack(side=tk.LEFT, padx=(6, 4))

        self.entry_password_temporal = ttk.Entry(
            frame_acciones, width=14, font=("Segoe UI", 10)
        )
        self.entry_password_temporal.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_restablecer = ttk.Button(
            frame_acciones,
            text="Restablecer contraseña",
            command=self._restablecer_password_seleccionado,
        )
        self.btn_restablecer.pack(side=tk.LEFT)

        # 2. Card Inferior: Alta de Usuario
        card_alta = tk.Frame(
            self.panel_admin,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_alta.grid(row=1, column=0, sticky="nsew")
        card_alta.grid_columnconfigure(1, weight=1)

        lbl_tit_alta = tk.Label(
            card_alta,
            text="➕ Registrar Nuevo Usuario",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_alta.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        # Formulario
        tk.Label(
            card_alta, text="Username:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).grid(row=1, column=0, sticky="w", pady=3)
        self.entry_nuevo_username = ttk.Entry(card_alta, font=("Segoe UI", 10))
        self.entry_nuevo_username.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=3)

        tk.Label(
            card_alta, text="Nombre Real:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).grid(row=2, column=0, sticky="w", pady=3)
        self.entry_nuevo_nombre = ttk.Entry(card_alta, font=("Segoe UI", 10))
        self.entry_nuevo_nombre.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=3)

        tk.Label(
            card_alta, text="Rol:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).grid(row=3, column=0, sticky="w", pady=3)
        self.combo_nuevo_rol = ttk.Combobox(
            card_alta,
            state="readonly",
            values=["vendedor", "admin"],
        )
        self.combo_nuevo_rol.set("vendedor")
        self.combo_nuevo_rol.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=3)

        tk.Label(
            card_alta, text="Contraseña inicial:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).grid(row=4, column=0, sticky="w", pady=3)
        self.entry_nuevo_password = ttk.Entry(card_alta, show="*", font=("Segoe UI", 10))
        self.entry_nuevo_password.grid(row=4, column=1, sticky="ew", padx=(8, 0), pady=3)

        # Mensajes y botón de creación
        frame_error_admin = tk.Frame(card_alta, background=COLOR_BLANCO)
        frame_error_admin.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.area_error_admin = AreaError(frame_error_admin)

        self.lbl_exito_admin = tk.Label(
            card_alta,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
            justify=tk.LEFT,
        )
        self.lbl_exito_admin.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ajustar_wraplength(self.lbl_exito_admin)

        self.btn_crear_usuario = ttk.Button(
            card_alta,
            text="Crear Usuario",
            style="Success.TButton",
            command=self._crear_usuario,
        )
        self.btn_crear_usuario.grid(row=7, column=1, sticky="e", pady=(6, 0))

    def _crear_panel_mi_password(self) -> None:
        """Construye el panel de autoservicio para cambio de contraseña propia."""
        card_pw = tk.Frame(
            self.panel_mi_password,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        card_pw.grid(row=0, column=0, sticky="nsew")
        card_pw.grid_columnconfigure(0, weight=1)

        lbl_tit_pw = tk.Label(
            card_pw,
            text="🔒 Cambiar Mi Contraseña",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_pw.pack(anchor="w", pady=(0, 4))

        lbl_desc_pw = tk.Label(
            card_pw,
            text="Actualiza tu clave de acceso personal. La contraseña debe tener al menos 6 caracteres.",
            font=FUENTE_PEQUENA,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_MUTED,
            justify=tk.LEFT,
        )
        lbl_desc_pw.pack(fill=tk.X, anchor="w", pady=(0, 10))
        ajustar_wraplength(lbl_desc_pw)

        # Aviso obligatorio de seguridad para contraseña inicial
        self.frame_aviso_seguridad = tk.Frame(
            card_pw,
            background="#fff3cd",
            highlightbackground="#ffeeba",
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        self.lbl_icono_aviso = tk.Label(
            self.frame_aviso_seguridad,
            text="⚠️",
            background="#fff3cd",
            font=("Segoe UI", 11, "bold"),
        )
        self.lbl_icono_aviso.pack(side=tk.LEFT, padx=(0, 8))
        self.lbl_aviso_seguridad = tk.Label(
            self.frame_aviso_seguridad,
            text="Por seguridad, cambie la contraseña inicial antes de continuar.",
            background="#fff3cd",
            foreground="#856404",
            font=FUENTE_BASE_BOLD,
            justify=tk.LEFT,
        )
        self.lbl_aviso_seguridad.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor="w")
        ajustar_wraplength(self.lbl_aviso_seguridad)

        # Campos
        self.lbl_pw_actual = tk.Label(
            card_pw, text="Contraseña actual:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        )
        self.lbl_pw_actual.pack(anchor="w", pady=(4, 2))
        self.entry_pw_actual = ttk.Entry(card_pw, show="*", font=("Segoe UI", 10))
        self.entry_pw_actual.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            card_pw, text="Nueva contraseña:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).pack(anchor="w", pady=(4, 2))
        self.entry_pw_nueva = ttk.Entry(card_pw, show="*", font=("Segoe UI", 10))
        self.entry_pw_nueva.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            card_pw, text="Confirmar nueva contraseña:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO
        ).pack(anchor="w", pady=(4, 2))
        self.entry_pw_confirmar = ttk.Entry(card_pw, show="*", font=("Segoe UI", 10))
        self.entry_pw_confirmar.pack(fill=tk.X, pady=(0, 8))

        # Mensajes
        self.area_error_mi_password = AreaError(card_pw)
        self.area_error_mi_password.pack(fill=tk.X, pady=(4, 0))

        self.lbl_exito_mi_password = tk.Label(
            card_pw,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
            justify=tk.LEFT,
        )
        self.lbl_exito_mi_password.pack(fill=tk.X, anchor="w", pady=(2, 0))
        ajustar_wraplength(self.lbl_exito_mi_password)

        # Botón
        self.btn_cambiar_mi_password = ttk.Button(
            card_pw,
            text="Actualizar Contraseña",
            style="Primary.TButton",
            command=self._cambiar_mi_password,
        )
        self.btn_cambiar_mi_password.pack(anchor="e", pady=(10, 0))

    def mostrar_aviso_seguridad(self, texto: str = "Por seguridad, cambie la contraseña inicial antes de continuar.") -> None:
        """Muestra el aviso de seguridad que exige el cambio de contraseña inicial."""
        self.lbl_aviso_seguridad.config(text=texto)
        if not self.frame_aviso_seguridad.winfo_ismapped():
            self.frame_aviso_seguridad.pack(fill=tk.X, pady=(0, 10), before=self.lbl_pw_actual)

    def ocultar_aviso_seguridad(self) -> None:
        """Oculta el aviso de seguridad obligatorio."""
        self.frame_aviso_seguridad.pack_forget()

    # =========================================================================
    # LÓGICA DE NEGOCIO Y MANEJO DE EVENTOS
    # =========================================================================

    def _limpiar_mensajes(self) -> None:
        """Limpia las áreas de error y etiquetas de éxito de ambos paneles."""
        self.area_error_admin.limpiar()
        self.lbl_exito_admin.config(text="")
        self.area_error_mi_password.limpiar()
        self.lbl_exito_mi_password.config(text="")
        if not self.sesion.debe_cambiar_password:
            self.ocultar_aviso_seguridad()

    def _cargar_lista_usuarios(self) -> None:
        """Carga y refresca el catálogo completo de usuarios en el Treeview."""
        for item in self.tree_usuarios.get_children():
            self.tree_usuarios.delete(item)

        usuarios = auth_service.listar_usuarios(self.sesion.conn)
        for u in usuarios:
            estado_txt = "Activo" if u.activo else "Inactivo"
            self.tree_usuarios.insert(
                "",
                tk.END,
                iid=str(u.id),
                values=(u.username, u.nombre, u.rol.capitalize(), estado_txt),
            )
        self._on_usuario_seleccionado()

    def _on_usuario_seleccionado(self, event=None) -> None:
        """Actualiza el texto del botón de estado según la selección actual."""
        sel = self.tree_usuarios.selection()
        if not sel:
            self.btn_cambiar_estado.config(text="Desactivar")
            return
        try:
            uid = int(sel[0])
            u = auth_service.obtener_usuario_por_id(uid, self.sesion.conn)
            if u and not u.activo:
                self.btn_cambiar_estado.config(text="Reactivar")
            else:
                self.btn_cambiar_estado.config(text="Desactivar")
        except Exception:
            self.btn_cambiar_estado.config(text="Desactivar")

    def _crear_usuario(self) -> None:
        """Da de alta un nuevo usuario en el sistema a través de auth_service."""
        self.area_error_admin.limpiar()
        self.lbl_exito_admin.config(text="")

        username = self.entry_nuevo_username.get().strip()
        nombre = self.entry_nuevo_nombre.get().strip()
        rol = self.combo_nuevo_rol.get().strip()
        password = self.entry_nuevo_password.get()

        try:
            nuevo = auth_service.crear_usuario(
                username=username,
                password=password,
                nombre=nombre,
                conn=self.sesion.conn,
                rol=rol,
            )
            self.lbl_exito_admin.config(
                text=f"✅ Usuario '{nuevo.username}' creado con éxito."
            )
            self.entry_nuevo_username.delete(0, tk.END)
            self.entry_nuevo_nombre.delete(0, tk.END)
            self.entry_nuevo_password.delete(0, tk.END)
            self.combo_nuevo_rol.set("vendedor")

            self._cargar_lista_usuarios()
            self.tree_usuarios.selection_set(str(nuevo.id))
            self.tree_usuarios.see(str(nuevo.id))
            self._on_usuario_seleccionado()
        except ValueError as e:
            self.area_error_admin.mostrar_error(str(e))
        except Exception as e:
            self.area_error_admin.mostrar_error(f"Error inesperado al crear usuario: {e}")

    def _cambiar_estado_seleccionado(self) -> None:
        """Alterna el estado activo/inactivo del usuario seleccionado en la lista."""
        self.area_error_admin.limpiar()
        self.lbl_exito_admin.config(text="")

        sel = self.tree_usuarios.selection()
        if not sel:
            self.area_error_admin.mostrar_error("Seleccione un usuario de la lista.")
            return

        try:
            usuario_id = int(sel[0])
        except (ValueError, TypeError):
            self.area_error_admin.mostrar_error("Seleccione un usuario válido.")
            return

        u = auth_service.obtener_usuario_por_id(usuario_id, self.sesion.conn)
        if not u:
            self.area_error_admin.mostrar_error("Usuario no encontrado.")
            return

        nuevo_estado = not u.activo

        try:
            u_act = auth_service.cambiar_estado_usuario(
                usuario_id=usuario_id,
                activo=nuevo_estado,
                conn=self.sesion.conn,
            )
            accion = "reactivado" if u_act.activo else "desactivado"
            self.lbl_exito_admin.config(
                text=f"✅ Usuario '{u_act.username}' {accion} con éxito."
            )
            self._cargar_lista_usuarios()
            self.tree_usuarios.selection_set(str(u_act.id))
            self._on_usuario_seleccionado()
        except ValueError as e:
            self.area_error_admin.mostrar_error(str(e))
        except Exception as e:
            self.area_error_admin.mostrar_error(f"Error al cambiar estado: {e}")

    def _restablecer_password_seleccionado(self) -> None:
        """Asigna una nueva clave temporal al usuario seleccionado."""
        self.area_error_admin.limpiar()
        self.lbl_exito_admin.config(text="")

        sel = self.tree_usuarios.selection()
        if not sel:
            self.area_error_admin.mostrar_error("Seleccione un usuario de la lista.")
            return

        try:
            usuario_id = int(sel[0])
        except (ValueError, TypeError):
            self.area_error_admin.mostrar_error("Seleccione un usuario válido.")
            return

        password_temporal = self.entry_password_temporal.get()

        try:
            auth_service.restablecer_password(
                usuario_id=usuario_id,
                nueva_password=password_temporal,
                conn=self.sesion.conn,
            )
            self.lbl_exito_admin.config(
                text="✅ Contraseña restablecida con éxito para el usuario seleccionado."
            )
            self.entry_password_temporal.delete(0, tk.END)
        except ValueError as e:
            self.area_error_admin.mostrar_error(str(e))
        except Exception as e:
            self.area_error_admin.mostrar_error(f"Error al restablecer contraseña: {e}")

    def _cambiar_mi_password(self) -> None:
        """Procesa la actualización de contraseña propia por parte del usuario en sesión."""
        self.area_error_mi_password.limpiar()
        self.lbl_exito_mi_password.config(text="")
        era_obligatorio = self.sesion.debe_cambiar_password

        if not self.sesion.esta_autenticado or not self.sesion.usuario_actual:
            self.area_error_mi_password.mostrar_error("No hay una sesión activa.")
            return

        pw_actual = self.entry_pw_actual.get()
        pw_nueva = self.entry_pw_nueva.get()
        pw_confirmar = self.entry_pw_confirmar.get()

        if pw_nueva != pw_confirmar:
            self.area_error_mi_password.mostrar_error(
                "La nueva contraseña y su confirmación no coinciden."
            )
            return

        if auth_service.usa_contrasena_inicial(pw_nueva):
            self.area_error_mi_password.mostrar_error(
                "La nueva contraseña no puede ser la contraseña inicial."
            )
            return

        try:
            auth_service.cambiar_password(
                usuario_id=self.sesion.usuario_actual.id,
                password_actual=pw_actual,
                password_nueva=pw_nueva,
                conn=self.sesion.conn,
            )
            self.sesion.debe_cambiar_password = False
            self.ocultar_aviso_seguridad()
            self.lbl_exito_mi_password.config(
                text="✅ Tu contraseña ha sido actualizada con éxito."
            )
            self.entry_pw_actual.delete(0, tk.END)
            self.entry_pw_nueva.delete(0, tk.END)
            self.entry_pw_confirmar.delete(0, tk.END)
            if era_obligatorio:
                self.app.navegar_a("pos")
        except ValueError as e:
            self.area_error_mi_password.mostrar_error(str(e))
        except Exception as e:
            self.area_error_mi_password.mostrar_error(f"Error al cambiar contraseña: {e}")

    # =========================================================================
    # CICLO DE VIDA REACTIVO
    # =========================================================================

    def al_mostrar(self) -> None:
        """
        Hook invocado por App.navegar_a.
        Ajusta la visibilidad del panel de administración reactivamente según el rol
        del usuario activo en la sesión (Parche #19).
        """
        self._limpiar_mensajes()
        if self.sesion.debe_cambiar_password:
            self.mostrar_aviso_seguridad()
        if self.sesion.es_admin:
            self.panel_admin.grid(row=0, column=0, sticky="nsew", padx=(14, 7), pady=12)
            self._cargar_lista_usuarios()
        else:
            self.panel_admin.grid_remove()
