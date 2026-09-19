from dataclasses import dataclass
from typing import Optional

@dataclass
class Cliente:
    id: Optional[int] = None
    nombre: str = ""
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    nivel_vinculo: str = "solo_apodo"
    limite_credito: float = 0.0
    saldo_actual: float = 0.0
    score_crediticio: int = 60
    categoria_riesgo: str = "B"
    activo: bool = True
