import sqlite3
import tkinter as tk
from datetime import date
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

from services import reportes_service
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


class PantallaReportes(tk.Frame):
    """
    Pantalla 5 — Reportes Operativos (RF-REP-01 y RF-REP-02).
    Gestiona el Arqueo / Cierre Diario de Caja física y digital, y el Consolidado
    de Cartera / CxC clasificado por bandas de riesgo, con bloqueo reactivo de pestaña
    en caliente para usuarios sin privilegios administrativos.
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

        # Caché de deudores en memoria para filtrado instantáneo sin peticiones SQL adicionales
        self._deudores_cache: List[Dict[str, Any]] = []

        # Estructura principal con Notebook
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # 1. Pestaña 1: Arqueo / Cierre Diario (RF-REP-01)
        self.tab_arqueo = tk.Frame(self.notebook, background=COLOR_FONDO_APP, padx=10, pady=10)
        self.notebook.add(self.tab_arqueo, text="💰 Arqueo / Cierre Diario")
        self._construir_pestana_arqueo()

        # 2. Pestaña 2: Cartera / CxC [Admin] (RF-REP-02)
        self.tab_cartera = tk.Frame(self.notebook, background=COLOR_FONDO_APP, padx=10, pady=10)
        self.notebook.add(self.tab_cartera, text="📊 Cartera / CxC [Admin]")
        self._construir_pestana_cartera()

        # Evento de cambio de pestaña para cargar cartera bajo demanda
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_cambiada)

        self.al_mostrar()

    # =========================================================================
    # PESTAÑA 1: ARQUEO / CIERRE DIARIO (RF-REP-01)
    # =========================================================================

    def _construir_pestana_arqueo(self) -> None:
        self.tab_arqueo.grid_rowconfigure(2, weight=1)
        self.tab_arqueo.grid_columnconfigure(0, weight=1)

        # A. Barra Superior: Selector de Fecha y Refresco
        frame_controles = tk.Frame(
            self.tab_arqueo,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        frame_controles.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        tk.Label(
            frame_controles,
            text="📅 Fecha de Cierre (YYYY-MM-DD):",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.entry_fecha_arqueo = ttk.Entry(frame_controles, width=12, font=("Segoe UI", 10))
        self.entry_fecha_arqueo.insert(0, date.today().strftime("%Y-%m-%d"))
        self.entry_fecha_arqueo.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_fecha_arqueo.bind("<Return>", lambda e: self._cargar_arqueo_diario())

        btn_hoy = ttk.Button(
            frame_controles,
            text="Hoy",
            width=5,
            command=self._establecer_fecha_hoy,
        )
        btn_hoy.pack(side=tk.LEFT, padx=(0, 8))

        btn_refrescar_a = ttk.Button(
            frame_controles,
            text="🔄 Consultar Arqueo",
            style="Primary.TButton",
            command=self._cargar_arqueo_diario,
        )
        btn_refrescar_a.pack(side=tk.LEFT)

        self.lbl_estado_arqueo = tk.Label(
            frame_controles,
            text="",
            font=FUENTE_PEQUENA,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_MUTED,
        )
        self.lbl_estado_arqueo.pack(side=tk.RIGHT)

        # B. Tarjetas KPI de Resumen de Caja (5 Métricas)
        frame_kpis = tk.Frame(self.tab_arqueo, background=COLOR_FONDO_APP)
        frame_kpis.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for col_idx in range(5):
            frame_kpis.grid_columnconfigure(col_idx, weight=1)

        # KPI 1: Ventas Efectivo
        self.lbl_kpi_v_efectivo = self._crear_kpi_card(
            frame_kpis, 0, "💵 Ventas Efectivo", "$ 0.00", "#2c3e50"
        )
        # KPI 2: Ventas Nequi
        self.lbl_kpi_v_nequi = self._crear_kpi_card(
            frame_kpis, 1, "📱 Nequi / Transf.", "$ 0.00", "#2980b9"
        )
        # KPI 3: Crédito Financiado
        self.lbl_kpi_v_credito = self._crear_kpi_card(
            frame_kpis, 2, "📑 Crédito Otorgado", "$ 0.00", "#d35400"
        )
        # KPI 4: Abonos CxC
        self.lbl_kpi_abonos = self._crear_kpi_card(
            frame_kpis, 3, "📥 Abonos Recibidos", "$ 0.00", "#16a085"
        )
        # KPI 5: TOTAL Efectivo en Caja (Caja Física) — Resaltado
        self.lbl_kpi_total_caja = self._crear_kpi_card(
            frame_kpis,
            4,
            "🏆 TOTAL EFECTIVO EN CAJA",
            "$ 0.00",
            "#155724",
            bg_card="#d4edda",
            border_color="#27ae60",
            font_size=15,
        )

        # C. Detalle Cronológico de Movimientos (Treeview de solo lectura)
        frame_tree_arq = tk.Frame(
            self.tab_arqueo,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        frame_tree_arq.grid(row=2, column=0, sticky="nsew")
        frame_tree_arq.grid_rowconfigure(1, weight=1)
        frame_tree_arq.grid_columnconfigure(0, weight=1)

        lbl_tit_tabla_a = tk.Label(
            frame_tree_arq,
            text="📋 Detalle Cronológico de Transacciones del Día",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_tabla_a.grid(row=0, column=0, sticky="w", pady=(0, 6))

        columnas_arq = ("id", "hora", "tipo", "metodo", "monto", "caja", "descripcion")
        self.tree_arqueo = ttk.Treeview(
            frame_tree_arq,
            columns=columnas_arq,
            show="headings",
            selectmode="browse",
        )
        self.tree_arqueo.heading("id", text="Ref.")
        self.tree_arqueo.heading("hora", text="Hora / Fecha")
        self.tree_arqueo.heading("tipo", text="Tipo Transacción")
        self.tree_arqueo.heading("metodo", text="Método")
        self.tree_arqueo.heading("monto", text="Monto Bruto")
        self.tree_arqueo.heading("caja", text="Ingreso a Caja")
        self.tree_arqueo.heading("descripcion", text="Detalle / Cliente")

        self.tree_arqueo.column("id", width=90, anchor=tk.CENTER)
        self.tree_arqueo.column("hora", width=125, anchor=tk.CENTER)
        self.tree_arqueo.column("tipo", width=170, anchor=tk.W)
        self.tree_arqueo.column("metodo", width=80, anchor=tk.CENTER)
        self.tree_arqueo.column("monto", width=95, anchor=tk.E)
        self.tree_arqueo.column("caja", width=95, anchor=tk.E)
        self.tree_arqueo.column("descripcion", width=260, anchor=tk.W)

        scroll_arq = ttk.Scrollbar(
            frame_tree_arq, orient="vertical", command=self.tree_arqueo.yview
        )
        self.tree_arqueo.configure(yscrollcommand=scroll_arq.set)
        self.tree_arqueo.grid(row=1, column=0, sticky="nsew")
        scroll_arq.grid(row=1, column=1, sticky="ns")

    def _crear_kpi_card(
        self,
        parent: tk.Widget,
        col: int,
        titulo: str,
        valor_inicial: str,
        color_valor: str,
        bg_card: str = COLOR_BLANCO,
        border_color: str = COLOR_BORDE_NEUTRAL,
        font_size: int = 13,
    ) -> tk.Label:
        """Crea una tarjeta KPI métrica estilizada."""
        card = tk.Frame(
            parent,
            background=bg_card,
            highlightbackground=border_color,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=3)

        tk.Label(
            card,
            text=titulo,
            font=FUENTE_PEQUENA,
            background=bg_card,
            foreground=COLOR_TEXTO_SECUNDARIO,
        ).pack(anchor="w")

        lbl_valor = tk.Label(
            card,
            text=valor_inicial,
            font=("Segoe UI", font_size, "bold"),
            background=bg_card,
            foreground=color_valor,
        )
        lbl_valor.pack(anchor="w", pady=(2, 0))
        return lbl_valor

    def _establecer_fecha_hoy(self) -> None:
        """Asigna la fecha actual en el campo de búsqueda."""
        self.entry_fecha_arqueo.delete(0, tk.END)
        self.entry_fecha_arqueo.insert(0, date.today().strftime("%Y-%m-%d"))
        self._cargar_arqueo_diario()

    def _cargar_arqueo_diario(self) -> None:
        """Consulta el arqueo diario consolidado y actualiza tarjetas y Treeview."""
        fecha = self.entry_fecha_arqueo.get().strip() or "now"

        try:
            datos = reportes_service.obtener_arqueo_diario(fecha=fecha, conn=self.sesion.conn)

            # Actualizar KPIs
            self.lbl_kpi_v_efectivo.config(text=f"${datos['ventas_efectivo']:,.2f}")
            self.lbl_kpi_v_nequi.config(text=f"${datos['ventas_nequi']:,.2f}")
            self.lbl_kpi_v_credito.config(text=f"${datos['ventas_credito']:,.2f}")
            self.lbl_kpi_abonos.config(text=f"${datos['abonos_cxc']:,.2f}")
            self.lbl_kpi_total_caja.config(text=f"${datos['total_efectivo_en_caja']:,.2f}")

            # Actualizar Treeview
            for r in self.tree_arqueo.get_children():
                self.tree_arqueo.delete(r)

            for m in datos["movimientos"]:
                self.tree_arqueo.insert(
                    "",
                    tk.END,
                    values=(
                        m.get("id", "--"),
                        m.get("hora", "--"),
                        m.get("tipo", "--"),
                        m.get("metodo", "--").upper(),
                        f"${m.get('monto', 0.0):,.2f}",
                        f"${m.get('efectivo_caja', 0.0):,.2f}",
                        m.get("descripcion", "--"),
                    ),
                )

            self.lbl_estado_arqueo.config(
                text=f"Cierre de {datos['fecha']}: {datos['total_transacciones']} operaciones | "
                f"Ingresos totales día: ${datos['total_ingresos_dia']:,.2f}"
            )

        except Exception as e:
            self.lbl_estado_arqueo.config(text=f"Error al consultar arqueo: {e}")

    # =========================================================================
    # PESTAÑA 2: CONSOLIDADO DE CARTERA / CXC (RF-REP-02, SOLO ADMIN)
    # =========================================================================

    def _construir_pestana_cartera(self) -> None:
        self.tab_cartera.grid_rowconfigure(2, weight=1)
        self.tab_cartera.grid_columnconfigure(0, weight=1)

        # A. Tarjetas de Resumen por Banda de Scoring (Semáforo de Colores)
        frame_bandas = tk.Frame(self.tab_cartera, background=COLOR_FONDO_APP)
        frame_bandas.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for col_idx in range(5):
            frame_bandas.grid_columnconfigure(col_idx, weight=1)

        # Banda 1: Vigente (0-3 días) - Verde (Clase A)
        cfg_a = COLORES_SCORING["A"]
        self.lbl_b_vigente, self.lbl_c_vigente = self._crear_banda_card(
            frame_bandas, 0, "🟢 Vigente (0-3 días)", "$ 0.00", "0 clientes", cfg_a["bg"], cfg_a["borde"], cfg_a["fg"]
        )

        # Banda 2: Preventiva (4-6 días) - Azul (Clase B)
        cfg_b = COLORES_SCORING["B"]
        self.lbl_b_preventiva, self.lbl_c_preventiva = self._crear_banda_card(
            frame_bandas, 1, "🔵 Preventiva (4-6 días)", "$ 0.00", "0 clientes", cfg_b["bg"], cfg_b["borde"], cfg_b["fg"]
        )

        # Banda 3: Congelada (7-10 días) - Ámbar / Naranja (Clase C)
        cfg_c = COLORES_SCORING["C"]
        self.lbl_b_congelada, self.lbl_c_congelada = self._crear_banda_card(
            frame_bandas, 2, "🟡 Congelada (7-10 días)", "$ 0.00", "0 clientes", cfg_c["bg"], cfg_c["borde"], cfg_c["fg"]
        )

        # Banda 4: Crítica (>10 días) - Rojo (Clase D)
        cfg_d = COLORES_SCORING["D"]
        self.lbl_b_critica, self.lbl_c_critica = self._crear_banda_card(
            frame_bandas, 3, "🔴 Crítica (>10 días)", "$ 0.00", "0 clientes", cfg_d["bg"], cfg_d["borde"], cfg_d["fg"]
        )

        # Tarjeta 5: Total Cartera por Cobrar
        self.lbl_b_total, self.lbl_c_total = self._crear_banda_card(
            frame_bandas, 4, "💼 Total Cartera Activa", "$ 0.00", "0 deudores", COLOR_BLANCO, COLOR_BORDE_NEUTRAL, COLOR_PRIMARIO
        )

        # B. Barra de Filtros en Memoria (RF-REP-02)
        frame_filtros_cartera = tk.Frame(
            self.tab_cartera,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        frame_filtros_cartera.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        tk.Label(
            frame_filtros_cartera,
            text="🔍 Filtrar por Clase:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.combo_filtro_clase = ttk.Combobox(
            frame_filtros_cartera,
            values=["Todas", "Clase A", "Clase B", "Clase C", "Clase D"],
            state="readonly",
            width=12,
        )
        self.combo_filtro_clase.set("Todas")
        self.combo_filtro_clase.pack(side=tk.LEFT, padx=(0, 15))
        self.combo_filtro_clase.bind("<<ComboboxSelected>>", lambda e: self._aplicar_filtros_cartera_en_memoria())

        tk.Label(
            frame_filtros_cartera,
            text="Rango de Mora:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.combo_filtro_mora = ttk.Combobox(
            frame_filtros_cartera,
            values=["Todos", "0 a 3 días", "4 a 6 días", "7 a 10 días", "> 10 días"],
            state="readonly",
            width=15,
        )
        self.combo_filtro_mora.set("Todos")
        self.combo_filtro_mora.pack(side=tk.LEFT, padx=(0, 15))
        self.combo_filtro_mora.bind("<<ComboboxSelected>>", lambda e: self._aplicar_filtros_cartera_en_memoria())

        btn_refrescar_c = ttk.Button(
            frame_filtros_cartera,
            text="🔄 Refrescar Cartera",
            command=self._cargar_consolidado_cartera,
        )
        btn_refrescar_c.pack(side=tk.LEFT)

        self.lbl_conteo_filtro = tk.Label(
            frame_filtros_cartera,
            text="",
            font=FUENTE_PEQUENA,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_MUTED,
        )
        self.lbl_conteo_filtro.pack(side=tk.RIGHT)

        # C. Tabla de Deudores (Treeview solo lectura)
        frame_tree_cart = tk.Frame(
            self.tab_cartera,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        frame_tree_cart.grid(row=2, column=0, sticky="nsew")
        frame_tree_cart.grid_rowconfigure(0, weight=1)
        frame_tree_cart.grid_columnconfigure(0, weight=1)

        columnas_cart = ("cliente", "saldo", "dias_mora", "clase", "estado_banda", "cupo_disp")
        self.tree_cartera = ttk.Treeview(
            frame_tree_cart,
            columns=columnas_cart,
            show="headings",
            selectmode="browse",
        )
        self.tree_cartera.heading("cliente", text="Cliente / Razón Social")
        self.tree_cartera.heading("saldo", text="Saldo Pendiente")
        self.tree_cartera.heading("dias_mora", text="Días Mora Efectiva")
        self.tree_cartera.heading("clase", text="Clase")
        self.tree_cartera.heading("estado_banda", text="Estado de Banda")
        self.tree_cartera.heading("cupo_disp", text="Cupo Disponible")

        self.tree_cartera.column("cliente", width=220, anchor=tk.W)
        self.tree_cartera.column("saldo", width=110, anchor=tk.E)
        self.tree_cartera.column("dias_mora", width=120, anchor=tk.CENTER)
        self.tree_cartera.column("clase", width=65, anchor=tk.CENTER)
        self.tree_cartera.column("estado_banda", width=210, anchor=tk.W)
        self.tree_cartera.column("cupo_disp", width=110, anchor=tk.E)

        # Configuración de tags de color para las filas
        self.tree_cartera.tag_configure("clase_A", background=cfg_a["bg"])
        self.tree_cartera.tag_configure("clase_B", background=cfg_b["bg"])
        self.tree_cartera.tag_configure("clase_C", background=cfg_c["bg"])
        self.tree_cartera.tag_configure("clase_D", background=cfg_d["bg"])

        scroll_cart = ttk.Scrollbar(
            frame_tree_cart, orient="vertical", command=self.tree_cartera.yview
        )
        self.tree_cartera.configure(yscrollcommand=scroll_cart.set)
        self.tree_cartera.grid(row=0, column=0, sticky="nsew")
        scroll_cart.grid(row=0, column=1, sticky="ns")

    def _crear_banda_card(
        self,
        parent: tk.Widget,
        col: int,
        titulo: str,
        monto_inicial: str,
        conteo_inicial: str,
        bg_color: str,
        border_color: str,
        fg_color: str,
    ) -> Tuple[tk.Label, tk.Label]:
        """Crea una tarjeta métrica de banda de riesgo."""
        card = tk.Frame(
            parent,
            background=bg_color,
            highlightbackground=border_color,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=3)

        tk.Label(
            card,
            text=titulo,
            font=FUENTE_BASE_BOLD,
            background=bg_color,
            foreground=fg_color,
        ).pack(anchor="w")

        lbl_monto = tk.Label(
            card,
            text=monto_inicial,
            font=("Segoe UI", 12, "bold"),
            background=bg_color,
            foreground=fg_color,
        )
        lbl_monto.pack(anchor="w", pady=(2, 0))

        lbl_conteo = tk.Label(
            card,
            text=conteo_inicial,
            font=FUENTE_PEQUENA,
            background=bg_color,
            foreground=fg_color,
        )
        lbl_conteo.pack(anchor="w")

        return lbl_monto, lbl_conteo

    def _cargar_consolidado_cartera(self) -> None:
        """Ejecuta una única consulta backend y cachea los deudores para filtrado en memoria."""
        try:
            datos = reportes_service.obtener_consolidado_cartera(self.sesion.conn)

            # Actualizar tarjetas resumen
            res = datos["resumen_por_banda"]
            cnt = datos["conteo_por_banda"]

            self.lbl_b_vigente.config(text=f"${res.get('vigente_0_3', 0.0):,.2f}")
            self.lbl_c_vigente.config(text=f"{cnt.get('vigente_0_3', 0)} cliente(s)")

            self.lbl_b_preventiva.config(text=f"${res.get('preventiva_4_6', 0.0):,.2f}")
            self.lbl_c_preventiva.config(text=f"{cnt.get('preventiva_4_6', 0)} cliente(s)")

            self.lbl_b_congelada.config(text=f"${res.get('congelada_7_10', 0.0):,.2f}")
            self.lbl_c_congelada.config(text=f"{cnt.get('congelada_7_10', 0)} cliente(s)")

            self.lbl_b_critica.config(text=f"${res.get('critica_mas_10', 0.0):,.2f}")
            self.lbl_c_critica.config(text=f"{cnt.get('critica_mas_10', 0)} cliente(s)")

            self.lbl_b_total.config(text=f"${datos['total_cartera_por_cobrar']:,.2f}")
            self.lbl_c_total.config(text=f"{datos['total_deudores']} deudor(es)")

            # Cachear deudores y aplicar filtros
            self._deudores_cache = datos["deudores"]
            self._aplicar_filtros_cartera_en_memoria()

        except Exception as e:
            self.lbl_conteo_filtro.config(text=f"Error al cargar cartera: {e}")

    def _aplicar_filtros_cartera_en_memoria(self) -> None:
        """Filtra la lista de deudores directamente en memoria sin peticiones SQL adicionales."""
        for r in self.tree_cartera.get_children():
            self.tree_cartera.delete(r)

        filtro_clase = self.combo_filtro_clase.get()
        filtro_mora = self.combo_filtro_mora.get()

        deudores_filtrados = []

        for d in self._deudores_cache:
            # 1. Filtro por clase
            if filtro_clase != "Todas":
                clase_esperada = filtro_clase.replace("Clase ", "").strip()
                if d.get("clase_riesgo") != clase_esperada:
                    continue

            # 2. Filtro por rango de mora
            dias_mora = d.get("dias_mora_efectiva", 0)
            if filtro_mora == "0 a 3 días" and not (0 <= dias_mora <= 3):
                continue
            elif filtro_mora == "4 a 6 días" and not (4 <= dias_mora <= 6):
                continue
            elif filtro_mora == "7 a 10 días" and not (7 <= dias_mora <= 10):
                continue
            elif filtro_mora == "> 10 días" and not (dias_mora > 10):
                continue

            deudores_filtrados.append(d)

        # Renderizar filas filtradas
        for d in deudores_filtrados:
            cat = d.get("clase_riesgo", "B")
            tag_name = f"clase_{cat}"
            self.tree_cartera.insert(
                "",
                tk.END,
                values=(
                    d.get("nombre", "--"),
                    f"${d.get('saldo_actual', 0.0):,.2f}",
                    f"{d.get('dias_mora_efectiva', 0)} días",
                    cat,
                    d.get("estado_banda", "--"),
                    f"${d.get('cupo_disponible', 0.0):,.2f}",
                ),
                tags=(tag_name,),
            )

        total_saldo_filtrado = sum(d.get("saldo_actual", 0.0) for d in deudores_filtrados)
        self.lbl_conteo_filtro.config(
            text=f"Mostrando {len(deudores_filtrados)} de {len(self._deudores_cache)} deudores "
            f"(Total subfiltro: ${total_saldo_filtrado:,.2f})"
        )

    # =========================================================================
    # CICLO DE VIDA Y CONTROL REACTIVO DE PERMISOS (al_mostrar)
    # =========================================================================

    def _on_tab_cambiada(self, event=None) -> None:
        """Carga los datos de cartera cuando el Administrador ingresa a la pestaña 2."""
        seleccion = self.notebook.select()
        if seleccion == str(self.tab_cartera):
            self._cargar_consolidado_cartera()

    def al_mostrar(self) -> None:
        """
        Hook invocado por App.navegar_a al levantar esta pantalla.
        Evalúa reactivamente los permisos del usuario activo y bloquea la Pestaña 2
        para roles no administradores.
        """
        es_admin = self.sesion.es_admin

        if not es_admin:
            # Vendedor: deshabilitar pestaña 2 y forzar selección a pestaña 1
            self.notebook.tab(self.tab_cartera, state="disabled")
            if self.notebook.select() == str(self.tab_cartera):
                self.notebook.select(self.tab_arqueo)
        else:
            # Admin: habilitar pestaña 2
            self.notebook.tab(self.tab_cartera, state="normal")

        # Refrescar automáticamente el arqueo diario
        self._cargar_arqueo_diario()
