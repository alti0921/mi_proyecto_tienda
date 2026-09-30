import sqlite3
from typing import Optional
from models.usuario import Usuario


class SesionActual:
    """
    Gestiona el estado de la sesión activa del usuario en la aplicación (RF-AUT-01).
    Almacena el usuario autenticado y la conexión compartida a la base de datos SQLite.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.usuario_actual: Optional[Usuario] = None

    def iniciar_sesion(self, usuario: Usuario) -> None:
        """Establece el usuario autenticado para la sesión en curso."""
        self.usuario_actual = usuario

    def cerrar_sesion(self) -> None:
        """Limpia la sesión activa, restableciendo usuario_actual a None."""
        self.usuario_actual = None

    @property
    def esta_autenticado(self) -> bool:
        """Indica si existe una sesión activa válida."""
        return self.usuario_actual is not None

    @property
    def es_admin(self) -> bool:
        """Indica si el usuario activo tiene rol de administrador."""
        return self.usuario_actual is not None and self.usuario_actual.rol == "admin"

    @property
    def rol_actual(self) -> Optional[str]:
        """Retorna el rol ('admin' o 'vendedor') del usuario en sesión, o None."""
        return self.usuario_actual.rol if self.usuario_actual else None

    @property
    def nombre_usuario(self) -> str:
        """Retorna el nombre descriptivo del usuario activo."""
        return self.usuario_actual.nombre if self.usuario_actual else ""
