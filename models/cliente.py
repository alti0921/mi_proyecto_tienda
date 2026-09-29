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

    @property
    def cupo_disponible(self) -> float:
        """Calcula el cupo de crédito disponible actual (RF-CXC-05)."""
        return max(0.0, round(self.limite_credito - self.saldo_actual, 2))

