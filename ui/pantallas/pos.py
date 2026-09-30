import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

from models.cliente import Cliente
from models.producto import Producto
from models.venta import Venta
from services import cxc_service, inventario_service, pos_service
from services.pos_service import LineaVentaInput
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
    COLOR_EXITO_HOVER,
    COLOR_FONDO_APP,
    COLOR_PRIMARIO,
    COLOR_TEXTO_MUTED,
    COLOR_TEXTO_PRINCIPAL,
    COLOR_TEXTO_SECUNDARIO,
    COLORES_SCORING,
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
from ui.widgets_comunes import AreaError


class PantallaPOS(tk.Frame):
    """
    Pantalla 2 — Punto de Venta (POS) (RF-POS-01 a RF-POS-04, RF-CXC-05).
    Gestiona el catálogo de productos con búsqueda en tiempo real, venta rápida sin catalogar,
    carrito en memoria como fuente única de verdad, tarjeta reactiva de crédito y despacho transaccional.
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

        # 1. Estado en memoria del Carrito (Fuente única de verdad)
        self._carrito: List[Dict[str, Any]] = []

        # Estado del cliente seleccionado y productos cargados
        self._cliente_actual: Optional[Cliente] = None
        self._clientes_map: Dict[str, int] = {}
        self._productos_cache: Dict[int, Producto] = {}

        # 2. Layout principal: Dos columnas (Izquierda: Catálogo/Carrito, Derecha: Pago/Crédito)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=6)
        self.grid_columnconfigure(1, weight=4)

        self._crear_panel_izquierdo()
        self._crear_panel_derecho()

        # 3. Cargar datos iniciales
        self.al_mostrar()

    # =========================================================================
    # PANEL IZQUIERDO: CATÁLOGO Y CARRITO
    # =========================================================================

    def _crear_panel_izquierdo(self) -> None:
        panel_izq = tk.Frame(self, background=COLOR_FONDO_APP)
        panel_izq.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        panel_izq.grid_rowconfigure(1, weight=4)  # Catálogo
        panel_izq.grid_rowconfigure(3, weight=5)  # Carrito
        panel_izq.grid_columnconfigure(0, weight=1)

        # --- A. Búsqueda y Catálogo de Productos ---
        frame_busqueda = tk.Frame(panel_izq, background=COLOR_FONDO_APP)
        frame_busqueda.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        lbl_buscar = tk.Label(
            frame_busqueda,
            text="🔍 Buscar Producto:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_buscar.pack(side=tk.LEFT, padx=(0, 6))

        self.entry_busqueda_prod = ttk.Entry(frame_busqueda, width=28)
        self.entry_busqueda_prod.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry_busqueda_prod.bind("<KeyRelease>", lambda e: self._filtrar_productos())
        self.entry_busqueda_prod.bind("<Return>", lambda e: self._filtrar_productos())

        btn_buscar = ttk.Button(
            frame_busqueda, text="Buscar", command=self._filtrar_productos
        )
        btn_buscar.pack(side=tk.LEFT, padx=(0, 4))

        btn_limpiar_b = ttk.Button(
            frame_busqueda, text="Limpiar", command=self._limpiar_busqueda_prod
        )
        btn_limpiar_b.pack(side=tk.LEFT)

        # Treeview de Catálogo
        frame_tree_cat = tk.Frame(
            panel_izq,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
        )
        frame_tree_cat.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        frame_tree_cat.grid_rowconfigure(0, weight=1)
        frame_tree_cat.grid_columnconfigure(0, weight=1)

        columnas_cat = ("id", "codigo", "nombre", "categoria", "precio", "stock")
        self.tree_catalogo = ttk.Treeview(
            frame_tree_cat,
            columns=columnas_cat,
            show="headings",
            selectmode="browse",
            height=6,
        )
        self.tree_catalogo.heading("id", text="ID")
        self.tree_catalogo.heading("codigo", text="Cód. Barras")
        self.tree_catalogo.heading("nombre", text="Producto")
        self.tree_catalogo.heading("categoria", text="Categoría")
        self.tree_catalogo.heading("precio", text="Precio Venta")
        self.tree_catalogo.heading("stock", text="Stock")

        self.tree_catalogo.column("id", width=40, anchor=tk.CENTER)
        self.tree_catalogo.column("codigo", width=100, anchor=tk.W)
        self.tree_catalogo.column("nombre", width=180, anchor=tk.W)
        self.tree_catalogo.column("categoria", width=110, anchor=tk.W)
        self.tree_catalogo.column("precio", width=85, anchor=tk.E)
        self.tree_catalogo.column("stock", width=60, anchor=tk.CENTER)

        scroll_cat = ttk.Scrollbar(
            frame_tree_cat, orient="vertical", command=self.tree_catalogo.yview
        )
        self.tree_catalogo.configure(yscrollcommand=scroll_cat.set)
        self.tree_catalogo.grid(row=0, column=0, sticky="nsew")
        scroll_cat.grid(row=0, column=1, sticky="ns")

        self.tree_catalogo.bind("<Double-1>", lambda e: self._agregar_producto_seleccionado())

        # Barra de acción del Catálogo y Venta Rápida por Monto
        frame_acciones_cat = tk.Frame(panel_izq, background=COLOR_FONDO_APP)
        frame_acciones_cat.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        lbl_cant = tk.Label(
            frame_acciones_cat,
            text="Cant:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
        )
        lbl_cant.pack(side=tk.LEFT, padx=(0, 4))

        self.spin_cant_agregar = ttk.Spinbox(
            frame_acciones_cat, from_=1, to=999, width=4
        )
        self.spin_cant_agregar.set(1)
        self.spin_cant_agregar.pack(side=tk.LEFT, padx=(0, 8))

        btn_agregar_cat = ttk.Button(
            frame_acciones_cat,
            text="➕ Agregar al Carrito",
            command=self._agregar_producto_seleccionado,
        )
        btn_agregar_cat.pack(side=tk.LEFT, padx=(0, 15))

        # --- Separador / Sección Venta por Monto Global (RF-POS-02) ---
        lbl_monto_directo = tk.Label(
            frame_acciones_cat,
            text="| Venta Rápida $: ",
            font=FUENTE_BASE_BOLD,
            background=COLOR_FONDO_APP,
            foreground="#2980b9",
        )
        lbl_monto_directo.pack(side=tk.LEFT, padx=(5, 2))

        self.entry_monto_directo = ttk.Entry(frame_acciones_cat, width=9)
        self.entry_monto_directo.pack(side=tk.LEFT, padx=(0, 4))
        self.entry_monto_directo.bind("<Return>", lambda e: self._agregar_monto_global())

        self.entry_desc_directo = ttk.Entry(frame_acciones_cat, width=14)
        self.entry_desc_directo.insert(0, "Venta rápida")
        self.entry_desc_directo.pack(side=tk.LEFT, padx=(0, 4))

        btn_agregar_monto = ttk.Button(
            frame_acciones_cat,
            text="➕ Monto",
            command=self._agregar_monto_global,
        )
        btn_agregar_monto.pack(side=tk.LEFT)

        # --- B. Carrito de Compras (En Memoria) ---
        frame_carrito_header = tk.Frame(panel_izq, background=COLOR_FONDO_APP)
        frame_carrito_header.grid(row=3, column=0, sticky="nsew")
        frame_carrito_header.grid_rowconfigure(1, weight=1)
        frame_carrito_header.grid_columnconfigure(0, weight=1)

        lbl_tit_carrito = tk.Label(
            frame_carrito_header,
            text="🛒 Carrito de Venta",
            font=FUENTE_SUBTITULO,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_carrito.grid(row=0, column=0, sticky="w", pady=(0, 4))

        frame_tree_car = tk.Frame(
            frame_carrito_header,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
        )
        frame_tree_car.grid(row=1, column=0, sticky="nsew")
        frame_tree_car.grid_rowconfigure(0, weight=1)
        frame_tree_car.grid_columnconfigure(0, weight=1)

        columnas_car = ("index", "descripcion", "cantidad", "precio", "subtotal")
        self.tree_carrito = ttk.Treeview(
            frame_tree_car,
            columns=columnas_car,
            show="headings",
            selectmode="browse",
            height=7,
        )
        self.tree_carrito.heading("index", text="#")
        self.tree_carrito.heading("descripcion", text="Descripción / Producto")
        self.tree_carrito.heading("cantidad", text="Cant.")
        self.tree_carrito.heading("precio", text="P. Unitario")
        self.tree_carrito.heading("subtotal", text="Subtotal")

        self.tree_carrito.column("index", width=30, anchor=tk.CENTER)
        self.tree_carrito.column("descripcion", width=220, anchor=tk.W)
        self.tree_carrito.column("cantidad", width=65, anchor=tk.CENTER)
        self.tree_carrito.column("precio", width=95, anchor=tk.E)
        self.tree_carrito.column("subtotal", width=105, anchor=tk.E)

        scroll_car = ttk.Scrollbar(
            frame_tree_car, orient="vertical", command=self.tree_carrito.yview
        )
        self.tree_carrito.configure(yscrollcommand=scroll_car.set)
        self.tree_carrito.grid(row=0, column=0, sticky="nsew")
        scroll_car.grid(row=0, column=1, sticky="ns")

        # Controles y Resumen del Carrito
        frame_carrito_footer = tk.Frame(panel_izq, background=COLOR_FONDO_APP)
        frame_carrito_footer.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        btn_mas = ttk.Button(
            frame_carrito_footer, text="➕ 1", width=5, command=lambda: self._modificar_cantidad_seleccion(1)
        )
        btn_mas.pack(side=tk.LEFT, padx=(0, 4))

        btn_menos = ttk.Button(
            frame_carrito_footer, text="➖ 1", width=5, command=lambda: self._modificar_cantidad_seleccion(-1)
        )
        btn_menos.pack(side=tk.LEFT, padx=(0, 4))

        btn_eliminar = ttk.Button(
            frame_carrito_footer, text="🗑️ Quitar", command=self._quitar_item_seleccionado
        )
        btn_eliminar.pack(side=tk.LEFT, padx=(0, 4))

        btn_vaciar = ttk.Button(
            frame_carrito_footer, text="🧹 Vaciar", command=self._vaciar_carrito
        )
        btn_vaciar.pack(side=tk.LEFT)

        self.lbl_total_carrito = tk.Label(
            frame_carrito_footer,
            text="Total: $ 0.00",
            font=FUENTE_TITULO,
            background=COLOR_FONDO_APP,
            foreground="#16a085",
        )
        self.lbl_total_carrito.pack(side=tk.RIGHT)

    # =========================================================================
    # PANEL DERECHO: CLIENTE, CRÉDITO Y CONFIRMACIÓN DE VENTA
    # =========================================================================

    def _crear_panel_derecho(self) -> None:
        panel_der = tk.Frame(
            self,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        panel_der.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        # 1. Sección Cliente / Cartera (RF-CXC-01, RF-POS-03)
        lbl_sec_cli = tk.Label(
            panel_der,
            text="👤 Ficha del Cliente / Cartera",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_sec_cli.pack(anchor="w", pady=(0, 4))

        self.combo_clientes = ttk.Combobox(panel_der, state="readonly", width=34)
        self.combo_clientes.pack(fill=tk.X, pady=(0, 8))
        self.combo_clientes.bind("<<ComboboxSelected>>", self._on_cliente_seleccionado)

        # Tarjeta visual de estado crediticio
        self.frame_card_credito = tk.Frame(
            panel_der,
            background="#f8f9fa",
            highlightbackground="#e9ecef",
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        self.frame_card_credito.pack(fill=tk.X, pady=(0, 10))

        self.lbl_card_nombre = tk.Label(
            self.frame_card_credito,
            text="Cliente: Mostrador (Sin registrar)",
            font=FUENTE_BASE_BOLD,
            background="#f8f9fa",
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        self.lbl_card_nombre.pack(anchor="w")

        # Fila de métricas: Límite, Saldo, Cupo
        frame_metricas_c = tk.Frame(self.frame_card_credito, background="#f8f9fa")
        frame_metricas_c.pack(fill=tk.X, pady=(4, 2))

        self.lbl_card_limite = tk.Label(
            frame_metricas_c,
            text="Límite: $ 0.00",
            font=FUENTE_PEQUENA,
            background="#f8f9fa",
            foreground=COLOR_TEXTO_SECUNDARIO,
        )
        self.lbl_card_limite.pack(side=tk.LEFT, expand=True, anchor="w")

        self.lbl_card_saldo = tk.Label(
            frame_metricas_c,
            text="Saldo: $ 0.00",
            font=FUENTE_PEQUENA,
            background="#f8f9fa",
            foreground=COLOR_TEXTO_SECUNDARIO,
        )
        self.lbl_card_saldo.pack(side=tk.LEFT, expand=True, anchor="center")

        self.lbl_card_cupo = tk.Label(
            frame_metricas_c,
            text="Cupo Disp: $ 0.00",
            font=FUENTE_BASE_BOLD,
            background="#f8f9fa",
            foreground="#27ae60",
        )
        self.lbl_card_cupo.pack(side=tk.RIGHT, expand=True, anchor="e")

        # Badge de Categoría de Riesgo / Alerta
        self.lbl_card_scoring = tk.Label(
            self.frame_card_credito,
            text="Sin historial crediticio",
            font=FUENTE_PEQUENA,
            background="#f8f9fa",
            foreground=COLOR_TEXTO_MUTED,
        )
        self.lbl_card_scoring.pack(anchor="w", pady=(2, 0))

        # 2. Selector de Tipo de Pago (RF-POS-03)
        lbl_sec_pago = tk.Label(
            panel_der,
            text="💳 Método de Pago",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_sec_pago.pack(anchor="w", pady=(6, 4))

        self.var_tipo_pago = tk.StringVar(value="efectivo")
        frame_radios = tk.Frame(panel_der, background=COLOR_BLANCO)
        frame_radios.pack(fill=tk.X, pady=(0, 8))

        r_efectivo = tk.Radiobutton(
            frame_radios,
            text="💵 Efectivo",
            variable=self.var_tipo_pago,
            value="efectivo",
            background=COLOR_BLANCO,
            font=FUENTE_BASE,
            command=self._on_tipo_pago_cambiado,
        )
        r_efectivo.pack(side=tk.LEFT, padx=(0, 10))

        r_nequi = tk.Radiobutton(
            frame_radios,
            text="📱 Nequi",
            variable=self.var_tipo_pago,
            value="nequi",
            background=COLOR_BLANCO,
            font=FUENTE_BASE,
            command=self._on_tipo_pago_cambiado,
        )
        r_nequi.pack(side=tk.LEFT, padx=(0, 10))

        r_credito = tk.Radiobutton(
            frame_radios,
            text="📑 Crédito (Fiar)",
            variable=self.var_tipo_pago,
            value="credito",
            background=COLOR_BLANCO,
            font=FUENTE_BASE,
            command=self._on_tipo_pago_cambiado,
        )
        r_credito.pack(side=tk.LEFT)

        # 3. Inputs Reactivos de Cobro / Monto Pagado
        frame_cobro = tk.Frame(panel_der, background=COLOR_BLANCO)
        frame_cobro.pack(fill=tk.X, pady=(4, 10))

        self.lbl_monto_recibido = tk.Label(
            frame_cobro,
            text="Monto Recibido ($):",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        self.lbl_monto_recibido.pack(anchor="w")

        self.entry_monto_recibido = ttk.Entry(frame_cobro, font=("Segoe UI", 12))
        self.entry_monto_recibido.pack(fill=tk.X, pady=(2, 6))
        self.entry_monto_recibido.bind("<KeyRelease>", lambda e: self._calcular_cambio_o_saldo())

        # Etiqueta dinámica: Cambio / Saldo a Financiar
        self.lbl_resultado_pago = tk.Label(
            frame_cobro,
            text="Cambio: $ 0.00",
            font=FUENTE_TITULO,
            background=COLOR_BLANCO,
            foreground="#2980b9",
        )
        self.lbl_resultado_pago.pack(anchor="w", pady=(2, 0))

        # 4. Notificación de éxito post-venta
        self.frame_exito = tk.Frame(
            panel_der,
            background="#d4edda",
            highlightbackground="#27ae60",
            highlightthickness=1,
            padx=8,
            pady=6,
        )
        self.lbl_exito = tk.Label(
            self.frame_exito,
            text="",
            background="#d4edda",
            foreground="#155724",
            font=FUENTE_BASE_BOLD,
            wraplength=350,
            justify=tk.LEFT,
        )
        self.lbl_exito.pack(fill=tk.X)
        self.frame_exito.pack_forget()

        # 5. Componente de Errores de Negocio
        self.area_error = AreaError(panel_der)

        # 6. Botón de Acción Principal (Confirmar Venta)
        self.btn_confirmar_venta = ttk.Button(
            panel_der,
            text="✅ Confirmar y Cobrar Venta",
            style="Primary.TButton",
            command=self._confirmar_venta,
        )
        self.btn_confirmar_venta.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

    # =========================================================================
    # LÓGICA DEL CARRITO (EN MEMORIA)
    # =========================================================================

    def _agregar_producto_seleccionado(self) -> None:
        """Agrega el producto seleccionado en el catálogo al carrito en memoria."""
        seleccion = self.tree_catalogo.selection()
        if not seleccion:
            self.area_error.mostrar_error("Seleccione un producto del catálogo para agregarlo.")
            return

        item_id = self.tree_catalogo.item(seleccion[0], "values")[0]
        try:
            prod_id = int(item_id)
        except ValueError:
            return

        producto = self._productos_cache.get(prod_id)
        if not producto:
            return

        try:
            cant = float(self.spin_cant_agregar.get() or 1)
            if cant <= 0:
                raise ValueError()
        except ValueError:
            self.area_error.mostrar_error("La cantidad a agregar debe ser un número mayor a cero.")
            return

        # Verificar si ya existe en el carrito para sumar cantidad
        existente = next((it for it in self._carrito if it.get("producto_id") == prod_id), None)
        if existente:
            existente["cantidad"] += cant
            existente["subtotal"] = round(existente["cantidad"] * existente["precio_unitario"], 2)
        else:
            self._carrito.append(
                {
                    "producto_id": prod_id,
                    "descripcion": producto.nombre,
                    "precio_unitario": producto.precio_venta,
                    "cantidad": cant,
                    "subtotal": round(cant * producto.precio_venta, 2),
                    "stock_disponible": producto.stock,
                }
            )

        self.area_error.limpiar()
        self._refrescar_carrito_visual()
        self.spin_cant_agregar.set(1)

    def _agregar_monto_global(self) -> None:
        """Agrega un ítem sin catalogar al carrito (producto_id=None) (RF-POS-02)."""
        texto_monto = self.entry_monto_directo.get().strip()
        desc = self.entry_desc_directo.get().strip() or "Venta por monto global"

        try:
            monto = float(texto_monto)
            if monto <= 0:
                raise ValueError()
        except ValueError:
            self.area_error.mostrar_error("Ingrese un monto válido y mayor a cero para la venta rápida.")
            return

        self._carrito.append(
            {
                "producto_id": None,
                "descripcion": desc,
                "precio_unitario": monto,
                "cantidad": 1.0,
                "subtotal": monto,
                "stock_disponible": None,
            }
        )

        self.entry_monto_directo.delete(0, tk.END)
        self.entry_desc_directo.delete(0, tk.END)
        self.entry_desc_directo.insert(0, "Venta rápida")
        self.area_error.limpiar()
        self._refrescar_carrito_visual()

    def _modificar_cantidad_seleccion(self, delta: float) -> None:
        """Incrementa o decrementa la cantidad del ítem seleccionado en el carrito."""
        seleccion = self.tree_carrito.selection()
        if not seleccion:
            return

        idx = int(self.tree_carrito.item(seleccion[0], "values")[0]) - 1
        if 0 <= idx < len(self._carrito):
            item = self._carrito[idx]
            nueva_cant = item["cantidad"] + delta
            if nueva_cant <= 0:
                self._carrito.pop(idx)
            else:
                item["cantidad"] = nueva_cant
                item["subtotal"] = round(nueva_cant * item["precio_unitario"], 2)
            self._refrescar_carrito_visual()

    def _quitar_item_seleccionado(self) -> None:
        """Elimina el ítem actualmente seleccionado en el carrito."""
        seleccion = self.tree_carrito.selection()
        if not seleccion:
            return

        idx = int(self.tree_carrito.item(seleccion[0], "values")[0]) - 1
        if 0 <= idx < len(self._carrito):
            self._carrito.pop(idx)
            self._refrescar_carrito_visual()

    def _vaciar_carrito(self) -> None:
        """Limpia todos los ítems del carrito."""
        self._carrito.clear()
        self._refrescar_carrito_visual()

    def _obtener_total_carrito(self) -> float:
        """Calcula la sumatoria de subtotales del carrito."""
        return round(sum(it["subtotal"] for it in self._carrito), 2)

    def _refrescar_carrito_visual(self) -> None:
        """Re-renderiza la Treeview del carrito a partir de self._carrito y actualiza totales."""
        for row in self.tree_carrito.get_children():
            self.tree_carrito.delete(row)

        for i, it in enumerate(self._carrito, start=1):
            self.tree_carrito.insert(
                "",
                tk.END,
                values=(
                    i,
                    it["descripcion"],
                    f"{it['cantidad']:g}",
                    f"${it['precio_unitario']:,.2f}",
                    f"${it['subtotal']:,.2f}",
                ),
            )

        total = self._obtener_total_carrito()
        self.lbl_total_carrito.config(text=f"Total: ${total:,.2f}")

        # Sincronizar si está en modo Nequi
        if self.var_tipo_pago.get() == "nequi":
            self.entry_monto_recibido.config(state="normal")
            self.entry_monto_recibido.delete(0, tk.END)
            self.entry_monto_recibido.insert(0, f"{total:.2f}")
            self.entry_monto_recibido.config(state="readonly")

        self._calcular_cambio_o_saldo()

    # =========================================================================
    # REACTIVIDAD DE PAGO Y CRÉDITO
    # =========================================================================

    def _on_tipo_pago_cambiado(self) -> None:
        """Reacciona a la alternancia entre efectivo, nequi y crédito."""
        tipo = self.var_tipo_pago.get()
        total = self._obtener_total_carrito()

        if tipo == "efectivo":
            self.lbl_monto_recibido.config(text="Monto Recibido ($):")
            self.entry_monto_recibido.config(state="normal")
            self.entry_monto_recibido.delete(0, tk.END)
            self.entry_monto_recibido.insert(0, f"{total:.2f}" if total > 0 else "")
            self.lbl_resultado_pago.config(text="Cambio: $ 0.00", foreground="#2980b9")

        elif tipo == "nequi":
            self.lbl_monto_recibido.config(text="Monto Transferencia ($):")
            self.entry_monto_recibido.config(state="normal")
            self.entry_monto_recibido.delete(0, tk.END)
            self.entry_monto_recibido.insert(0, f"{total:.2f}")
            self.entry_monto_recibido.config(state="readonly")
            self.lbl_resultado_pago.config(text="Cambio: $ 0.00", foreground="#2980b9")

        elif tipo == "credito":
            self.lbl_monto_recibido.config(text="Anticipo / Abono Inicial ($):")
            self.entry_monto_recibido.config(state="normal")
            self.entry_monto_recibido.delete(0, tk.END)
            self.entry_monto_recibido.insert(0, "0.00")
            self.lbl_resultado_pago.config(
                text=f"Saldo a Fiar: ${total:,.2f}", foreground="#d35400"
            )

        self._calcular_cambio_o_saldo()

    def _calcular_cambio_o_saldo(self) -> None:
        """Calcula dinámicamente el cambio o el saldo resultante a financiar."""
        tipo = self.var_tipo_pago.get()
        total = self._obtener_total_carrito()
        texto_monto = self.entry_monto_recibido.get().strip()

        try:
            monto = float(texto_monto) if texto_monto else 0.0
        except ValueError:
            monto = 0.0

        if tipo == "efectivo":
            cambio = round(monto - total, 2)
            if cambio >= 0:
                self.lbl_resultado_pago.config(
                    text=f"Cambio: ${cambio:,.2f}", foreground="#27ae60"
                )
            else:
                faltante = round(abs(cambio), 2)
                self.lbl_resultado_pago.config(
                    text=f"Faltan: ${faltante:,.2f}", foreground="#c0392b"
                )

        elif tipo == "nequi":
            self.lbl_resultado_pago.config(text="Cambio: $ 0.00", foreground="#2980b9")

        elif tipo == "credito":
            saldo_a_fiar = round(total - monto, 2)
            if saldo_a_fiar < 0:
                self.lbl_resultado_pago.config(
                    text="El anticipo supera el total", foreground="#c0392b"
                )
            else:
                color = "#d35400"
                if (
                    self._cliente_actual
                    and saldo_a_fiar > self._cliente_actual.cupo_disponible
                ):
                    color = "#c0392b"
                self.lbl_resultado_pago.config(
                    text=f"Saldo a Fiar: ${saldo_a_fiar:,.2f}", foreground=color
                )

    def _on_cliente_seleccionado(self, event=None) -> None:
        """Carga y actualiza los indicadores de crédito del cliente seleccionado."""
        seleccion = self.combo_clientes.get()
        cliente_id = self._clientes_map.get(seleccion)

        if not cliente_id:
            self._cliente_actual = None
            self.lbl_card_nombre.config(text="Cliente: Mostrador (Sin registrar)")
            self.lbl_card_limite.config(text="Límite: $ 0.00")
            self.lbl_card_saldo.config(text="Saldo: $ 0.00")
            self.lbl_card_cupo.config(text="Cupo Disp: $ 0.00", foreground="#27ae60")
            self.lbl_card_scoring.config(
                text="Sin restricciones de crédito",
                background="#f8f9fa",
                foreground=COLOR_TEXTO_MUTED,
            )
            self._calcular_cambio_o_saldo()
            return

        cliente = cxc_service.obtener_cliente(cliente_id, self.sesion.conn)
        self._cliente_actual = cliente

        if cliente:
            self.lbl_card_nombre.config(text=f"👤 {cliente.nombre}")
            self.lbl_card_limite.config(text=f"Límite: ${cliente.limite_credito:,.2f}")
            self.lbl_card_saldo.config(text=f"Saldo: ${cliente.saldo_actual:,.2f}")

            cupo_color = "#27ae60" if cliente.cupo_disponible > 0 else "#c0392b"
            self.lbl_card_cupo.config(
                text=f"Cupo Disp: ${cliente.cupo_disponible:,.2f}", foreground=cupo_color
            )

            # Estilo del semáforo de scoring
            cat = cliente.categoria_riesgo or "B"
            estilo_cat = COLORES_SCORING.get(cat, COLORES_SCORING["B"])
            score_txt = f"Score: {cliente.score_crediticio} | {estilo_cat['etiqueta']}"
            if cat == "D":
                score_txt += " 🚫 BLOQUEADO"
            elif cat == "C":
                score_txt += " ⚠️ Requiere abono previo >= 50%"

            self.lbl_card_scoring.config(
                text=score_txt,
                background=estilo_cat["bg"],
                foreground=estilo_cat["fg"],
            )

        self._calcular_cambio_o_saldo()

    # =========================================================================
    # CONFIRMACIÓN Y DESPACHO DE LA VENTA
    # =========================================================================

    def _confirmar_venta(self) -> None:
        """Valida e invoca pos_service.registrar_venta atómicamente."""
        self.area_error.limpiar()
        self.frame_exito.pack_forget()

        if not self._carrito:
            self.area_error.mostrar_error("El carrito está vacío. Agregue productos antes de cobrar.")
            return

        tipo_pago = self.var_tipo_pago.get()
        total = self._obtener_total_carrito()
        texto_monto = self.entry_monto_recibido.get().strip()

        # Parsear monto pagado
        try:
            monto_pagado = float(texto_monto) if texto_monto else 0.0
        except ValueError:
            self.area_error.mostrar_error("El monto ingresado no es válido.")
            return

        # Validaciones de interfaz: presencia de cliente si es venta a crédito
        if tipo_pago == "credito" and not self._cliente_actual:
            self.area_error.mostrar_error(
                "Debe seleccionar un cliente registrado para autorizar una venta a crédito."
            )
            return

        # Construir líneas de venta
        items_pos: List[LineaVentaInput] = [
            LineaVentaInput(
                producto_id=it["producto_id"],
                cantidad=it["cantidad"],
                precio_unitario=it["precio_unitario"],
                descripcion=it["descripcion"],
            )
            for it in self._carrito
        ]

        usuario_id = self.sesion.usuario_actual.id if self.sesion.usuario_actual else 1
        cliente_id = self._cliente_actual.id if self._cliente_actual else None

        try:
            venta = pos_service.registrar_venta(
                usuario_id=usuario_id,
                tipo_pago=tipo_pago,
                items=items_pos,
                conn=self.sesion.conn,
                cliente_id=cliente_id,
                monto_pagado=monto_pagado,
            )

            # Éxito: calcular cambio o mensaje
            if tipo_pago == "efectivo":
                cambio = round(monto_pagado - total, 2)
                msg_exito = f"✅ Venta #{venta.id} completada (Efectivo). Total: ${total:,.2f} | Cambio: ${cambio:,.2f}"
            elif tipo_pago == "nequi":
                msg_exito = f"✅ Venta #{venta.id} completada (Nequi). Total: ${total:,.2f}"
            else:
                saldo_financiado = round(total - monto_pagado, 2)
                msg_exito = (
                    f"✅ Venta a crédito #{venta.id} registrada exitosamente para {self._cliente_actual.nombre}. "
                    f"Total: ${total:,.2f} (Anticipo: ${monto_pagado:,.2f}, Saldo financiado: ${saldo_financiado:,.2f})."
                )

            self.lbl_exito.config(text=msg_exito)
            self.frame_exito.pack(fill=tk.X, pady=(0, 10))

            # Limpieza y refresco
            self._vaciar_carrito()
            self._refrescar_catalogo()

            # Refrescar ficha del cliente si aplica
            if self._cliente_actual:
                self._on_cliente_seleccionado()

            # Resetear campo de pago
            if tipo_pago == "efectivo":
                self.entry_monto_recibido.delete(0, tk.END)
                self.lbl_resultado_pago.config(text="Cambio: $ 0.00", foreground="#2980b9")
            elif tipo_pago == "credito":
                self.entry_monto_recibido.delete(0, tk.END)
                self.entry_monto_recibido.insert(0, "0.00")
                self.lbl_resultado_pago.config(text="Saldo a Fiar: $ 0.00", foreground="#d35400")

        except ValueError as e:
            self.area_error.mostrar_error(str(e))
        except Exception as e:
            self.area_error.mostrar_error(f"Error inesperado al procesar la venta: {e}")

    # =========================================================================
    # RECARGA DE DATOS Y CICLO DE VIDA (al_mostrar)
    # =========================================================================

    def _refrescar_catalogo(self, termino: str = "") -> None:
        """Carga o filtra el catálogo de productos activos desde la base de datos."""
        for row in self.tree_catalogo.get_children():
            self.tree_catalogo.delete(row)

        self._productos_cache.clear()

        if termino:
            prods = inventario_service.buscar_productos(termino, self.sesion.conn, solo_activos=True)
        else:
            prods = inventario_service.listar_productos(self.sesion.conn, solo_activos=True)

        for p in prods:
            self._productos_cache[p.id] = p
            self.tree_catalogo.insert(
                "",
                tk.END,
                values=(
                    p.id,
                    p.codigo_barras or "S/C",
                    p.nombre,
                    p.categoria,
                    f"${p.precio_venta:,.2f}",
                    p.stock,
                ),
            )

    def _filtrar_productos(self) -> None:
        """Ejecuta búsqueda de productos al teclear o presionar buscar."""
        termino = self.entry_busqueda_prod.get().strip()
        self._refrescar_catalogo(termino)

    def _limpiar_busqueda_prod(self) -> None:
        """Limpia el filtro de búsqueda y recarga el catálogo completo."""
        self.entry_busqueda_prod.delete(0, tk.END)
        self._refrescar_catalogo()

    def _cargar_clientes(self) -> None:
        """Carga la lista de clientes activos en el Combobox."""
        clientes = cxc_service.listar_clientes(self.sesion.conn, solo_activos=True)
        self._clientes_map.clear()

        opciones = ["--- Venta Mostrador (Sin Ficha / Contado) ---"]
        for c in clientes:
            etiqueta = f"{c.nombre} (ID: {c.id})"
            opciones.append(etiqueta)
            self._clientes_map[etiqueta] = c.id

        self.combo_clientes["values"] = opciones
        self.combo_clientes.current(0)
        self._on_cliente_seleccionado()

    def al_mostrar(self) -> None:
        """Hook invocado al navegar hacia la pantalla POS para sincronizar estado."""
        self.area_error.limpiar()
        self.frame_exito.pack_forget()
        self._refrescar_catalogo()
        self._cargar_clientes()
