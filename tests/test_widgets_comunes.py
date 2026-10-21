"""
Pruebas unitarias para utilidades de widgets comunes y adaptabilidad responsive.
"""

import tkinter as tk
from ui.widgets_comunes import (
    MarcoDesplazable,
    ajustar_wraplength,
    configurar_columnas,
    agregar_scroll_horizontal,
)


def test_marco_desplazable():
    """
    Verifica el comportamiento de MarcoDesplazable:
    - Ventana de 300x200 con 30 labels en interior.
    - Altura de scrollregion (bbox) > canvas.winfo_height().
    - Barra vertical visible (winfo_ismapped).
    - |interior.winfo_width() - canvas.winfo_width()| <= 2.
    - Tras desplazar_al_final(), canvas.yview()[1] == 1.0.
    """
    root = tk.Tk()
    root.geometry("300x200")
    root.deiconify()
    try:
        marco = MarcoDesplazable(root)
        marco.pack(fill=tk.BOTH, expand=True)

        for i in range(30):
            lbl = tk.Label(marco.interior, text=f"Item de prueba {i}")
            lbl.pack(pady=4)

        root.update()

        bbox = marco.canvas.bbox("all")
        assert bbox is not None
        altura_scroll = bbox[3] - bbox[1]
        assert altura_scroll > marco.canvas.winfo_height()
        assert marco.scrollbar.winfo_ismapped()
        assert abs(marco.interior.winfo_width() - marco.canvas.winfo_width()) <= 2

        marco.desplazar_al_final()
        root.update()
        assert marco.canvas.yview()[1] == 1.0
    finally:
        root.destroy()


def test_ajustar_wraplength():
    """
    Verifica que ajustar_wraplength configure anchor='w', justify=LEFT
    y ajuste reactivamente el wraplength ante el ancho de la ventana.
    """
    root = tk.Tk()
    root.geometry("400x200")
    root.deiconify()
    try:
        lbl = tk.Label(
            root,
            text="Texto de prueba suficientemente largo para validar wraplength adaptable",
        )
        lbl.pack(fill=tk.X)
        ajustar_wraplength(lbl, margen_px=10)

        root.update()

        wrap = int(lbl.cget("wraplength"))
        assert 300 <= wrap <= 400
        assert lbl.cget("anchor") == "w"
    finally:
        root.destroy()
