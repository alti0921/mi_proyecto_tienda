from dataclasses import dataclass
from typing import Optional

@dataclass
class VentaDetalle:
    id: Optional[int] = None
    venta_id: int = 0
    producto_id: Optional[int] = None
    descripcion: str = ""
    cantidad: float = 1.0
    precio_unitario: float = 0.0
    subtotal: float = 0.0
