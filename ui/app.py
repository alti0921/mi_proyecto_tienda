import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional, Any

from db.connection import get_connection
from ui.estilos import COLOR_FONDO_APP, configurar_estilos
from ui.sesion import SesionActual
from ui.widgets_comunes import BarraSuperior
from ui.pantallas.login import PantallaLogin
from ui.pantallas.pos import PantallaPOS
from ui.pantallas.perfil_cliente import PantallaPerfilCliente
from ui.pantallas.inventario import PantallaInventario


class PantallaPlaceholder(tk.Frame):
    """Vista provisional para pantallas de hitos posteriores."""

    def __init__(self, parent: tk.Widget, nombre: str, app: Any, *args, **kwargs):
        super().__init__(parent, background=COLOR_FONDO_APP, *args, **kwargs)
        self.nombre = nombre
        self.app = app

        lbl = tk.Label(
            self,
            text=f"🚧 Módulo '{nombre.upper()}' en Construcción",
            font=("Segoe UI", 16, "bold"),
            background=COLOR_FONDO_APP,
            foreground="#2c3e50",
        )
        lbl.pack(expand=True, pady=40)


class App(tk.Tk):
    """
    Ventana y controlador principal de la aplicación de escritorio Tkinter.
    Orquesta la conexión a base de datos, el ciclo de vida de la sesión activa,
    el tema visual y la navegación desacoplada entre pantallas.
    """

    def __init__(self, conn: Optional[sqlite3.Connection] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Configuración de Ventana
        self.title("Sistema de Información y Scoring Crediticio — Micronegocios")
        self.geometry("1120x720")
        self.minsize(980, 640)
        self.configure(background=COLOR_FONDO_APP)

        # 2. Persistencia y Sesión
        self.conn = conn if conn is not None else get_connection()
        self.sesion = SesionActual(self.conn)

        # 3. Tema Visual
        self.style = configurar_estilos(self)

        # 4. Estructura de Contenedores
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Barra Superior Persistente (Oculta en Login, visible en pantallas autenticadas)
        self.barra_superior = BarraSuperior(
            self,
            sesion=self.sesion,
            on_cerrar_sesion=self.cerrar_sesion,
            on_navegar=self.navegar_a,
        )

        # Contenedor de Pantallas (Stack de Frames)
        self.contenedor = tk.Frame(self, background=COLOR_FONDO_APP)
        self.contenedor.grid(row=1, column=0, sticky="nsew")
        self.contenedor.grid_rowconfigure(0, weight=1)
        self.contenedor.grid_columnconfigure(0, weight=1)

        # 5. Registro de Pantallas
        self.pantallas: Dict[str, tk.Frame] = {}
        self._registrar_pantallas()

        # 6. Estado Inicial
        self.navegar_a("login")

    def _registrar_pantallas(self) -> None:
        """Instancia y registra cada pantalla en el contenedor principal."""
        # Pantalla 1: Login
        self.pantallas["login"] = PantallaLogin(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["login"].grid(row=0, column=0, sticky="nsew")

        # Pantalla 2: POS
        self.pantallas["pos"] = PantallaPOS(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["pos"].grid(row=0, column=0, sticky="nsew")

        # Pantalla 3: Clientes / CxC
        self.pantallas["cxc"] = PantallaPerfilCliente(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["cxc"].grid(row=0, column=0, sticky="nsew")

        # Pantalla 4: Inventario
        self.pantallas["inventario"] = PantallaInventario(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["inventario"].grid(row=0, column=0, sticky="nsew")

        # Pantallas provisionales (se reemplazarán en los siguientes hitos)
        for nombre in ("reportes",):
            frame = PantallaPlaceholder(parent=self.contenedor, nombre=nombre, app=self)
            frame.grid(row=0, column=0, sticky="nsew")
            self.pantallas[nombre] = frame

    def navegar_a(self, nombre_pantalla: str) -> None:
        """
        Navega hacia la pantalla indicada levantándola al tope del stack visual (tkraise).
        Ajusta la visibilidad de la barra superior según el estado de autenticación.
        """
        if nombre_pantalla not in self.pantallas:
            raise ValueError(f"Pantalla '{nombre_pantalla}' no registrada.")

        pantalla = self.pantallas[nombre_pantalla]

        # Gestionar barra superior
        if nombre_pantalla == "login":
            self.barra_superior.grid_forget()
        else:
            self.barra_superior.actualizar_datos()
            self.barra_superior.grid(row=0, column=0, sticky="ew")

        # Invocar hook al_mostrar si está implementado en la pantalla
        if hasattr(pantalla, "al_mostrar") and callable(getattr(pantalla, "al_mostrar")):
            pantalla.al_mostrar()

        pantalla.tkraise()

    def cerrar_sesion(self) -> None:
        """Finaliza la sesión del usuario actual y retorna a la pantalla de login."""
        self.sesion.cerrar_sesion()
        self.navegar_a("login")

    def destroy(self) -> None:
        """Cierre ordenado de la aplicación y de la conexión a base de datos."""
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
