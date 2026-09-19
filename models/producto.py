from dataclasses import dataclass
from typing import Optional

@dataclass
class Producto:
    id: Optional[int] = None
    codigo_barras: Optional[str] = None
    nombre: str = ""
    categoria: str = "canasta_basica"
    precio_venta: float = 0.0
    costo: float = 0.0
    stock: float = 0.0
    stock_minimo: float = 5.0
    activo: bool = True
