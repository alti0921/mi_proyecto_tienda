from dataclasses import dataclass
from typing import Optional

@dataclass
class Venta:
    id: Optional[int] = None
    usuario_id: int = 1
    cliente_id: Optional[int] = None
    tipo_pago: str = "efectivo"  # Valores permitidos: 'efectivo', 'nequi', 'credito'
    total: float = 0.0
    monto_pagado: float = 0.0
    fecha_venta: Optional[str] = None

    @property
    def monto_cambio(self) -> float:
        """Calcula el cambio a devolver en transacciones de contado."""
        if self.tipo_pago in ("efectivo", "nequi"):
            return max(0.0, round(self.monto_pagado - self.total, 2))
        return 0.0
