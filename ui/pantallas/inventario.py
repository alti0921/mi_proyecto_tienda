import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional

from models.producto import Producto
from services import inventario_service
from ui.estilos import (
    COLOR_ALERTA_BG,
    COLOR_ALERTA_BORDE,
    COLOR_ALERTA_TEXTO,
    COLOR_BLANCO,
    COLOR_BORDE_NEUTRAL,
    COLOR_ERROR_BG,
    COLOR_ERROR_BORDE,
    COLOR_ERROR_TEXTO,
    COLOR_EXITO,
    COLOR_FONDO_APP,
    COLOR_PELIGRO,
    COLOR_PRIMARIO,
    COLOR_TEXTO_MUTED,
    COLOR_TEXTO_PRINCIPAL,
    COLOR_TEXTO_SECUNDARIO,
    FUENTE_BASE,
    FUENTE_BASE_BOLD,
    FUENTE_BOTON,
    FUENTE_KPI_NUMERO,
    FUENTE_PEQUENA,
    FUENTE_SUBTITULO,
    FUENTE_TITULO,
    PAD_CAMPOS,
    PAD_INTERNO,
)
from ui.sesion import SesionActual
from ui.widgets_comunes import AreaError, BotonRestringidoPorRol

CATEGORIAS_VALIDAS = ("canasta_basica", "cesta_mixta", "consumo_suntuario")


