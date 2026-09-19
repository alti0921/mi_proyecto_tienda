from dataclasses import dataclass
from typing import Optional

@dataclass
class CuentaPorCobrar:
    id: Optional[int] = None
    cliente_id: int = 0
    venta_id: Optional[int] = None
    tipo_movimiento: str = "cargo"
    monto: float = 0.0
    saldo_resultante: float = 0.0
    descripcion: Optional[str] = None
    fecha_movimiento: Optional[str] = None
