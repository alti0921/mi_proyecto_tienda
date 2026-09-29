import sqlite3
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple

import services.scoring_service as scoring_service
from services.scoring_service import (
    PLAZO_ESTANDAR_DIAS,
    calcular_v1_1,
    calcular_score,
    aplicar_matriz_decision,
)


def clasificar_banda_mora(dias_mora_efectiva: int) -> Tuple[str, str]:
    """
    Clasifica los días de mora efectiva en las 4 bandas exactas del sistema de scoring (P-Q9 / V1.1 / RF-REP-02):
    - 0 a 3 días: vigente_0_3 (Cartera Vigente)
    - 4 a 6 días: preventiva_4_6 (Alerta Preventiva)
    - 7 a 10 días: congelada_7_10 (Cartera Congelada / Clase C)
    - >10 días: critica_mas_10 (Cartera Crítica / Bloqueada / Clase D)
    """
    if dias_mora_efectiva <= 3:
        return ("vigente_0_3", "Cartera Vigente (0 a 3 días)")
    elif 4 <= dias_mora_efectiva <= 6:
        return ("preventiva_4_6", "Alerta Preventiva (4 a 6 días)")
    elif 7 <= dias_mora_efectiva <= 10:
        return ("congelada_7_10", "Cartera Congelada (7 a 10 días)")
    else:
        return ("critica_mas_10", "Cartera Crítica (> 10 días)")


