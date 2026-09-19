from dataclasses import dataclass
from typing import Optional

@dataclass
class Producto:
    id: Optional[int] = None
    codigo_barras: Optional[str] = None
    nombre: str = ""
    categoria: str = "canasta_basica"  # 'canasta_basica', 'cesta_mixta', 'consumo_suntuario'
    precio_venta: float = 0.0
    costo: float = 0.0
    stock: float = 0.0
    stock_minimo: float = 5.0
    activo: bool = True

    @property
    def margen(self) -> float:
        """Propiedad calculada: ganancia o margen bruto unitario."""
        return round(self.precio_venta - self.costo, 2)

    @property
    def alerta_stock_bajo(self) -> bool:
        """Propiedad calculada: verdadero si el stock actual es menor o igual al mínimo."""
        return self.stock <= self.stock_minimo
