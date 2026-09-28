import sqlite3
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Union
from models.venta import Venta
from models.cliente import Cliente
import services.inventario_service as inventario_service
import services.cxc_service as cxc_service
import services.scoring_service as scoring_service


@dataclass
class LineaVentaInput:
    """Representa una línea o ítem para el registro de una venta en el POS."""
    cantidad: float
    precio_unitario: float
    producto_id: Optional[int] = None
    descripcion: Optional[str] = None
    subtotal: Optional[float] = None


def asignar_limite_credito(
    cliente_id: int,
    nuevo_limite: float,
    conn: sqlite3.Connection,
) -> Cliente:
    """
    Asigna o actualiza el límite de crédito (cupo) de un cliente (RF-SCR-02 / RF-CXC-05).
    Requiere confirmación operativa del tendero.
    """
    if nuevo_limite < 0:
        raise ValueError(f"El límite de crédito no puede ser negativo ({nuevo_limite}).")

    cursor = conn.cursor()
    cursor.execute("SELECT id, activo FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row or not row["activo"]:
        raise ValueError(f"Cliente ID {cliente_id} no encontrado o inactivo.")

    try:
        cursor.execute(
            "UPDATE clientes SET limite_credito = ? WHERE id = ?",
            (round(float(nuevo_limite), 2), cliente_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    cliente = cxc_service.obtener_cliente(cliente_id, conn)
    return cliente


def _validar_credito_clase_c(
    cliente_id: int,
    conn: sqlite3.Connection,
    abono_previo_verificado: bool = False,
) -> None:
    """
    Valida la regla de negocio RF-SCR-04 para clientes en Clase C (Riesgo Alto / Congelado):
    Exige un abono previo de al menos el 50% de su saldo antes de despachar un nuevo fiado.
    """
    if abono_previo_verificado:
        return

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT tipo_movimiento, monto, saldo_resultante
        FROM cuentas_por_cobrar
        WHERE cliente_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (cliente_id,),
    )
    ultimo = cursor.fetchone()
    if not ultimo or ultimo["tipo_movimiento"] != "abono":
        raise ValueError(
            "Crédito rechazado (RF-SCR-04): Cliente en Clase C (Riesgo Alto / Congelado). "
            "Requiere un abono previo de al menos el 50% de su saldo antes de despachar un nuevo fiado."
        )

    monto_abono = float(ultimo["monto"])
    saldo_resultante = float(ultimo["saldo_resultante"])
    saldo_previo = round(saldo_resultante + monto_abono, 2)

    if saldo_previo > 0 and (monto_abono / saldo_previo) < 0.50:
        minimo_requerido = round(saldo_previo * 0.50, 2)
        raise ValueError(
            f"Crédito rechazado (RF-SCR-04): Cliente en Clase C. El último abono (${monto_abono:,.2f}) "
            f"no alcanza el 50% mínimo requerido (${minimo_requerido:,.2f}) sobre el saldo previo."
        )


def _normalizar_item(item: Union[LineaVentaInput, Dict[str, Any], Any], conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Normaliza y valida un ítem o línea de venta.
    Admite LineaVentaInput, diccionarios u objetos equivalentes.
    """
    if isinstance(item, dict):
        p_id = item.get("producto_id")
        cant = item.get("cantidad")
        p_unit = item.get("precio_unitario")
        desc = item.get("descripcion")
        sub = item.get("subtotal")
    else:
        p_id = getattr(item, "producto_id", None)
        cant = getattr(item, "cantidad", None)
        p_unit = getattr(item, "precio_unitario", None)
        desc = getattr(item, "descripcion", None)
        sub = getattr(item, "subtotal", None)

    if cant is None or float(cant) <= 0:
        raise ValueError(f"La cantidad del producto debe ser mayor a cero (recibido: {cant}).")
    if p_unit is None or float(p_unit) < 0:
        raise ValueError(f"El precio unitario no puede ser negativo ({p_unit}).")

    cant_float = float(cant)
    p_unit_float = float(p_unit)
    sub_float = round(cant_float * p_unit_float, 2) if sub is None else round(float(sub), 2)

    cursor = conn.cursor()
    if p_id is not None:
        cursor.execute("SELECT nombre FROM productos WHERE id = ?", (p_id,))
        p_row = cursor.fetchone()
        if not p_row:
            raise ValueError(f"Producto ID {p_id} no encontrado en el catálogo.")
        if not desc:
            desc = p_row["nombre"]
    else:
        if not desc or not str(desc).strip():
            desc = "Venta por monto global"

    return {
        "producto_id": p_id,
        "cantidad": cant_float,
        "precio_unitario": p_unit_float,
        "descripcion": str(desc).strip(),
        "subtotal": sub_float,
    }


def registrar_venta(
    usuario_id: int,
    tipo_pago: str,
    items: List[Union[LineaVentaInput, Dict[str, Any], Any]],
    conn: sqlite3.Connection,
    cliente_id: Optional[int] = None,
    monto_pagado: float = 0.0,
    abono_previo_verificado: bool = False,
) -> Venta:
    """
    Orquestador comercial y transaccional del Punto de Venta (POS).
    Ejecuta todo el flujo bajo una única transacción atómica (todo o nada):
    1. Valida items y tipos de pago permitidos ('efectivo', 'nequi', 'credito').
    2. Valida pago mínimo en ventas de contado (monto_pagado >= total).
    3. Si es crédito, valida scoring (bloqueo Clase D, abono previo 50% Clase C).
    4. Descuenta inventario mediante ajustar_stock().
    5. Inserta cabecera en ventas y líneas en venta_detalle.
    6. Si es crédito, registra cargo en CxC y snapshot en scoring_historial (auto_commit=False).
    7. Confirma la transacción con conn.commit(), o revierte con conn.rollback() ante cualquier fallo.
    """
    if not items:
        raise ValueError("La venta debe contener al menos un producto o ítem en el detalle.")

    if tipo_pago not in ("efectivo", "nequi", "credito"):
        raise ValueError(
            f"Tipo de pago no válido: '{tipo_pago}'. Debe ser 'efectivo', 'nequi' o 'credito'."
        )

    # Validar y normalizar líneas de venta
    items_procesados = [_normalizar_item(it, conn) for it in items]
    total = round(sum(it["subtotal"] for it in items_procesados), 2)

    # Validación de pago en ventas de contado
    if tipo_pago in ("efectivo", "nequi") and monto_pagado < total:
        raise ValueError(
            f"El monto pagado ({monto_pagado}) es insuficiente para cubrir el total ({total})."
        )

    # Validaciones previas para ventas a crédito
    score_actual = 0.0
    categoria_riesgo = "B"
    if tipo_pago == "credito":
        if not cliente_id:
            raise ValueError("Las ventas a crédito requieren asociar un cliente obligatorio (cliente_id).")

        if monto_pagado < 0:
            raise ValueError(f"El monto pagado no puede ser negativo ({monto_pagado}).")

        if monto_pagado >= total:
            raise ValueError(
                f"El monto pagado ({monto_pagado}) cubre la totalidad de la venta ({total}). "
                "Para pagos completos utilice un tipo de pago de contado (efectivo o nequi)."
            )

        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, saldo_actual, limite_credito, activo FROM clientes WHERE id = ?", (cliente_id,))
        cli_row = cursor.fetchone()
        if not cli_row or not cli_row["activo"]:
            raise ValueError(f"Cliente ID {cliente_id} no encontrado o inactivo.")

        # Evaluación de riesgo crediticio con scoring fresco
        cold_start = scoring_service.evaluar_cold_start(cliente_id, conn)
        if cold_start.get("es_cold_start"):
            score_actual = float(cold_start["score_semilla"])
            decision = cold_start["decision"]
            categoria_riesgo = decision["categoria_riesgo"]
        else:
            score_actual, categoria_riesgo = scoring_service.calcular_score(cliente_id, conn)
            decision = scoring_service.aplicar_matriz_decision(score_actual)

        if decision.get("bloqueado") or categoria_riesgo == "D":
            raise ValueError(
                f"Crédito rechazado (RF-SCR-03): El cliente está en {decision.get('nivel_riesgo', 'Clase D')} "
                f"(Score: {score_actual}). Crédito bloqueado."
            )

        if (decision.get("congelado") or categoria_riesgo == "C") and not cold_start.get("es_cold_start"):
            _validar_credito_clase_c(cliente_id, conn, abono_previo_verificado)

    # Iniciar bloque transaccional atómico
    try:
        cursor = conn.cursor()

        # 1. Descontar inventario para cada ítem catalogado
        for it in items_procesados:
            if it["producto_id"] is not None:
                inventario_service.ajustar_stock(
                    producto_id=it["producto_id"],
                    cantidad=-it["cantidad"],
                    conn=conn,
                )

        # 2. Insertar cabecera de venta
        cursor.execute(
            """
            INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total, monto_pagado)
            VALUES (?, ?, ?, ?, ?)
            """,
            (usuario_id, cliente_id, tipo_pago, total, monto_pagado),
        )
        venta_id = cursor.lastrowid

        # 3. Insertar detalle de venta
        for it in items_procesados:
            cursor.execute(
                """
                INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (venta_id, it["producto_id"], it["descripcion"], it["cantidad"], it["precio_unitario"], it["subtotal"]),
            )

        # 4. Si es crédito: registrar cargo en CxC y snapshot en scoring_historial
        if tipo_pago == "credito":
            monto_a_fiar = round(total - monto_pagado, 2)

            # Registrar cargo sin commit interno por el saldo neto financiado
            cxc_service.registrar_cargo(
                cliente_id=cliente_id,
                monto=monto_a_fiar,
                conn=conn,
                venta_id=venta_id,
                descripcion=f"Venta a crédito #{venta_id}",
                auto_commit=False,
            )

            # Registrar snapshot de scoring sin commit interno
            sw1 = scoring_service.calcular_sw1(cliente_id, conn)
            sw2 = scoring_service.calcular_sw2(cliente_id, conn)
            sw3 = scoring_service.calcular_sw3(cliente_id, conn)
            score_nuevo, cat_nueva = scoring_service.calcular_score(cliente_id, conn)

            scoring_service.registrar_snapshot(
                cliente_id=cliente_id,
                sw1=sw1,
                sw2=sw2,
                sw3=sw3,
                score_ant=int(round(score_actual)),
                score_nuevo=int(round(score_nuevo)),
                cat_ant=categoria_riesgo,
                cat_nueva=cat_nueva,
                motivo=f"Venta a crédito #{venta_id}",
                conn=conn,
                auto_commit=False,
            )

        # 5. Confirmación final de la transacción
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e

    # Consultar fecha_venta asignada por SQLite
    cursor.execute("SELECT fecha_venta FROM ventas WHERE id = ?", (venta_id,))
    v_row = cursor.fetchone()
    fecha_venta = v_row["fecha_venta"] if v_row else None

    return Venta(
        id=venta_id,
        usuario_id=usuario_id,
        cliente_id=cliente_id,
        tipo_pago=tipo_pago,
        total=total,
        monto_pagado=monto_pagado,
        fecha_venta=fecha_venta,
    )