class PantallaInventario(tk.Frame):
    """
    Pantalla 4 — Gestión de Inventario (RF-INV-01, RF-INV-02, RF-INV-03, RS-05).
    Implementa el patrón Maestro-Detalle sin modales invasivos, control de permisos
    por rol (Admin para creación/edición/baja vs Vendedor/Admin para ajuste de stock),
    stepper entero con combinación de signo, badge global y resaltado en ámbar de stock bajo.
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

        self._producto_seleccionado: Optional[Producto] = None
        self._productos_cache: Dict[int, Producto] = {}

        # Configuración de Grid: Cabecera superior y dos columnas Maestro-Detalle
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=6)  # Catálogo Maestro
        self.grid_columnconfigure(1, weight=4)  # Detalle y Acciones

        self._crear_cabecera()
        self._crear_panel_maestro_catalogo()
        self._crear_panel_detalle_acciones()

        self.al_mostrar()

    # =========================================================================
    # CABECERA: TÍTULO, BADGE GLOBAL DE ALERTAS Y FILTROS (RF-INV-03)
    # =========================================================================

    def _crear_cabecera(self) -> None:
        frame_cabecera = tk.Frame(
            self,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=14,
            pady=8,
        )
        frame_cabecera.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))

        # Título
        lbl_titulo = tk.Label(
            frame_cabecera,
            text="📦 Catálogo de Productos y Control de Stock",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_titulo.pack(side=tk.LEFT)

        # Badge Global de Alerta de Stock Bajo (RF-INV-03)
        self.frame_badge_alerta = tk.Frame(
            frame_cabecera,
            background=COLOR_ALERTA_BG,
            highlightbackground=COLOR_ALERTA_BORDE,
            highlightthickness=1,
            padx=10,
            pady=4,
        )
        self.frame_badge_alerta.pack(side=tk.RIGHT)

        self.lbl_badge_alerta = tk.Label(
            self.frame_badge_alerta,
            text="⚠️ 0 Productos en Stock Bajo",
            font=FUENTE_BASE_BOLD,
            background=COLOR_ALERTA_BG,
            foreground=COLOR_ALERTA_TEXTO,
        )
        self.lbl_badge_alerta.pack()

    # =========================================================================
    # PANEL MAESTRO: CATÁLOGO, BÚSQUEDA Y RESALTADO EN ÁMBAR (RF-INV-01, 03)
    # =========================================================================

    def _crear_panel_maestro_catalogo(self) -> None:
        panel_izq = tk.Frame(self, background=COLOR_FONDO_APP)
        panel_izq.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        panel_izq.grid_rowconfigure(1, weight=1)
        panel_izq.grid_columnconfigure(0, weight=1)

        # Barra de Búsqueda y Filtro de Stock Bajo
        frame_filtros = tk.Frame(panel_izq, background=COLOR_FONDO_APP)
        frame_filtros.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        tk.Label(
            frame_filtros,
            text="🔍 Buscar:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.entry_busqueda = ttk.Entry(frame_filtros, width=22)
        self.entry_busqueda.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_busqueda.bind("<KeyRelease>", lambda e: self._filtrar_catalogo())
        self.entry_busqueda.bind("<Return>", lambda e: self._filtrar_catalogo())

        btn_buscar = ttk.Button(
            frame_filtros, text="Buscar", command=self._filtrar_catalogo
        )
        btn_buscar.pack(side=tk.LEFT, padx=(0, 4))

        btn_limpiar = ttk.Button(
            frame_filtros, text="Limpiar", command=self._limpiar_filtros
        )
        btn_limpiar.pack(side=tk.LEFT, padx=(0, 10))

        # Selector de Filtro: Todos vs Stock Bajo
        self.var_filtro_stock = tk.StringVar(value="todos")
        r_todos = ttk.Radiobutton(
            frame_filtros,
            text="Todos los activos",
            variable=self.var_filtro_stock,
            value="todos",
            command=self._filtrar_catalogo,
        )
        r_todos.pack(side=tk.LEFT, padx=(0, 6))

        r_alerta = ttk.Radiobutton(
            frame_filtros,
            text="⚠️ Solo stock bajo",
            variable=self.var_filtro_stock,
            value="alerta",
            command=self._filtrar_catalogo,
        )
        r_alerta.pack(side=tk.LEFT)

        # Treeview de Catálogo Maestro
        frame_tree = tk.Frame(
            panel_izq,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
        )
        frame_tree.grid(row=1, column=0, sticky="nsew")
        frame_tree.grid_rowconfigure(0, weight=1)
        frame_tree.grid_columnconfigure(0, weight=1)

        columnas = ("id", "codigo", "nombre", "categoria", "costo", "precio", "stock", "stock_min", "estado")
        self.tree_catalogo = ttk.Treeview(
            frame_tree,
            columns=columnas,
            show="headings",
            selectmode="browse",
        )
        self.tree_catalogo.heading("id", text="ID")
        self.tree_catalogo.heading("codigo", text="Cód. Barras")
        self.tree_catalogo.heading("nombre", text="Producto")
        self.tree_catalogo.heading("categoria", text="Categoría")
        self.tree_catalogo.heading("costo", text="Costo")
        self.tree_catalogo.heading("precio", text="P. Venta")
        self.tree_catalogo.heading("stock", text="Stock")
        self.tree_catalogo.heading("stock_min", text="Mínimo")
        self.tree_catalogo.heading("estado", text="Alerta")

        self.tree_catalogo.column("id", width=35, anchor=tk.CENTER)
        self.tree_catalogo.column("codigo", width=105, anchor=tk.W)
        self.tree_catalogo.column("nombre", width=180, anchor=tk.W)
        self.tree_catalogo.column("categoria", width=110, anchor=tk.W)
        self.tree_catalogo.column("costo", width=75, anchor=tk.E)
        self.tree_catalogo.column("precio", width=80, anchor=tk.E)
        self.tree_catalogo.column("stock", width=55, anchor=tk.CENTER)
        self.tree_catalogo.column("stock_min", width=60, anchor=tk.CENTER)
        self.tree_catalogo.column("estado", width=70, anchor=tk.CENTER)

        # Configuración de tag de resaltado en ámbar (#fff3cd) para productos en alerta
        self.tree_catalogo.tag_configure("alerta_stock", background=COLOR_ALERTA_BG)

        scroll_tree = ttk.Scrollbar(
            frame_tree, orient="vertical", command=self.tree_catalogo.yview
        )
        self.tree_catalogo.configure(yscrollcommand=scroll_tree.set)
        self.tree_catalogo.grid(row=0, column=0, sticky="nsew")
        scroll_tree.grid(row=0, column=1, sticky="ns")

        # Vinculación Maestro-Detalle: clic en fila carga el producto sin diálogo modal
        self.tree_catalogo.bind("<<TreeviewSelect>>", self._on_producto_seleccionado)

    # =========================================================================
    # PANEL DETALLE: AJUSTE DE STOCK, EDICIÓN Y CREACIÓN (RS-05, RF-INV-01)
    # =========================================================================

    def _crear_panel_detalle_acciones(self) -> None:
        panel_der = tk.Frame(self, background=COLOR_FONDO_APP)
        panel_der.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        panel_der.grid_rowconfigure(0, weight=0)  # Ajuste de Stock
        panel_der.grid_rowconfigure(1, weight=1)  # Notebook (Editar / Crear)
        panel_der.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # Card 1: Ajuste Rápido de Stock con Signo y Stepper (RS-05)
        # Habilitado para Administrador Y Vendedor
        # ---------------------------------------------------------------------
        card_ajuste = tk.Frame(
            panel_der,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_ajuste.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.lbl_tit_ajuste = tk.Label(
            card_ajuste,
            text="⚡ Ajuste Rápido de Stock (RS-05)",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        self.lbl_tit_ajuste.pack(anchor="w", pady=(0, 4))

        self.lbl_info_prod_ajuste = tk.Label(
            card_ajuste,
            text="Seleccione un producto del catálogo para ajustar su stock.",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground="#2980b9",
        )
        self.lbl_info_prod_ajuste.pack(anchor="w", pady=(0, 6))

        # Fila de Controles: Dirección y Magnitud Entera
        frame_controles_ajuste = tk.Frame(card_ajuste, background=COLOR_BLANCO)
        frame_controles_ajuste.pack(fill=tk.X, pady=(2, 6))

        # Selector de Dirección (Entrada vs Salida)
        self.var_direccion_ajuste = tk.StringVar(value="entrada")
        r_entrada = ttk.Radiobutton(
            frame_controles_ajuste,
            text="📥 Entrada (+)",
            variable=self.var_direccion_ajuste,
            value="entrada",
        )
        r_entrada.pack(side=tk.LEFT, padx=(0, 10))

        r_salida = ttk.Radiobutton(
            frame_controles_ajuste,
            text="📤 Salida (-)",
            variable=self.var_direccion_ajuste,
            value="salida",
        )
        r_salida.pack(side=tk.LEFT, padx=(0, 15))

        tk.Label(
            frame_controles_ajuste,
            text="Cant:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).pack(side=tk.LEFT, padx=(0, 4))

        # Stepper Entero (Sin decimales)
        self.spin_magnitud = ttk.Spinbox(
            frame_controles_ajuste, from_=1, to=9999, width=5, font=("Segoe UI", 10, "bold")
        )
        self.spin_magnitud.set(1)
        self.spin_magnitud.pack(side=tk.LEFT, padx=(0, 8))

        # Botones Rápidos de Incremento
        for delta in (1, 5, 10):
            btn_step = ttk.Button(
                frame_controles_ajuste,
                text=f"+{delta}",
                width=3,
                command=lambda d=delta: self._incrementar_stepper(d),
            )
            btn_step.pack(side=tk.LEFT, padx=1)

        # Botón Confirmar Ajuste (Habilitado para TODOS: Admin y Vendedor)
        self.btn_confirmar_ajuste = ttk.Button(
            card_ajuste,
            text="⚡ Confirmar Ajuste de Stock",
            style="Primary.TButton",
            command=self._confirmar_ajuste_stock,
        )
        self.btn_confirmar_ajuste.pack(fill=tk.X, pady=(4, 0))

        self.area_error_ajuste = AreaError(card_ajuste)
        self.lbl_exito_ajuste = tk.Label(
            card_ajuste,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
        )
        self.lbl_exito_ajuste.pack(anchor="w", pady=(2, 0))

        # ---------------------------------------------------------------------
        # Card 2: Pestañas de Edición y Creación (Notebook)
        # ---------------------------------------------------------------------
        self.notebook = ttk.Notebook(panel_der)
        self.notebook.grid(row=1, column=0, sticky="nsew")

        # Pestaña 1: Editar Producto Seleccionado (Admin-Only)
        self.tab_editar = tk.Frame(self.notebook, background=COLOR_BLANCO, padx=12, pady=10)
        self.notebook.add(self.tab_editar, text="✏️ Editar Producto")
        self._construir_formulario_edicion(self.tab_editar)

        # Pestaña 2: Crear Nuevo Producto (Admin-Only)
        self.tab_crear = tk.Frame(self.notebook, background=COLOR_BLANCO, padx=12, pady=10)
        self.notebook.add(self.tab_crear, text="➕ Crear Producto")
        self._construir_formulario_creacion(self.tab_crear)

    # =========================================================================
    # FORMULARIO DE EDICIÓN (ADMIN-ONLY) (RF-INV-01)
    # =========================================================================

    def _construir_formulario_edicion(self, parent: tk.Widget) -> None:
        parent.columnconfigure(1, weight=1)

        # Nombre
        tk.Label(parent, text="Nombre del Producto:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_edit_nombre = ttk.Entry(parent)
        self.entry_edit_nombre.grid(row=0, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Categoría restringida por CHECK
        tk.Label(parent, text="Categoría:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=1, column=0, sticky="w", pady=2)
        self.combo_edit_cat = ttk.Combobox(parent, values=list(CATEGORIAS_VALIDAS), state="readonly")
        self.combo_edit_cat.grid(row=1, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Precio Venta y Costo
        tk.Label(parent, text="Precio de Venta ($):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=2, column=0, sticky="w", pady=2)
        self.entry_edit_precio = ttk.Entry(parent)
        self.entry_edit_precio.grid(row=2, column=1, sticky="ew", pady=2, padx=(6, 0))

        tk.Label(parent, text="Costo ($):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=3, column=0, sticky="w", pady=2)
        self.entry_edit_costo = ttk.Entry(parent)
        self.entry_edit_costo.grid(row=3, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Stock Mínimo (Entero)
        tk.Label(parent, text="Stock Mínimo (Alerta):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=4, column=0, sticky="w", pady=2)
        self.entry_edit_stock_min = ttk.Entry(parent)
        self.entry_edit_stock_min.grid(row=4, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Código de barras
        tk.Label(parent, text="Código de Barras:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=5, column=0, sticky="w", pady=2)
        self.entry_edit_codigo = ttk.Entry(parent)
        self.entry_edit_codigo.grid(row=5, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Mensajes de error y confirmación
        self.area_error_edit = AreaError(parent)
        self.lbl_exito_edit = tk.Label(parent, text="", background=COLOR_BLANCO, foreground=COLOR_EXITO, font=FUENTE_BASE_BOLD)
        self.lbl_exito_edit.grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Botones de Acción (Admin-Only vía BotonRestringidoPorRol)
        frame_btns_edit = tk.Frame(parent, background=COLOR_BLANCO)
        frame_btns_edit.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        self.btn_guardar_edit = BotonRestringidoPorRol(
            frame_btns_edit,
            sesion=self.sesion,
            roles_permitidos=["admin"],
            text="💾 Guardar Cambios (Admin)",
            style="Primary.TButton",
            command=self._guardar_edicion,
        )
        self.btn_guardar_edit.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_desactivar = BotonRestringidoPorRol(
            frame_btns_edit,
            sesion=self.sesion,
            roles_permitidos=["admin"],
            text="🗑️ Desactivar (Baja)",
            style="Danger.TButton",
            command=self._desactivar_producto,
        )
        self.btn_desactivar.pack(side=tk.LEFT)

    # =========================================================================
    # FORMULARIO DE CREACIÓN (ADMIN-ONLY) (RF-INV-01)
    # =========================================================================

    def _construir_formulario_creacion(self, parent: tk.Widget) -> None:
        parent.columnconfigure(1, weight=1)

        # Nombre
        tk.Label(parent, text="Nombre del Producto (*):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_crear_nombre = ttk.Entry(parent)
        self.entry_crear_nombre.grid(row=0, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Categoría restringida por CHECK
        tk.Label(parent, text="Categoría (*):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=1, column=0, sticky="w", pady=2)
        self.combo_crear_cat = ttk.Combobox(parent, values=list(CATEGORIAS_VALIDAS), state="readonly")
        self.combo_crear_cat.set("canasta_basica")
        self.combo_crear_cat.grid(row=1, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Precio Venta y Costo
        tk.Label(parent, text="Precio Venta ($) (*):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=2, column=0, sticky="w", pady=2)
        self.entry_crear_precio = ttk.Entry(parent)
        self.entry_crear_precio.grid(row=2, column=1, sticky="ew", pady=2, padx=(6, 0))

        tk.Label(parent, text="Costo ($) (*):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=3, column=0, sticky="w", pady=2)
        self.entry_crear_costo = ttk.Entry(parent)
        self.entry_crear_costo.grid(row=3, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Stock Inicial y Mínimo (Enteros)
        tk.Label(parent, text="Stock Inicial:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=4, column=0, sticky="w", pady=2)
        self.entry_crear_stock = ttk.Entry(parent)
        self.entry_crear_stock.insert(0, "0")
        self.entry_crear_stock.grid(row=4, column=1, sticky="ew", pady=2, padx=(6, 0))

        tk.Label(parent, text="Stock Mínimo (Alerta):", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=5, column=0, sticky="w", pady=2)
        self.entry_crear_stock_min = ttk.Entry(parent)
        self.entry_crear_stock_min.insert(0, "5")
        self.entry_crear_stock_min.grid(row=5, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Código de barras
        tk.Label(parent, text="Código de Barras:", font=FUENTE_BASE_BOLD, background=COLOR_BLANCO).grid(row=6, column=0, sticky="w", pady=2)
        self.entry_crear_codigo = ttk.Entry(parent)
        self.entry_crear_codigo.grid(row=6, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Mensajes
        self.area_error_crear = AreaError(parent)
        self.lbl_exito_crear = tk.Label(parent, text="", background=COLOR_BLANCO, foreground=COLOR_EXITO, font=FUENTE_BASE_BOLD)
        self.lbl_exito_crear.grid(row=8, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Botón Guardar Producto (Admin-Only vía BotonRestringidoPorRol)
        self.btn_guardar_crear = BotonRestringidoPorRol(
            parent,
            sesion=self.sesion,
            roles_permitidos=["admin"],
            text="➕ Guardar Producto (Admin)",
            style="Primary.TButton",
            command=self._crear_producto,
        )
        self.btn_guardar_crear.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    # =========================================================================
    # LÓGICA DE MANIPULACIÓN Y EVENTOS
    # =========================================================================

    def _incrementar_stepper(self, delta: int) -> None:
        """Incrementa la magnitud entera del stepper."""
        try:
            val = int(self.spin_magnitud.get() or 1)
        except ValueError:
            val = 1
        self.spin_magnitud.delete(0, tk.END)
        self.spin_magnitud.insert(0, str(val + delta))

    def _on_producto_seleccionado(self, event=None) -> None:
        """Carga el producto seleccionado en los controles de ajuste y edición sin abrir modal."""
        if event is not None:
            self._limpiar_mensajes()
        seleccion = self.tree_catalogo.selection()
        if not seleccion:
            return

        item_id = self.tree_catalogo.item(seleccion[0], "values")[0]
        try:
            prod_id = int(item_id)
        except ValueError:
            return

        prod = inventario_service.obtener_producto(prod_id, self.sesion.conn)
        if not prod:
            return

        self._producto_seleccionado = prod

        # Cargar info en Ajuste de Stock
        self.lbl_info_prod_ajuste.config(
            text=f"📦 [{prod.id}] {prod.nombre} | Stock actual: {prod.stock} (Mín: {prod.stock_minimo})"
        )

        # Cargar info en Formulario de Edición
        self.entry_edit_nombre.delete(0, tk.END)
        self.entry_edit_nombre.insert(0, prod.nombre)

        self.combo_edit_cat.set(prod.categoria)

        self.entry_edit_precio.delete(0, tk.END)
        self.entry_edit_precio.insert(0, f"{prod.precio_venta:.2f}")

        self.entry_edit_costo.delete(0, tk.END)
        self.entry_edit_costo.insert(0, f"{prod.costo:.2f}")

        self.entry_edit_stock_min.delete(0, tk.END)
        self.entry_edit_stock_min.insert(0, str(prod.stock_minimo))

        self.entry_edit_codigo.delete(0, tk.END)
        self.entry_edit_codigo.insert(0, prod.codigo_barras or "")

    def _confirmar_ajuste_stock(self) -> None:
        """
        Ejecuta el ajuste de stock combinando la dirección y magnitud entera con signo (RS-05).
        Delega el rechazo al backend si el stock resultante sería negativo.
        """
        self.area_error_ajuste.limpiar()
        self.lbl_exito_ajuste.config(text="")

        if not self._producto_seleccionado:
            self.area_error_ajuste.mostrar_error("Seleccione primero un producto del catálogo para ajustar.")
            return

        texto_mag = self.spin_magnitud.get().strip()
        try:
            # Forzar validación entera estricta
            magnitud = int(texto_mag)
            if magnitud <= 0:
                raise ValueError()
        except ValueError:
            self.area_error_ajuste.mostrar_error("La cantidad de ajuste debe ser un número entero mayor a cero.")
            return

        direccion = self.var_direccion_ajuste.get()
        cantidad_con_signo = magnitud if direccion == "entrada" else -magnitud

        try:
            prod_actualizado = inventario_service.ajustar_stock(
                producto_id=self._producto_seleccionado.id,
                cantidad=cantidad_con_signo,
                conn=self.sesion.conn,
                auto_commit=True,
            )
            self._producto_seleccionado = prod_actualizado
            self.lbl_exito_ajuste.config(
                text=f"✅ Stock de '{prod_actualizado.nombre}' ajustado a {prod_actualizado.stock} unidades."
            )
            self._refrescar_todo(mantener_id=prod_actualizado.id)

        except ValueError as e:
            self.area_error_ajuste.mostrar_error(str(e))
        except Exception as e:
            self.area_error_ajuste.mostrar_error(f"Error inesperado al ajustar stock: {e}")

    def _guardar_edicion(self) -> None:
        """Actualiza el catálogo del producto seleccionado (Admin-Only)."""
        self.area_error_edit.limpiar()
        self.lbl_exito_edit.config(text="")

        if not self._producto_seleccionado:
            self.area_error_edit.mostrar_error("Seleccione un producto para editar.")
            return

        nombre = self.entry_edit_nombre.get().strip()
        cat = self.combo_edit_cat.get()
        cod = self.entry_edit_codigo.get().strip() or None

        try:
            precio = float(self.entry_edit_precio.get().strip())
            costo = float(self.entry_edit_costo.get().strip())
            stock_min = int(self.entry_edit_stock_min.get().strip())
        except ValueError:
            self.area_error_edit.mostrar_error("Verifique que precio, costo y stock mínimo tengan formato numérico válido.")
            return

        try:
            prod_actualizado = inventario_service.actualizar_producto(
                producto_id=self._producto_seleccionado.id,
                conn=self.sesion.conn,
                nombre=nombre,
                categoria=cat,
                precio_venta=precio,
                costo=costo,
                stock_minimo=stock_min,
                codigo_barras=cod,
            )
            self._producto_seleccionado = prod_actualizado
            self.lbl_exito_edit.config(text=f"✅ Producto '{prod_actualizado.nombre}' actualizado.")
            self._refrescar_todo(mantener_id=prod_actualizado.id)

        except ValueError as e:
            self.area_error_edit.mostrar_error(str(e))
        except Exception as e:
            self.area_error_edit.mostrar_error(f"Error inesperado al actualizar: {e}")

    def _desactivar_producto(self) -> None:
        """Baja lógica de producto (Admin-Only)."""
        self.area_error_edit.limpiar()
        self.lbl_exito_edit.config(text="")

        if not self._producto_seleccionado:
            self.area_error_edit.mostrar_error("Seleccione un producto para desactivar.")
            return

        try:
            inventario_service.desactivar_producto(
                producto_id=self._producto_seleccionado.id,
                conn=self.sesion.conn,
            )
            self.lbl_exito_edit.config(
                text=f"✅ Producto '{self._producto_seleccionado.nombre}' desactivado del catálogo."
            )
            self._producto_seleccionado = None
            self.lbl_info_prod_ajuste.config(
                text="Seleccione un producto del catálogo para ajustar su stock."
            )
            self._refrescar_todo()

        except ValueError as e:
            self.area_error_edit.mostrar_error(str(e))
        except Exception as e:
            self.area_error_edit.mostrar_error(f"Error inesperado al desactivar: {e}")

    def _crear_producto(self) -> None:
        """Crea y persiste un nuevo producto en el catálogo (Admin-Only)."""
        self.area_error_crear.limpiar()
        self.lbl_exito_crear.config(text="")

        nombre = self.entry_crear_nombre.get().strip()
        cat = self.combo_crear_cat.get()
        cod = self.entry_crear_codigo.get().strip() or None

        try:
            precio = float(self.entry_crear_precio.get().strip())
            costo = float(self.entry_crear_costo.get().strip())
            stock = int(self.entry_crear_stock.get().strip() or 0)
            stock_min = int(self.entry_crear_stock_min.get().strip() or 5)
        except ValueError:
            self.area_error_crear.mostrar_error("Precios, costos y stocks deben contener valores numéricos válidos.")
            return

        try:
            nuevo = inventario_service.crear_producto(
                nombre=nombre,
                categoria=cat,
                precio_venta=precio,
                costo=costo,
                conn=self.sesion.conn,
                codigo_barras=cod,
                stock=stock,
                stock_minimo=stock_min,
            )
            self.entry_crear_nombre.delete(0, tk.END)
            self.entry_crear_precio.delete(0, tk.END)
            self.entry_crear_costo.delete(0, tk.END)
            self.entry_crear_codigo.delete(0, tk.END)
            self._refrescar_todo(mantener_id=nuevo.id)
            self.lbl_exito_crear.config(text=f"✅ Producto '{nuevo.nombre}' creado exitosamente (ID: {nuevo.id}).")

        except ValueError as e:
            self.area_error_crear.mostrar_error(str(e))
        except Exception as e:
            self.area_error_crear.mostrar_error(f"Error inesperado al crear producto: {e}")

    # =========================================================================
    # RECARGA, FILTRADO Y CICLO DE VIDA (al_mostrar)
    # =========================================================================

    def _limpiar_mensajes(self) -> None:
        """Limpia las áreas de error y confirmación visual."""
        self.area_error_ajuste.limpiar()
        self.area_error_edit.limpiar()
        self.area_error_crear.limpiar()
        self.lbl_exito_ajuste.config(text="")
        self.lbl_exito_edit.config(text="")
        self.lbl_exito_crear.config(text="")

    def _refrescar_todo(self, mantener_id: Optional[int] = None) -> None:
        """Actualiza el catálogo, el badge de alertas y resalta filas en ámbar."""
        self._cargar_catalogo(mantener_id=mantener_id)
        self._actualizar_badge_alerta()

    def _actualizar_badge_alerta(self) -> None:
        """Refresca el conteo global de productos en alerta de stock."""
        alertas = inventario_service.listar_alertas_stock(self.sesion.conn)
        total_alertas = len(alertas)
        if total_alertas > 0:
            self.lbl_badge_alerta.config(
                text=f"⚠️ {total_alertas} Producto{'s' if total_alertas > 1 else ''} en Stock Bajo",
                foreground=COLOR_ALERTA_TEXTO,
            )
            self.frame_badge_alerta.config(background=COLOR_ALERTA_BG)
        else:
            self.lbl_badge_alerta.config(
                text="✅ Stock en Niveles Óptimos",
                foreground="#155724",
            )
            self.frame_badge_alerta.config(background="#d4edda")

    def _cargar_catalogo(self, mantener_id: Optional[int] = None) -> None:
        """Carga productos en el Treeview aplicando filtros y resaltando en ámbar."""
        for row in self.tree_catalogo.get_children():
            self.tree_catalogo.delete(row)

        self._productos_cache.clear()
        termino = self.entry_busqueda.get().strip()
        filtro_alerta = self.var_filtro_stock.get() == "alerta"

        if filtro_alerta:
            productos = inventario_service.listar_alertas_stock(self.sesion.conn)
            if termino:
                termino_l = termino.lower()
                productos = [
                    p for p in productos
                    if termino_l in p.nombre.lower() or (p.codigo_barras and termino_l in p.codigo_barras.lower())
                ]
        else:
            if termino:
                productos = inventario_service.buscar_productos(termino, self.sesion.conn, solo_activos=True)
            else:
                productos = inventario_service.listar_productos(self.sesion.conn, solo_activos=True)

        item_a_seleccionar = None

        for p in productos:
            self._productos_cache[p.id] = p
            es_alerta = p.stock <= p.stock_minimo
            tags = ("alerta_stock",) if es_alerta else ()
            estado_txt = "⚠️ BAJO" if es_alerta else "OK"

            item = self.tree_catalogo.insert(
                "",
                tk.END,
                values=(
                    p.id,
                    p.codigo_barras or "S/C",
                    p.nombre,
                    p.categoria,
                    f"${p.costo:,.2f}",
                    f"${p.precio_venta:,.2f}",
                    p.stock,
                    p.stock_minimo,
                    estado_txt,
                ),
                tags=tags,
            )
            if mantener_id and p.id == mantener_id:
                item_a_seleccionar = item

        if item_a_seleccionar:
            self.tree_catalogo.selection_set(item_a_seleccionar)
            self._on_producto_seleccionado()

    def _filtrar_catalogo(self) -> None:
        """Dispara el refresco del catálogo filtrado."""
        self._cargar_catalogo(
            mantener_id=self._producto_seleccionado.id if self._producto_seleccionado else None
        )

    def _limpiar_filtros(self) -> None:
        """Limpia el término de búsqueda y resetea el filtro a todos."""
        self.entry_busqueda.delete(0, tk.END)
        self.var_filtro_stock.set("todos")
        self._cargar_catalogo()

    def al_mostrar(self) -> None:
        """Hook invocado al navegar a esta pantalla para sincronizar permisos y datos."""
        self._limpiar_mensajes()
        # Refrescar botones restringidos por rol
        self.btn_guardar_edit.actualizar_estado()
        self.btn_desactivar.actualizar_estado()
        self.btn_guardar_crear.actualizar_estado()
        self._refrescar_todo(
            mantener_id=self._producto_seleccionado.id if self._producto_seleccionado else None
        )
