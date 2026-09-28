from dataclasses import dataclass
from typing import Optional


@dataclass
class Usuario:
    """Modelo de dominio puro para usuarios del sistema (RF-AUT-01)."""
    id: Optional[int]
    username: str
    nombre: str
    rol: str = "vendedor"  # Valores permitidos: 'admin', 'vendedor'
    activo: bool = True
    created_at: Optional[str] = None