def obtener_arqueo_diario(
    fecha: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """
    Consolida las transacciones y operaciones de caja de una jornada específica (RF-REP-01).

    Parámetros:
    - fecha: Cadena 'YYYY-MM-DD', o 'now'/'hoy' para el día actual. Si no se pasa o es None, usa hoy.
    - conn: Conexión activa a la base de datos SQLite.

    Retorna un diccionario con:
    - fecha: Fecha consultada ('YYYY-MM-DD').
    - ventas_efectivo: Total cobrado por ventas de contado en efectivo.
    - ventas_nequi: Total cobrado por ventas de contado por transferencia / Nequi.
    - ventas_credito: Total neto financiado otorgado a crédito (total - anticipo).
    - total_ventas_credito: Total bruto pactado en ventas a crédito.
    - anticipos_credito: Total recibido en efectivo como abono inicial en ventas a crédito.
    - abonos_cxc: Total recibido en efectivo por pagos/abonos a cartera en cuentas_por_cobrar.
    - total_efectivo_en_caja: Dinero físico neto que debe existir en caja
      (ventas_efectivo + anticipos_credito + abonos_cxc).
    - total_ingresos_dia: Suma de todos los ingresos reales (efectivo + nequi + anticipos + abonos).
    - movimientos: Lista detallada de movimientos cronológicos del día.
    """
    if conn is None:
        raise ValueError("Se requiere una conexión activa a la base de datos (conn).")

    # Normalizar parámetro de fecha
    if not fecha or fecha.strip().lower() in ("now", "today", "hoy"):
        fecha_str = date.today().strftime("%Y-%m-%d")
    else:
        fecha_str = fecha.strip()[:10]

    cursor = conn.cursor()

    # 1. Consultar ventas del día
    cursor.execute(
        """
        SELECT v.id, v.fecha_venta, v.tipo_pago, v.total, v.monto_pagado, v.cliente_id,
               c.nombre AS cliente_nombre, u.nombre AS usuario_nombre
        FROM ventas v
        LEFT JOIN clientes c ON v.cliente_id = c.id
        LEFT JOIN usuarios u ON v.usuario_id = u.id
        WHERE strftime('%Y-%m-%d', v.fecha_venta) = ?
        ORDER BY v.fecha_venta ASC, v.id ASC
        """,
        (fecha_str,),
    )
    ventas_rows = cursor.fetchall()

    ventas_efectivo = 0.0
    ventas_nequi = 0.0
    ventas_credito_neto = 0.0
    total_ventas_credito_bruto = 0.0
    anticipos_credito = 0.0
    movimientos: List[Dict[str, Any]] = []

    for row in ventas_rows:
        v_id = row["id"]
        v_fecha = row["fecha_venta"]
        v_tipo = row["tipo_pago"]
        v_total = float(row["total"] or 0.0)
        v_pagado = float(row["monto_pagado"] or 0.0)
        c_nombre = row["cliente_nombre"] or "Cliente Mostrador"

        if v_tipo == "efectivo":
            ventas_efectivo += v_total
            movimientos.append({
                "id": f"VENTA-{v_id}",
                "hora": v_fecha,
                "tipo": "Venta Contado (Efectivo)",
                "metodo": "efectivo",
                "monto": round(v_total, 2),
                "efectivo_caja": round(v_total, 2),
                "cliente": c_nombre,
                "descripcion": f"Venta #{v_id} - Contado Efectivo",
            })
        elif v_tipo == "nequi":
            ventas_nequi += v_total
            movimientos.append({
                "id": f"VENTA-{v_id}",
                "hora": v_fecha,
                "tipo": "Venta Contado (Nequi/Transf.)",
                "metodo": "nequi",
                "monto": round(v_total, 2),
                "efectivo_caja": 0.0,
                "cliente": c_nombre,
                "descripcion": f"Venta #{v_id} - Nequi / Transferencia",
            })
        elif v_tipo == "credito":
            neto_financiado = round(v_total - v_pagado, 2)
            total_ventas_credito_bruto += v_total
            ventas_credito_neto += neto_financiado
            anticipos_credito += v_pagado

            desc = f"Venta #{v_id} a Crédito (Total: ${v_total:,.2f}"
            if v_pagado > 0:
                desc += f", Anticipo Efectivo: ${v_pagado:,.2f}, Fiado Neto: ${neto_financiado:,.2f})"
            else:
                desc += f", Fiado Total: ${neto_financiado:,.2f})"

            movimientos.append({
                "id": f"VENTA-{v_id}",
                "hora": v_fecha,
                "tipo": "Venta a Crédito (Fiado)",
                "metodo": "credito",
                "monto": round(v_total, 2),
                "efectivo_caja": round(v_pagado, 2),  # Solo el anticipo entra a caja física
                "cliente": c_nombre,
                "descripcion": desc,
            })

    # 2. Consultar abonos recibidos en CxC durante el día
    cursor.execute(
        """
        SELECT cxc.id, cxc.fecha_movimiento, cxc.monto, cxc.saldo_resultante,
               cxc.descripcion, cxc.cliente_id, c.nombre AS cliente_nombre
        FROM cuentas_por_cobrar cxc
        LEFT JOIN clientes c ON cxc.cliente_id = c.id
        WHERE cxc.tipo_movimiento = 'abono'
          AND strftime('%Y-%m-%d', cxc.fecha_movimiento) = ?
        ORDER BY cxc.fecha_movimiento ASC, cxc.id ASC
        """,
        (fecha_str,),
    )
    abonos_rows = cursor.fetchall()

    abonos_cxc = 0.0
    for row in abonos_rows:
        a_id = row["id"]
        a_fecha = row["fecha_movimiento"]
        a_monto = float(row["monto"] or 0.0)
        c_nombre = row["cliente_nombre"] or f"Cliente ID {row['cliente_id']}"
        abonos_cxc += a_monto

        movimientos.append({
            "id": f"ABONO-{a_id}",
            "hora": a_fecha,
            "tipo": "Abono Cartera CxC",
            "metodo": "efectivo",
            "monto": round(a_monto, 2),
            "efectivo_caja": round(a_monto, 2),
            "cliente": c_nombre,
            "descripcion": row["descripcion"] or f"Abono a cartera de {c_nombre}",
        })

    # Ordenar cronológicamente los movimientos combinados
    movimientos.sort(key=lambda m: (m.get("hora") or "", m.get("id") or ""))

    # Totales consolidados
    ventas_efectivo = round(ventas_efectivo, 2)
    ventas_nequi = round(ventas_nequi, 2)
    ventas_credito_neto = round(ventas_credito_neto, 2)
    total_ventas_credito_bruto = round(total_ventas_credito_bruto, 2)
    anticipos_credito = round(anticipos_credito, 2)
    abonos_cxc = round(abonos_cxc, 2)

    total_efectivo_en_caja = round(ventas_efectivo + anticipos_credito + abonos_cxc, 2)
    total_ingresos_dia = round(total_efectivo_en_caja + ventas_nequi, 2)

    return {
        "fecha": fecha_str,
        "ventas_efectivo": ventas_efectivo,
        "ventas_nequi": ventas_nequi,
        "ventas_credito": ventas_credito_neto,
        "total_ventas_credito": total_ventas_credito_bruto,
        "anticipos_credito": anticipos_credito,
        "abonos_cxc": abonos_cxc,
        "total_efectivo_en_caja": total_efectivo_en_caja,
        "total_ingresos_dia": total_ingresos_dia,
        "total_transacciones": len(movimientos),
        "movimientos": movimientos,
    }


def obtener_consolidado_cartera(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Consolida el estado global de la cartera y clasifica a todos los clientes deudores (RF-REP-02).
    Reutiliza directamente las constantes y algoritmos de services/scoring_service.py para
    garantizar consistencia analítica absoluta.

    Clasificación según mora efectiva (P-Q9 / V1.1):
    - vigente_0_3: 0 a 3 días de mora efectiva.
    - preventiva_4_6: 4 a 6 días de mora efectiva.
    - congelada_7_10: 7 a 10 días de mora efectiva (Clase C).
    - critica_mas_10: más de 10 días de mora efectiva (Clase D).

    Retorna un diccionario con:
    - total_cartera_por_cobrar: Suma del saldo deudor de todos los clientes.
    - total_deudores: Cantidad de clientes con saldo > 0.
    - resumen_por_banda: Monto total adeudado en cada banda de riesgo.
    - conteo_por_banda: Cantidad de clientes en cada banda.
    - deudores: Lista detallada de clientes deudores.
    """
    cursor = conn.cursor()

    # Consultar todos los clientes activos con saldo pendiente > 0
    cursor.execute(
        """
        SELECT id, nombre, telefono, direccion, nivel_vinculo, limite_credito, saldo_actual, activo
        FROM clientes
        WHERE activo = 1 AND saldo_actual > 0
        ORDER BY saldo_actual DESC, nombre ASC
        """
    )
    clientes_deudores = cursor.fetchall()

    resumen_por_banda = {
        "vigente_0_3": 0.0,
        "preventiva_4_6": 0.0,
        "congelada_7_10": 0.0,
        "critica_mas_10": 0.0,
    }
    conteo_por_banda = {
        "vigente_0_3": 0,
        "preventiva_4_6": 0,
        "congelada_7_10": 0,
        "critica_mas_10": 0,
    }

    deudores: List[Dict[str, Any]] = []

    for cli in clientes_deudores:
        c_id = cli["id"]
        c_nombre = cli["nombre"]
        c_tel = cli["telefono"]
        c_dir = cli["direccion"]
        c_limite = float(cli["limite_credito"] or 0.0)
        c_saldo = float(cli["saldo_actual"] or 0.0)

        # 1. Calcular días transcurridos desde el cargo pendiente más antiguo (idéntico a scoring_service)
        cursor.execute(
            """
            SELECT fecha_movimiento,
                   CAST(julianday('now') - julianday(fecha_movimiento) AS INTEGER) AS dias_transcurridos
            FROM cuentas_por_cobrar
            WHERE cliente_id = ? AND tipo_movimiento = 'cargo'
            ORDER BY fecha_movimiento ASC
            LIMIT 1
            """,
            (c_id,),
        )
        cxc_row = cursor.fetchone()
        dias_transcurridos = (
            cxc_row["dias_transcurridos"]
            if (cxc_row and cxc_row["dias_transcurridos"] is not None)
            else 0
        )
        if dias_transcurridos < 0:
            dias_transcurridos = 0

        # 2. Descontar plazo pactado (PLAZO_ESTANDAR_DIAS = 8) para obtener mora efectiva
        dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS)

        # 3. Evaluar scoring y matriz de decisión en vivo
        score_cliente, cat_riesgo = scoring_service.calcular_score(c_id, conn)

        # 4. Clasificar banda de mora según los umbrales de P-Q9 / V1.1
        banda, etiqueta_banda = clasificar_banda_mora(dias_mora_efectiva)

        # 5. Acumular en resúmenes
        resumen_por_banda[banda] += c_saldo
        conteo_por_banda[banda] += 1

        cupo_disponible = max(0.0, round(c_limite - c_saldo, 2))

        deudores.append({
            "cliente_id": c_id,
            "nombre": c_nombre,
            "telefono": c_tel,
            "direccion": c_dir,
            "limite_credito": round(c_limite, 2),
            "saldo_actual": round(c_saldo, 2),
            "cupo_disponible": cupo_disponible,
            "dias_transcurridos": dias_transcurridos,
            "dias_mora_efectiva": dias_mora_efectiva,
            "score": score_cliente,
            "clase_riesgo": cat_riesgo,
            "banda": banda,
            "estado_banda": etiqueta_banda,
        })

    total_cartera = round(sum(d["saldo_actual"] for d in deudores), 2)

    return {
        "total_cartera_por_cobrar": total_cartera,
        "total_deudores": len(deudores),
        "resumen_por_banda": {k: round(v, 2) for k, v in resumen_por_banda.items()},
        "conteo_por_banda": conteo_por_banda,
        "deudores": deudores,
    }
