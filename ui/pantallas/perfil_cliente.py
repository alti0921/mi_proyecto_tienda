import os
import sqlite3
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, List, Optional

from models.cliente import Cliente
from services import cxc_service, pos_service, reportes_service, scoring_service
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
    FUENTE_MONO_BASE,
    FUENTE_PEQUENA,
    FUENTE_SUBTITULO,
    FUENTE_TITULO,
    PAD_CAMPOS,
    PAD_INTERNO,
)
from ui.sesion import SesionActual
from ui.widgets_comunes import AreaError, BotonRestringidoPorRol


class PantallaPerfilCliente(tk.Frame):
    """
    Pantalla 3 — Perfil de Cliente / CxC (RF-CXC-01 a RF-CXC-06, RF-SCR-01 a RF-SCR-06).
    Gestiona la ficha del cliente, actualización demográfica independiente, asignación de cupo
    restringida al rol admin, recálculo en vivo de scoring, registro de abonos con cascada reactiva,
    historial append-only y generación de comprobantes digitales.
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

        self._cliente_actual: Optional[Cliente] = None
        self._clientes_map: Dict[str, int] = {}
        self._ultimo_abono: Optional[Dict[str, Any]] = None

        # Grid principal: Barra superior de búsqueda y dos columnas de trabajo
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._crear_barra_superior_busqueda()
        self._crear_columna_izquierda()
        self._crear_columna_derecha()

        self.al_mostrar()

    # =========================================================================
    # BARRA SUPERIOR DE BÚSQUEDA Y SELECCIÓN DE CLIENTE (RF-CXC-01)
    # =========================================================================

    def _crear_barra_superior_busqueda(self) -> None:
        frame_top = tk.Frame(
            self,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        frame_top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))

        lbl_buscar = tk.Label(
            frame_top,
            text="👤 Seleccionar Cliente:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_buscar.pack(side=tk.LEFT, padx=(0, 8))

        self.combo_clientes = ttk.Combobox(frame_top, state="readonly", width=36)
        self.combo_clientes.pack(side=tk.LEFT, padx=(0, 10))
        self.combo_clientes.bind("<<ComboboxSelected>>", self._on_cliente_seleccionado)

        self.entry_buscar_termino = ttk.Entry(frame_top, width=22)
        self.entry_buscar_termino.pack(side=tk.LEFT, padx=(0, 6))
        self.entry_buscar_termino.bind("<KeyRelease>", lambda e: self._filtrar_clientes())
        self.entry_buscar_termino.bind("<Return>", lambda e: self._filtrar_clientes())

        btn_buscar = ttk.Button(
            frame_top, text="🔍 Buscar", command=self._filtrar_clientes
        )
        btn_buscar.pack(side=tk.LEFT, padx=(0, 4))

        btn_limpiar = ttk.Button(
            frame_top, text="Limpiar", command=self._limpiar_busqueda_clientes
        )
        btn_limpiar.pack(side=tk.LEFT, padx=(0, 12))

        btn_nuevo_cliente = ttk.Button(
            frame_top,
            text="➕ Nuevo Cliente",
            command=self._abrir_modal_nuevo_cliente,
        )
        btn_nuevo_cliente.pack(side=tk.RIGHT)

    # =========================================================================
    # COLUMNA IZQUIERDA: DATOS DEMOGRÁFICOS, SCORING Y GESTIÓN DE CUPO
    # =========================================================================

    def _crear_columna_izquierda(self) -> None:
        col_izq = tk.Frame(self, background=COLOR_FONDO_APP)
        col_izq.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        col_izq.grid_rowconfigure(0, weight=0)  # Datos demográficos
        col_izq.grid_rowconfigure(1, weight=0)  # Scoring en vivo
        col_izq.grid_rowconfigure(2, weight=1)  # Asignación de cupo
        col_izq.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # Card 1: Formulario de Datos Demográficos y Vínculo (RF-CXC-01, 03)
        # ---------------------------------------------------------------------
        card_datos = tk.Frame(
            col_izq,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_datos.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        lbl_tit_datos = tk.Label(
            card_datos,
            text="📋 Ficha y Datos Demográficos",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_datos.pack(anchor="w", pady=(0, 6))

        # Campos
        frame_grid_datos = tk.Frame(card_datos, background=COLOR_BLANCO)
        frame_grid_datos.pack(fill=tk.X)
        frame_grid_datos.columnconfigure(1, weight=1)

        # Nombre
        tk.Label(
            frame_grid_datos,
            text="Nombre completo:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=0, column=0, sticky="w", pady=2)
        self.entry_nombre = ttk.Entry(frame_grid_datos)
        self.entry_nombre.grid(row=0, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Teléfono
        tk.Label(
            frame_grid_datos,
            text="Teléfono / Celular:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=1, column=0, sticky="w", pady=2)
        self.entry_telefono = ttk.Entry(frame_grid_datos)
        self.entry_telefono.grid(row=1, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Dirección
        tk.Label(
            frame_grid_datos,
            text="Dirección / Barrio:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=2, column=0, sticky="w", pady=2)
        self.entry_direccion = ttk.Entry(frame_grid_datos)
        self.entry_direccion.grid(row=2, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Nivel de Vínculo (RF-CXC-03)
        tk.Label(
            frame_grid_datos,
            text="Nivel de Vínculo:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=3, column=0, sticky="w", pady=2)
        self.combo_vinculo = ttk.Combobox(
            frame_grid_datos,
            values=["solo_apodo", "conocido_referido", "registro_completo"],
            state="readonly",
        )
        self.combo_vinculo.grid(row=3, column=1, sticky="ew", pady=2, padx=(6, 0))

        # Estado Activo
        self.var_activo = tk.BooleanVar(value=True)
        self.chk_activo = ttk.Checkbutton(
            frame_grid_datos,
            text="Cliente Activo en el Sistema",
            variable=self.var_activo,
        )
        self.chk_activo.grid(row=4, column=1, sticky="w", pady=4, padx=(6, 0))

        # Mensajes de datos
        self.area_error_datos = AreaError(card_datos)
        self.lbl_exito_datos = tk.Label(
            card_datos,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
        )
        self.lbl_exito_datos.pack(anchor="w", pady=(2, 0))

        # Botón Guardar Datos Demográficos (Completamente independiente)
        self.btn_guardar_datos = ttk.Button(
            card_datos,
            text="💾 Guardar Cambios de Ficha",
            command=self._guardar_datos_cliente,
        )
        self.btn_guardar_datos.pack(anchor="e", pady=(6, 0))

        # ---------------------------------------------------------------------
        # Card 2: Evaluación de Scoring en Vivo (RF-SCR-01 a 06)
        # ---------------------------------------------------------------------
        self.card_scoring = tk.Frame(
            col_izq,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        self.card_scoring.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        lbl_tit_scoring = tk.Label(
            self.card_scoring,
            text="📈 Evaluación de Scoring y Decisión en Vivo",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_scoring.pack(anchor="w", pady=(0, 4))

        frame_score_header = tk.Frame(self.card_scoring, background=COLOR_BLANCO)
        frame_score_header.pack(fill=tk.X, pady=(2, 4))

        self.lbl_score_valor = tk.Label(
            frame_score_header,
            text="Score: -- / 100",
            font=FUENTE_KPI_NUMERO,
            background=COLOR_BLANCO,
            foreground=COLOR_PRIMARIO,
        )
        self.lbl_score_valor.pack(side=tk.LEFT)

        self.lbl_badge_clase = tk.Label(
            frame_score_header,
            text="Clase: --",
            font=FUENTE_BASE_BOLD,
            background="#e9ecef",
            foreground="#495057",
            padx=10,
            pady=4,
        )
        self.lbl_badge_clase.pack(side=tk.RIGHT)

        self.lbl_decision_accion = tk.Label(
            self.card_scoring,
            text="Seleccione un cliente para ver la evaluación.",
            font=FUENTE_BASE,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_SECUNDARIO,
            wraplength=480,
            justify=tk.LEFT,
        )
        self.lbl_decision_accion.pack(anchor="w", pady=(2, 4))

        # Desglose de Factores (SW1, SW2, SW3)
        self.lbl_factores = tk.Label(
            self.card_scoring,
            text="",
            font=FUENTE_PEQUENA,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_MUTED,
            justify=tk.LEFT,
        )
        self.lbl_factores.pack(anchor="w")

        # ---------------------------------------------------------------------
        # Card 3: Asignación de Cupo (RF-CXC-05, RF-SCR-02) (Solo Admin)
        # ---------------------------------------------------------------------
        card_cupo = tk.Frame(
            col_izq,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_cupo.grid(row=2, column=0, sticky="nsew")

        lbl_tit_cupo = tk.Label(
            card_cupo,
            text="🔒 Gestión de Límite de Crédito (Cupo)",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_cupo.pack(anchor="w", pady=(0, 4))

        # Métricas de crédito
        frame_metricas = tk.Frame(card_cupo, background=COLOR_BLANCO)
        frame_metricas.pack(fill=tk.X, pady=(2, 6))

        self.lbl_limite_actual = tk.Label(
            frame_metricas,
            text="Límite: $ 0.00",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        self.lbl_limite_actual.pack(side=tk.LEFT, expand=True, anchor="w")

        self.lbl_saldo_actual = tk.Label(
            frame_metricas,
            text="Saldo: $ 0.00",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground="#c0392b",
        )
        self.lbl_saldo_actual.pack(side=tk.LEFT, expand=True, anchor="center")

        self.lbl_cupo_disp = tk.Label(
            frame_metricas,
            text="Disponible: $ 0.00",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
            foreground="#27ae60",
        )
        self.lbl_cupo_disp.pack(side=tk.RIGHT, expand=True, anchor="e")

        # Sugerencia informativa Cold-Start o de la matriz
        self.lbl_sugerencia_cupo = tk.Label(
            card_cupo,
            text="",
            font=FUENTE_BASE_BOLD,
            background="#eef6fb",
            foreground="#2980b9",
            padx=8,
            pady=4,
            wraplength=480,
            justify=tk.LEFT,
        )
        self.lbl_sugerencia_cupo.pack(fill=tk.X, pady=(2, 6))

        # Campo y botón para confirmar cupo (Separado y Restringido a Admin)
        frame_input_cupo = tk.Frame(card_cupo, background=COLOR_BLANCO)
        frame_input_cupo.pack(fill=tk.X, pady=(4, 6))

        tk.Label(
            frame_input_cupo,
            text="Nuevo Límite ($):",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.entry_nuevo_cupo = ttk.Entry(frame_input_cupo, width=14, font=("Segoe UI", 10))
        self.entry_nuevo_cupo.pack(side=tk.LEFT, padx=(0, 8))

        # Reutilización obligatoria de BotonRestringidoPorRol
        self.btn_asignar_cupo = BotonRestringidoPorRol(
            frame_input_cupo,
            sesion=self.sesion,
            roles_permitidos=["admin"],
            text="🔒 Confirmar Cupo (Admin)",
            style="Primary.TButton",
            command=self._asignar_cupo,
        )
        self.btn_asignar_cupo.pack(side=tk.LEFT)

        # Mensajes de asignación de cupo
        self.area_error_cupo = AreaError(card_cupo)
        self.lbl_exito_cupo = tk.Label(
            card_cupo,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
        )
        self.lbl_exito_cupo.pack(anchor="w", pady=(2, 0))

    # =========================================================================
    # COLUMNA DERECHA: REGISTRO DE ABONO E HISTORIAL APPEND-ONLY (RF-CXC-04, 06)
    # =========================================================================

    def _crear_columna_derecha(self) -> None:
        col_der = tk.Frame(self, background=COLOR_FONDO_APP)
        col_der.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        col_der.grid_rowconfigure(0, weight=0)  # Registro de abono
        col_der.grid_rowconfigure(1, weight=1)  # Historial de movimientos
        col_der.grid_columnconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # Card 4: Registro de Abonos a Cuenta (RF-CXC-04)
        # ---------------------------------------------------------------------
        card_abono = tk.Frame(
            col_der,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_abono.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        lbl_tit_abono = tk.Label(
            card_abono,
            text="💵 Registro de Abono a Cartera",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_abono.pack(anchor="w", pady=(0, 6))

        frame_grid_abono = tk.Frame(card_abono, background=COLOR_BLANCO)
        frame_grid_abono.pack(fill=tk.X)
        frame_grid_abono.columnconfigure(1, weight=1)

        tk.Label(
            frame_grid_abono,
            text="Monto Abono ($):",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=0, column=0, sticky="w", pady=3)
        self.entry_monto_abono = ttk.Entry(
            frame_grid_abono, font=("Segoe UI", 11, "bold"), width=16
        )
        self.entry_monto_abono.grid(row=0, column=1, sticky="w", pady=3, padx=(6, 0))

        tk.Label(
            frame_grid_abono,
            text="Descripción / Ref:",
            font=FUENTE_BASE_BOLD,
            background=COLOR_BLANCO,
        ).grid(row=1, column=0, sticky="w", pady=3)
        self.entry_desc_abono = ttk.Entry(frame_grid_abono)
        self.entry_desc_abono.insert(0, "Abono en efectivo")
        self.entry_desc_abono.grid(row=1, column=1, sticky="ew", pady=3, padx=(6, 0))

        # Mensajes de abono
        self.area_error_abono = AreaError(card_abono)
        self.lbl_exito_abono = tk.Label(
            card_abono,
            text="",
            background=COLOR_BLANCO,
            foreground=COLOR_EXITO,
            font=FUENTE_BASE_BOLD,
            wraplength=480,
            justify=tk.LEFT,
        )
        self.lbl_exito_abono.pack(anchor="w", pady=(2, 4))

        # Botones de Abono y Comprobante
        frame_btns_abono = tk.Frame(card_abono, background=COLOR_BLANCO)
        frame_btns_abono.pack(fill=tk.X, pady=(4, 0))

        self.btn_registrar_abono = ttk.Button(
            frame_btns_abono,
            text="💵 Registrar Abono",
            style="Success.TButton",
            command=self._registrar_abono,
        )
        self.btn_registrar_abono.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_comprobante = ttk.Button(
            frame_btns_abono,
            text="🧾 Ver Comprobante Digital",
            command=self._ver_comprobante,
        )
        self.btn_comprobante.pack(side=tk.LEFT)

        # ---------------------------------------------------------------------
        # Card 5: Historial de Movimientos CxC (Append-Only) (RF-CXC-06)
        # ---------------------------------------------------------------------
        card_historial = tk.Frame(
            col_der,
            background=COLOR_BLANCO,
            highlightbackground=COLOR_BORDE_NEUTRAL,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        card_historial.grid(row=1, column=0, sticky="nsew")
        card_historial.grid_rowconfigure(1, weight=1)
        card_historial.grid_columnconfigure(0, weight=1)

        lbl_tit_historial = tk.Label(
            card_historial,
            text="📜 Historial de Movimientos CxC (Inmutable / Append-Only)",
            font=FUENTE_SUBTITULO,
            background=COLOR_BLANCO,
            foreground=COLOR_TEXTO_PRINCIPAL,
        )
        lbl_tit_historial.grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Treeview de Historial estrictamente de solo lectura (Sin eventos de mutación)
        frame_tree_h = tk.Frame(card_historial, background=COLOR_BLANCO)
        frame_tree_h.grid(row=1, column=0, sticky="nsew")
        frame_tree_h.grid_rowconfigure(0, weight=1)
        frame_tree_h.grid_columnconfigure(0, weight=1)

        columnas_h = ("id", "fecha", "tipo", "monto", "saldo", "descripcion")
        self.tree_historial = ttk.Treeview(
            frame_tree_h,
            columns=columnas_h,
            show="headings",
            selectmode="browse",
        )
        self.tree_historial.heading("id", text="#")
        self.tree_historial.heading("fecha", text="Fecha / Hora")
        self.tree_historial.heading("tipo", text="Tipo")
        self.tree_historial.heading("monto", text="Monto")
        self.tree_historial.heading("saldo", text="Saldo Resultante")
        self.tree_historial.heading("descripcion", text="Descripción / Referencia")

        self.tree_historial.column("id", width=35, anchor=tk.CENTER)
        self.tree_historial.column("fecha", width=125, anchor=tk.CENTER)
        self.tree_historial.column("tipo", width=70, anchor=tk.CENTER)
        self.tree_historial.column("monto", width=85, anchor=tk.E)
        self.tree_historial.column("saldo", width=105, anchor=tk.E)
        self.tree_historial.column("descripcion", width=150, anchor=tk.W)

        scroll_h = ttk.Scrollbar(
            frame_tree_h, orient="vertical", command=self.tree_historial.yview
        )
        self.tree_historial.configure(yscrollcommand=scroll_h.set)
        self.tree_historial.grid(row=0, column=0, sticky="nsew")
        scroll_h.grid(row=0, column=1, sticky="ns")

    # =========================================================================
    # LÓGICA DE CARGA Y ACTUALIZACIÓN EN VIVO (SCORING Y ESTADO)
    # =========================================================================

    def _limpiar_mensajes(self) -> None:
        """Limpia áreas de error y mensajes de éxito de todos los módulos."""
        self.area_error_datos.limpiar()
        self.area_error_cupo.limpiar()
        self.area_error_abono.limpiar()
        self.lbl_exito_datos.config(text="")
        self.lbl_exito_cupo.config(text="")
        self.lbl_exito_abono.config(text="")

    def _cargar_ficha_cliente(self, cliente_id: int) -> None:
        """Carga y sincroniza la información completa del cliente en todos los paneles."""
        self._limpiar_mensajes()
        cliente = cxc_service.obtener_cliente(cliente_id, self.sesion.conn)
        if not cliente:
            return

        self._cliente_actual = cliente

        # 1. Poblar Formulario Demográfico
        self.entry_nombre.delete(0, tk.END)
        self.entry_nombre.insert(0, cliente.nombre)

        self.entry_telefono.delete(0, tk.END)
        self.entry_telefono.insert(0, cliente.telefono or "")

        self.entry_direccion.delete(0, tk.END)
        self.entry_direccion.insert(0, cliente.direccion or "")

        self.combo_vinculo.set(cliente.nivel_vinculo or "solo_apodo")
        self.var_activo.set(bool(cliente.activo))

        # 2. Refrescar Bloque de Cupo y Saldos
        self.lbl_limite_actual.config(text=f"Límite: ${cliente.limite_credito:,.2f}")
        self.lbl_saldo_actual.config(text=f"Saldo: ${cliente.saldo_actual:,.2f}")
        cupo_color = "#27ae60" if cliente.cupo_disponible > 0 else "#c0392b"
        self.lbl_cupo_disp.config(
            text=f"Disponible: ${cliente.cupo_disponible:,.2f}", foreground=cupo_color
        )

        # 3. Recálculo Fresco de Score y Matriz de Decisión (No se cachea)
        self._actualizar_scoring_visual(cliente_id)

        # 4. Cargar Historial CxC Append-Only
        self._cargar_historial_cxc(cliente_id)

        # 5. Sugerencia Cold-Start en campo de cupo
        cold_start = scoring_service.evaluar_cold_start(cliente_id, self.sesion.conn)
        if cold_start.get("es_cold_start"):
            cupo_sug = cold_start.get("cupo_semilla", 40000.0)
            self.lbl_sugerencia_cupo.config(
                text=f"💡 Sugerencia Cold-Start (Protocolo Semilla): ${cupo_sug:,.2f} COP "
                f"({cold_start['decision']['accion']})"
            )
            self.entry_nuevo_cupo.delete(0, tk.END)
            self.entry_nuevo_cupo.insert(0, f"{cupo_sug:.2f}")
        else:
            self.lbl_sugerencia_cupo.config(
                text=f"💡 Cliente con historial activo ({cold_start.get('ciclos_completados', 3)}+ ciclos de abono)."
            )
            self.entry_nuevo_cupo.delete(0, tk.END)
            self.entry_nuevo_cupo.insert(0, f"{cliente.limite_credito:.2f}")

    def _actualizar_scoring_visual(self, cliente_id: int) -> None:
        """Calcula de forma fresca e instantánea el score y actualiza los badges."""
        cold_start = scoring_service.evaluar_cold_start(cliente_id, self.sesion.conn)
        if cold_start.get("es_cold_start"):
            score = float(cold_start["score_semilla"])
            decision = cold_start["decision"]
            cat = decision["categoria_riesgo"]
            factores_txt = (
                f"🌱 Protocolo Cold-Start activo | Vínculo: {self.combo_vinculo.get()} | "
                f"Ciclos completados: {cold_start.get('ciclos_completados', 0)}/3"
            )
        else:
            score, cat = scoring_service.calcular_score(cliente_id, self.sesion.conn)
            decision = scoring_service.aplicar_matriz_decision(score)
            sw1 = scoring_service.calcular_sw1(cliente_id, self.sesion.conn)
            sw2 = scoring_service.calcular_sw2(cliente_id, self.sesion.conn)
            sw3 = scoring_service.calcular_sw3(cliente_id, self.sesion.conn)
            factores_txt = f"📊 Desglose de Factores: SW1 (Mora 40%): {sw1:.1f} pts | SW2 (Rotación 35%): {sw2:.1f} pts | SW3 (Arraigo 25%): {sw3:.1f} pts"

        self.lbl_score_valor.config(text=f"Score: {int(round(score))} / 100")

        estilo_cat = COLORES_SCORING.get(cat, COLORES_SCORING["B"])
        self.lbl_badge_clase.config(
            text=estilo_cat["etiqueta"],
            background=estilo_cat["bg"],
            foreground=estilo_cat["fg"],
        )
        self.lbl_decision_accion.config(text=decision["accion"])
        self.lbl_factores.config(text=factores_txt)

    def _cargar_historial_cxc(self, cliente_id: int) -> None:
        """Carga las transacciones append-only en la Treeview del historial."""
        for row in self.tree_historial.get_children():
            self.tree_historial.delete(row)

        movs = cxc_service.obtener_historial_cxc(cliente_id, self.sesion.conn)
        for m in movs:
            tipo_fmt = "📥 Abono" if m.tipo_movimiento == "abono" else "📤 Cargo"
            self.tree_historial.insert(
                "",
                tk.END,
                values=(
                    m.id,
                    m.fecha_movimiento or "--",
                    tipo_fmt,
                    f"${m.monto:,.2f}",
                    f"${m.saldo_resultante:,.2f}",
                    m.descripcion or (f"Venta #{m.venta_id}" if m.venta_id else "S/D"),
                ),
            )

    # =========================================================================
    # ACCIÓN 1: GUARDAR DATOS DEMOGRÁFICOS (RF-CXC-01, RF-CXC-03)
    # =========================================================================

    def _guardar_datos_cliente(self) -> None:
        """Actualiza los datos demográficos y de vínculo sin alterar límites ni abonos."""
        self.area_error_datos.limpiar()
        self.lbl_exito_datos.config(text="")

        if not self._cliente_actual:
            self.area_error_datos.mostrar_error("No hay un cliente seleccionado para actualizar.")
            return

        nombre = self.entry_nombre.get().strip()
        telefono = self.entry_telefono.get().strip() or None
        direccion = self.entry_direccion.get().strip() or None
        vinculo = self.combo_vinculo.get()
        activo = 1 if self.var_activo.get() else 0

        try:
            cli_actualizado = cxc_service.actualizar_cliente(
                cliente_id=self._cliente_actual.id,
                conn=self.sesion.conn,
                nombre=nombre,
                telefono=telefono,
                direccion=direccion,
                nivel_vinculo=vinculo,
                activo=activo,
            )
            self._cliente_actual = cli_actualizado
            self._actualizar_scoring_visual(cli_actualizado.id)
            self._cargar_selector_clientes(mantener_id=cli_actualizado.id)
            self.lbl_exito_datos.config(
                text=f"✅ Datos de '{cli_actualizado.nombre}' guardados exitosamente."
            )

        except ValueError as e:
            self.area_error_datos.mostrar_error(str(e))
        except Exception as e:
            self.area_error_datos.mostrar_error(f"Error inesperado al actualizar: {e}")

    # =========================================================================
    # ACCIÓN 2: ASIGNACIÓN DE CUPO (RF-CXC-05, RF-SCR-02) (SOLO ADMIN)
    # =========================================================================

    def _asignar_cupo(self) -> None:
        """Confirma el límite de crédito asignado por el Administrador."""
        self.area_error_cupo.limpiar()
        self.lbl_exito_cupo.config(text="")

        if not self._cliente_actual:
            self.area_error_cupo.mostrar_error("Seleccione un cliente para asignarle cupo.")
            return

        texto_cupo = self.entry_nuevo_cupo.get().strip()
        try:
            nuevo_limite = float(texto_cupo)
        except ValueError:
            self.area_error_cupo.mostrar_error("El cupo a asignar debe ser un valor numérico válido.")
            return

        try:
            cli = pos_service.asignar_limite_credito(
                cliente_id=self._cliente_actual.id,
                nuevo_limite=nuevo_limite,
                conn=self.sesion.conn,
            )
            self._cliente_actual = cli
            self.lbl_limite_actual.config(text=f"Límite: ${cli.limite_credito:,.2f}")
            cupo_color = "#27ae60" if cli.cupo_disponible > 0 else "#c0392b"
            self.lbl_cupo_disp.config(
                text=f"Disponible: ${cli.cupo_disponible:,.2f}", foreground=cupo_color
            )
            self.lbl_exito_cupo.config(
                text=f"✅ Cupo de crédito actualizado a ${cli.limite_credito:,.2f} COP."
            )

        except ValueError as e:
            self.area_error_cupo.mostrar_error(str(e))
        except Exception as e:
            self.area_error_cupo.mostrar_error(f"Error inesperado al asignar cupo: {e}")

    # =========================================================================
    # ACCIÓN 3: REGISTRO DE ABONOS CON ACTUALIZACIÓN EN CASCADA (RF-CXC-04)
    # =========================================================================

    def _registrar_abono(self) -> None:
        """
        Registra un abono a cartera y dispara la actualización en cascada:
        (a) Nueva fila en tabla de movimientos CxC.
        (b) Bloque de cupo y saldos actualizados.
        (c) Badge de Score y Decisión recalculados.
        """
        self.area_error_abono.limpiar()
        self.lbl_exito_abono.config(text="")

        if not self._cliente_actual:
            self.area_error_abono.mostrar_error("Seleccione un cliente para registrar el abono.")
            return

        texto_monto = self.entry_monto_abono.get().strip()
        desc = self.entry_desc_abono.get().strip() or "Abono en efectivo"

        try:
            monto = float(texto_monto)
        except ValueError:
            self.area_error_abono.mostrar_error("Ingrese un monto de abono válido.")
            return

        try:
            saldo_previo = self._cliente_actual.saldo_actual
            usuario_id = self.sesion.usuario_actual.id if (self.sesion and self.sesion.usuario_actual) else None
            abono_dto = cxc_service.registrar_abono(
                cliente_id=self._cliente_actual.id,
                monto=monto,
                conn=self.sesion.conn,
                descripcion=desc,
                auto_commit=True,
                usuario_id=usuario_id,
            )

            # Guardar referencia para comprobante digital
            self._ultimo_abono = {
                "abono_id": abono_dto.id,
                "cliente_nombre": self._cliente_actual.nombre,
                "cliente_id": self._cliente_actual.id,
                "monto": monto,
                "saldo_previo": saldo_previo,
                "saldo_resultante": abono_dto.saldo_resultante,
                "descripcion": desc,
                "fecha": abono_dto.fecha_movimiento or "Ahora",
                "usuario": self.sesion.usuario_actual.nombre if self.sesion.usuario_actual else "Sistema",
            }

            # --- CASCADA REACTIVA ---
            # 1. Refrescar cliente en memoria desde BD
            cli_fresco = cxc_service.obtener_cliente(self._cliente_actual.id, self.sesion.conn)
            self._cliente_actual = cli_fresco

            # (b) Actualizar bloque de saldos y cupo
            self.lbl_saldo_actual.config(text=f"Saldo: ${cli_fresco.saldo_actual:,.2f}")
            cupo_color = "#27ae60" if cli_fresco.cupo_disponible > 0 else "#c0392b"
            self.lbl_cupo_disp.config(
                text=f"Disponible: ${cli_fresco.cupo_disponible:,.2f}", foreground=cupo_color
            )

            # (c) Recalcular Score y Clase de Riesgo en vivo
            self._actualizar_scoring_visual(cli_fresco.id)

            # (a) Refrescar historial append-only
            self._cargar_historial_cxc(cli_fresco.id)

            # Limpiar entradas de abono
            self.entry_monto_abono.delete(0, tk.END)
            self.lbl_exito_abono.config(
                text=f"✅ Abono #{abono_dto.id} por ${monto:,.2f} registrado. Nuevo saldo: ${abono_dto.saldo_resultante:,.2f} COP."
            )

        except ValueError as e:
            self.area_error_abono.mostrar_error(str(e))
        except Exception as e:
            self.area_error_abono.mostrar_error(f"Error inesperado al registrar abono: {e}")

    # =========================================================================
    # COMPROBANTE DIGITAL EN PDF 80MM (RF-CXC-04)
    # =========================================================================

    def _abrir_pdf_sistema(self, ruta_pdf: str) -> None:
        """Abre el archivo PDF generado en el visor predeterminado del sistema operativo."""
        try:
            if sys.platform == "win32":
                os.startfile(ruta_pdf)
            elif sys.platform == "darwin":
                subprocess.run(["open", ruta_pdf], check=True)
            else:
                subprocess.run(["xdg-open", ruta_pdf], check=True)
        except Exception as e:
            self.area_error_abono.mostrar_error(
                f"Comprobante PDF generado en '{ruta_pdf}', pero no se pudo abrir el visor del sistema: {e}"
            )

    def _ver_comprobante(self) -> None:
        """
        Genera el comprobante en formato tirilla térmica 80mm en PDF (RF-CXC-04)
        y lo abre en el visor predeterminado del sistema operativo.
        """
        self.area_error_abono.limpiar()

        movimiento_id: Optional[int] = None

        # 1. Prioridad: movimiento seleccionado en la tabla de historial
        seleccion = self.tree_historial.selection()
        if seleccion:
            valores = self.tree_historial.item(seleccion[0], "values")
            if valores and valores[0]:
                try:
                    movimiento_id = int(valores[0])
                except (ValueError, TypeError):
                    pass

        # 2. Si no hay selección, usar el último abono registrado en la sesión
        if movimiento_id is None and self._ultimo_abono and isinstance(self._ultimo_abono.get("abono_id"), int):
            movimiento_id = self._ultimo_abono["abono_id"]

        # 3. Si aún no hay ID, pero el cliente tiene movimientos en el historial
        if movimiento_id is None and self._cliente_actual:
            hijos = self.tree_historial.get_children()
            if hijos:
                ultimos_valores = self.tree_historial.item(hijos[-1], "values")
                if ultimos_valores and ultimos_valores[0]:
                    try:
                        movimiento_id = int(ultimos_valores[0])
                    except (ValueError, TypeError):
                        pass

        if movimiento_id is None:
            self.area_error_abono.mostrar_error(
                "Seleccione un movimiento del historial o registre un abono para generar su comprobante en PDF."
            )
            return

        try:
            ruta_pdf = reportes_service.generar_comprobante_pdf(
                movimiento_id=movimiento_id,
                conn=self.sesion.conn,
            )
            self._abrir_pdf_sistema(ruta_pdf)
        except ValueError as e:
            self.area_error_abono.mostrar_error(str(e))
        except Exception as e:
            self.area_error_abono.mostrar_error(f"Error al generar comprobante en PDF: {e}")

    # =========================================================================
    # DIÁLOGO MODAL: CREAR NUEVO CLIENTE (RF-CXC-02)
    # =========================================================================

    def _abrir_modal_nuevo_cliente(self) -> None:
        """Abre ventana modal para dar de alta a un nuevo cliente en el sistema."""
        dialog = tk.Toplevel(self)
        dialog.title("Registrar Nuevo Cliente")
        dialog.geometry("420x360")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(background=COLOR_FONDO_APP)

        frame = tk.Frame(dialog, background=COLOR_FONDO_APP, padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame,
            text="➕ Alta de Cliente",
            font=FUENTE_SUBTITULO,
            background=COLOR_FONDO_APP,
            foreground=COLOR_TEXTO_PRINCIPAL,
        ).pack(anchor="w", pady=(0, 10))

        # Campos
        tk.Label(frame, text="Nombre completo (*):", font=FUENTE_BASE_BOLD, background=COLOR_FONDO_APP).pack(anchor="w")
        entry_nom = ttk.Entry(frame, width=35)
        entry_nom.pack(fill=tk.X, pady=(2, 6))

        tk.Label(frame, text="Teléfono:", font=FUENTE_BASE_BOLD, background=COLOR_FONDO_APP).pack(anchor="w")
        entry_tel = ttk.Entry(frame, width=35)
        entry_tel.pack(fill=tk.X, pady=(2, 6))

        tk.Label(frame, text="Dirección:", font=FUENTE_BASE_BOLD, background=COLOR_FONDO_APP).pack(anchor="w")
        entry_dir = ttk.Entry(frame, width=35)
        entry_dir.pack(fill=tk.X, pady=(2, 6))

        tk.Label(frame, text="Nivel de vínculo:", font=FUENTE_BASE_BOLD, background=COLOR_FONDO_APP).pack(anchor="w")
        combo_v = ttk.Combobox(
            frame,
            values=["solo_apodo", "conocido_referido", "registro_completo"],
            state="readonly",
        )
        combo_v.set("solo_apodo")
        combo_v.pack(fill=tk.X, pady=(2, 10))

        area_err_modal = AreaError(frame)

        def _guardar_nuevo():
            nom = entry_nom.get().strip()
            tel = entry_tel.get().strip() or None
            dire = entry_dir.get().strip() or None
            vinc = combo_v.get()

            try:
                nuevo = cxc_service.crear_cliente(
                    nombre=nom,
                    conn=self.sesion.conn,
                    telefono=tel,
                    direccion=dire,
                    nivel_vinculo=vinc,
                    limite_credito=0.0,
                )
                dialog.destroy()
                self._cargar_selector_clientes(mantener_id=nuevo.id)
                self._cargar_ficha_cliente(nuevo.id)
            except ValueError as e:
                area_err_modal.mostrar_error(str(e))

        btn_crear = ttk.Button(frame, text="Crear Cliente", style="Primary.TButton", command=_guardar_nuevo)
        btn_crear.pack(fill=tk.X, pady=(10, 0))

    # =========================================================================
    # RECARGA Y NAVEGACIÓN (al_mostrar)
    # =========================================================================

    def _cargar_selector_clientes(self, mantener_id: Optional[int] = None) -> None:
        """Carga o actualiza el Combobox de clientes activos."""
        termino = self.entry_buscar_termino.get().strip()
        if termino:
            clientes = cxc_service.buscar_clientes(termino, self.sesion.conn, solo_activos=True)
        else:
            clientes = cxc_service.listar_clientes(self.sesion.conn, solo_activos=True)

        self._clientes_map.clear()
        opciones: List[str] = []
        indice_seleccionar = 0

        for idx, c in enumerate(clientes):
            etiqueta = f"{c.nombre} (ID: {c.id})"
            opciones.append(etiqueta)
            self._clientes_map[etiqueta] = c.id
            if mantener_id and c.id == mantener_id:
                indice_seleccionar = idx

        self.combo_clientes["values"] = opciones
        if opciones:
            self.combo_clientes.current(indice_seleccionar)
            cliente_id = self._clientes_map[opciones[indice_seleccionar]]
            self._cargar_ficha_cliente(cliente_id)

    def _filtrar_clientes(self) -> None:
        """Aplica el término de búsqueda de clientes."""
        self._cargar_selector_clientes()

    def _limpiar_busqueda_clientes(self) -> None:
        """Limpia la búsqueda y lista todos los clientes activos."""
        self.entry_buscar_termino.delete(0, tk.END)
        self._cargar_selector_clientes()

    def _on_cliente_seleccionado(self, event=None) -> None:
        """Manejador al cambiar la selección en el Combobox de clientes."""
        sel = self.combo_clientes.get()
        cid = self._clientes_map.get(sel)
        if cid:
            self._cargar_ficha_cliente(cid)

    def al_mostrar(self) -> None:
        """Hook invocado por App.navegar_a al levantar esta pantalla."""
        self._limpiar_mensajes()
        self.btn_asignar_cupo.actualizar_estado()
        self._cargar_selector_clientes(
            mantener_id=self._cliente_actual.id if self._cliente_actual else None
        )
