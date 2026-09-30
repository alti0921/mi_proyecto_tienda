import tkinter as tk
from tkinter import ttk
from typing import Dict, Any

# ============================================================================
# PALETA DE COLORES (Conforme a Wireframes y Guía de Estilos)
# ============================================================================

# Colores Base / Neutros
COLOR_FONDO_APP = "#f4f6f8"
COLOR_BLANCO = "#ffffff"
COLOR_TEXTO_PRINCIPAL = "#2c3e50"
COLOR_TEXTO_SECUNDARIO = "#7f8c8d"
COLOR_TEXTO_MUTED = "#95a5a6"
COLOR_BORDE_NEUTRAL = "#dcdde1"

# Barra Superior / Navegación
COLOR_BARRA_SUPERIOR = "#e8e8e8"
COLOR_BARRA_BORDE = "#d0d0d0"

# Botones y Acentos
COLOR_PRIMARIO = "#2980b9"
COLOR_PRIMARIO_HOVER = "#3498db"
COLOR_EXITO = "#27ae60"
COLOR_EXITO_HOVER = "#2ecc71"
COLOR_PELIGRO = "#c0392b"
COLOR_PELIGRO_HOVER = "#e74c3c"
COLOR_NEUTRO_BTN = "#bdc3c7"
COLOR_NEUTRO_BTN_TEXTO = "#2c3e50"

# Alertas y Errores (Área de Error y Borde Rojo)
COLOR_ERROR_BG = "#f8d7da"
COLOR_ERROR_TEXTO = "#721c24"
COLOR_ERROR_BORDE = "#c0392b"

# Alerta Stock Bajo / Preventiva (Ámbar)
COLOR_ALERTA_BG = "#fff3cd"
COLOR_ALERTA_TEXTO = "#856404"
COLOR_ALERTA_BORDE = "#ffeeba"

# ============================================================================
# MATRIZ SEMÁFORO DE SCORING (Clases A, B, C, D)
# ============================================================================

COLORES_SCORING: Dict[str, Dict[str, str]] = {
    "A": {
        "bg": "#d4edda",
        "fg": "#155724",
        "borde": "#27ae60",
        "etiqueta": "Clase A — Riesgo Bajo",
    },
    "B": {
        "bg": "#d1ecf1",
        "fg": "#0c5460",
        "borde": "#2980b9",
        "etiqueta": "Clase B — Riesgo Medio",
    },
    "C": {
        "bg": "#fff3cd",
        "fg": "#856404",
        "borde": "#f39c12",
        "etiqueta": "Clase C — Riesgo Alto (Congelado)",
    },
    "D": {
        "bg": "#f8d7da",
        "fg": "#721c24",
        "borde": "#c0392b",
        "etiqueta": "Clase D — Riesgo Crítico (Bloqueado)",
    },
}

# ============================================================================
# TIPOGRAFÍAS (Segoe UI con fallbacks estándar)
# ============================================================================

FUENTE_FAMILIA = "Segoe UI"
FUENTE_MONO = "Consolas"

FUENTE_TITULO_GRANDE = (FUENTE_FAMILIA, 18, "bold")
FUENTE_TITULO = (FUENTE_FAMILIA, 14, "bold")
FUENTE_SUBTITULO = (FUENTE_FAMILIA, 11, "bold")
FUENTE_BASE = (FUENTE_FAMILIA, 10)
FUENTE_BASE_BOLD = (FUENTE_FAMILIA, 10, "bold")
FUENTE_PEQUENA = (FUENTE_FAMILIA, 9)
FUENTE_BOTON = (FUENTE_FAMILIA, 10, "bold")
FUENTE_KPI_NUMERO = (FUENTE_FAMILIA, 20, "bold")
FUENTE_MONO_BASE = (FUENTE_MONO, 10)

# ============================================================================
# ESPACIADOS Y MÁRGENES
# ============================================================================

PAD_EXTERNO = 15
PAD_INTERNO = 10
PAD_CAMPOS = 6


def configurar_estilos(root: tk.Tk) -> ttk.Style:
    """
    Inicializa y configura el tema visual de la aplicación mediante ttk.Style.
    Establece estilos consistentes para Frames, Labels, Entries y Buttons.
    """
    style = ttk.Style(root)

    # Usar tema 'clam' si está disponible por su flexibilidad para colores
    temas_disponibles = style.theme_names()
    if "clam" in temas_disponibles:
        style.theme_use("clam")
    elif "vista" in temas_disponibles:
        style.theme_use("vista")

    # Configuración de base
    style.configure(".", font=FUENTE_BASE, background=COLOR_FONDO_APP)

    # Frames
    style.configure("TFrame", background=COLOR_FONDO_APP)
    style.configure("Card.TFrame", background=COLOR_BLANCO, relief="solid", borderwidth=1)
    style.configure("TopBar.TFrame", background=COLOR_BARRA_SUPERIOR)

    # Labels
    style.configure("TLabel", background=COLOR_FONDO_APP, foreground=COLOR_TEXTO_PRINCIPAL)
    style.configure("Card.TLabel", background=COLOR_BLANCO, foreground=COLOR_TEXTO_PRINCIPAL)
    style.configure("Title.TLabel", font=FUENTE_TITULO_GRANDE, foreground=COLOR_TEXTO_PRINCIPAL)
    style.configure("Subtitle.TLabel", font=FUENTE_SUBTITULO, foreground=COLOR_TEXTO_SECUNDARIO)
    style.configure("TopBar.TLabel", background=COLOR_BARRA_SUPERIOR, font=FUENTE_BASE_BOLD)
    style.configure("TopBarTitle.TLabel", background=COLOR_BARRA_SUPERIOR, font=FUENTE_TITULO, foreground="#1e272e")

    # Botones
    style.configure(
        "TButton",
        font=FUENTE_BOTON,
        padding=(12, 6),
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("active", "#dcdde1"), ("disabled", "#e5e5e5")],
        foreground=[("disabled", "#a4b0be")],
    )

    # Botón Primario (Azul)
    style.configure(
        "Primary.TButton",
        font=FUENTE_BOTON,
        background=COLOR_PRIMARIO,
        foreground=COLOR_BLANCO,
        padding=(14, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_PRIMARIO_HOVER), ("disabled", "#a4b0be")],
        foreground=[("disabled", "#ffffff")],
    )

    # Botón Éxito (Verde)
    style.configure(
        "Success.TButton",
        font=FUENTE_BOTON,
        background=COLOR_EXITO,
        foreground=COLOR_BLANCO,
        padding=(12, 6),
    )
    style.map(
        "Success.TButton",
        background=[("active", COLOR_EXITO_HOVER), ("disabled", "#a4b0be")],
    )

    # Botón Peligro (Rojo)
    style.configure(
        "Danger.TButton",
        font=FUENTE_BOTON,
        background=COLOR_PELIGRO,
        foreground=COLOR_BLANCO,
        padding=(10, 5),
    )
    style.map(
        "Danger.TButton",
        background=[("active", COLOR_PELIGRO_HOVER), ("disabled", "#a4b0be")],
    )

    # Entry
    style.configure(
        "TEntry",
        padding=(6, 4),
        fieldbackground=COLOR_BLANCO,
        foreground=COLOR_TEXTO_PRINCIPAL,
    )

    # Combobox
    style.configure("TCombobox", padding=(6, 4))

    return style
