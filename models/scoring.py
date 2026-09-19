from dataclasses import dataclass
from typing import Optional

@dataclass
class ScoringHistorial:
    id: Optional[int] = None
    cliente_id: int = 0
    sw1: float = 0.0
    sw2: float = 0.0
    sw3: float = 0.0
    score_anterior: int = 60
    score_nuevo: int = 60
    categoria_anterior: str = "B"
    categoria_nueva: str = "B"
    motivo: str = ""
    fecha_calculo: Optional[str] = None
