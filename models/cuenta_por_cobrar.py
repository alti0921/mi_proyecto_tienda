from dataclasses import dataclass
from typing import Optional

@dataclass
class CuentaPorCobrar:
    """
    DTO / Read-Model en memoria que representa un registro de la tabla 'cuentas_por_cobrar'.
    Nota de diseño: La tabla subyacente es un libro mayor inmutable (Append-Only)
    protegido por triggers SQLite que impiden cualquier operación UPDATE o DELETE.
    """
    id: Optional[int] = None
    cliente_id: int = 0
    venta_id: Optional[int] = None
    tipo_movimiento: str = "cargo"  # 'cargo' o 'abono'
    monto: float = 0.0
    saldo_resultante: float = 0.0
    descripcion: Optional[str] = None
    fecha_movimiento: Optional[str] = None
