from services.scoring_service import (
    calcular_sw1,
    calcular_sw2,
    calcular_sw3,
    calcular_score,
    aplicar_matriz_decision,
    evaluar_cold_start,
    registrar_snapshot,
)
from services.inventario_service import (
    crear_producto,
    obtener_producto,
    obtener_producto_por_codigo,
    listar_productos,
    actualizar_producto,
    ajustar_stock,
    desactivar_producto,
    listar_alertas_stock,
)

__all__ = [
    "calcular_sw1",
    "calcular_sw2",
    "calcular_sw3",
    "calcular_score",
    "aplicar_matriz_decision",
    "evaluar_cold_start",
    "registrar_snapshot",
    "crear_producto",
    "obtener_producto",
    "obtener_producto_por_codigo",
    "listar_productos",
    "actualizar_producto",
    "ajustar_stock",
    "desactivar_producto",
    "listar_alertas_stock",
]
