from dataclasses import dataclass
from typing import Optional

@dataclass
class Venta:
    id: Optional[int] = None
    usuario_id: int = 1
    cliente_id: Optional[int] = None
    tipo_pago: str = "efectivo"
    total: float = 0.0
    monto_pagado: float = 0.0
    fecha_venta: Optional[str] = None
