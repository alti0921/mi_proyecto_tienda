import os
import sys
import ctypes
import sqlite3
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional, Any

from db.connection import get_connection
from db.rutas import es_ejecutable, ruta_base_datos, carpeta_datos
from scripts.inicializar_base_tienda import preparar_base_datos
from ui.estilos import COLOR_FONDO_APP, configurar_estilos, px
from ui.sesion import SesionActual
from ui.widgets_comunes import BarraSuperior
from ui.pantallas.login import PantallaLogin
from ui.pantallas.pos import PantallaPOS
from ui.pantallas.perfil_cliente import PantallaPerfilCliente
from ui.pantallas.inventario import PantallaInventario
from ui.pantallas.reportes import PantallaReportes
from ui.pantallas.usuarios import PantallaUsuarios


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

    def __init__(
        self,
        conn: Optional[sqlite3.Connection] = None,
        target_scale: Optional[float] = None,
        geom: Optional[str] = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if target_scale is not None:
            self.tk.call("tk", "scaling", target_scale)

        # 1. Configuración de Ventana y Adaptabilidad
        self.title("Sistema de Información y Scoring Crediticio — Micronegocios")
        self.configure(background=COLOR_FONDO_APP)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        min_w = int(min(px(self, 900), sw * 0.95))
        min_h = int(min(px(self, 600), sh * 0.90))
        self.minsize(min_w, min_h)

        if geom:
            self.geometry(geom)
        else:
            init_w = int(sw * 0.90)
            init_h = int(sh * 0.85)
            pos_x = max(0, (sw - init_w) // 2)
            pos_y = max(0, (sh - init_h) // 2)
            self.geometry(f"{init_w}x{init_h}+{pos_x}+{pos_y}")

            if sys.platform == "win32":
                try:
                    self.state("zoomed")
                except Exception:
                    pass

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
        self.pantalla_actual: str = "login"
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

        # Pantalla 5: Reportes Operativos
        self.pantallas["reportes"] = PantallaReportes(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["reportes"].grid(row=0, column=0, sticky="nsew")

        # Pantalla 6: Gestión de Usuarios
        self.pantallas["usuarios"] = PantallaUsuarios(
            parent=self.contenedor,
            app=self,
            sesion=self.sesion,
        )
        self.pantallas["usuarios"].grid(row=0, column=0, sticky="nsew")

    def navegar_a(self, nombre_pantalla: str) -> None:
        """
        Navega hacia la pantalla indicada levantándola al tope del stack visual (tkraise).
        Ajusta la visibilidad de la barra superior según el estado de autenticación.
        """
        if nombre_pantalla not in self.pantallas:
            raise ValueError(f"Pantalla '{nombre_pantalla}' no registrada.")

        if self.sesion.debe_cambiar_password and nombre_pantalla not in ("usuarios", "login"):
            pantalla_usuarios = self.pantallas.get("usuarios")
            if pantalla_usuarios and hasattr(pantalla_usuarios, "mostrar_aviso_seguridad"):
                pantalla_usuarios.mostrar_aviso_seguridad()
            return

        pantalla = self.pantallas[nombre_pantalla]
        self.pantalla_actual = nombre_pantalla

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

    def report_callback_exception(self, exc, val, tb) -> None:
        """Captura excepciones no manejadas en callbacks de Tkinter sin cerrar la aplicación."""
        detalle = "".join(traceback.format_exception(exc, val, tb))
        log_path = _registrar_error(detalle)
        try:
            messagebox.showerror(
                "Error Inesperado",
                f"Ocurrió un error inesperado. La aplicación sigue abierta. El detalle quedó en: {log_path}",
            )
        except Exception:
            pass

    def destroy(self) -> None:
        """Cierre ordenado de la aplicación y de la conexión a base de datos."""
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        super().destroy()


def _registrar_error(detalle: str) -> str:
    """Registra el detalle del error en carpeta_datos()/errores.log y retorna la ruta del archivo."""
    log_dir = carpeta_datos()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "errores.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error:\n{detalle}\n" + "=" * 50 + "\n")
    except Exception:
        pass
    return log_path


def main() -> None:
    """Punto de entrada principal con reconocimiento de DPI de Windows antes de crear la ventana Tk."""
    try:
        if es_ejecutable() and not os.path.exists(ruta_base_datos()):
            preparar_base_datos(ruta_base_datos())

        if sys.platform == "win32":
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

        app = App()
        app.mainloop()
    except Exception as e:
        detalle = traceback.format_exc()
        log_path = _registrar_error(detalle)

        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Error Crítico",
                f"Ocurrió un error y la aplicación debe cerrarse. El detalle quedó en: {log_path}",
            )
            root.destroy()
        except Exception:
            pass

        if not es_ejecutable():
            raise


if __name__ == "__main__":
    main()
