"""
Pruebas unitarias para funciones de escalado dinámico (DPI) y conversión de píxeles.
"""

import tkinter as tk
from ui.estilos import factor_escala, px


def test_px_y_factor_escala():
    """
    Verifica la conversión de píxeles con diferentes factores de escala Tkinter (DPI):
    - scaling = 1.3333 (96 DPI base) -> factor 1.0 -> px(100) == 100
    - scaling = 2.0 (144 DPI / 150%) -> factor 1.5 -> px(100) == 150
    Restaura el valor original de scaling al finalizar.
    """
    root = tk.Tk()
    root.withdraw()

    scaling_original = float(root.tk.call("tk", "scaling"))
    try:
        # 1. Escala estándar 96 DPI (100%)
        root.tk.call("tk", "scaling", 1.3333)
        assert factor_escala(root) == 1.0
        assert px(root, 100) == 100
        assert px(100) == 100

        # 2. Escala 144 DPI (150%)
        root.tk.call("tk", "scaling", 2.0)
        assert abs(factor_escala(root) - 1.5) < 0.01
        assert px(root, 100) == 150
        assert px(100) == 150
    finally:
        root.tk.call("tk", "scaling", scaling_original)
        root.destroy()
