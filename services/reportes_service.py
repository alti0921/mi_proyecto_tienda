import os
import sqlite3
import tempfile
from datetime import date, datetime
from typing import Dict, Any, List, Optional, Tuple

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

import services.scoring_service as scoring_service
from services.scoring_service import clasificar_banda_mora
from services.fechas import a_hora_local
from db.rutas import carpeta_comprobantes


def _calcular_ganancia(
    conn: sqlite3.Connection, formato: str, valor: str
) -> Dict[str, Any]:
    """
    Calcula la rentabilidad real de las ventas del periodo ('%Y-%m-%d', '%Y-%m', '%Y').
    Reglas:
    - Ganancia de una línea = subtotal - (cantidad * costo_unitario), solo si costo_unitario > 0.
    - Líneas con costo_unitario NULL o <= 0 no entran en la ganancia y se suman a 'ventas_sin_costo'
      con su conteo en 'lineas_sin_costo'.
    - Ventas de contado (efectivo, nequi) -> ganancia_en_mano.
    - Ventas a crédito -> ganancia_por_cobrar.
    - ganancia_total = ganancia_en_mano + ganancia_por_cobrar.
    - Fechas en hora local con strftime(..., 'localtime').
    """
    if formato not in ("%Y-%m-%d", "%Y-%m", "%Y"):
        raise ValueError(f"Formato de fecha no soportado: {formato}")

    cursor = conn.cursor()

    # 1. Total vendido en el periodo (suma de ventas.total)
    cursor.execute(
        f"""
        SELECT COALESCE(SUM(total), 0.0) AS total_vendido
        FROM ventas
        WHERE strftime('{formato}', fecha_venta, 'localtime') = ?
        """,
        (valor,),
    )
    row_tot = cursor.fetchone()
    total_vendido = float(row_tot["total_vendido"] if row_tot else 0.0)

    # 2. Desglose de líneas de venta del periodo
    cursor.execute(
        f"""
        SELECT vd.cantidad, vd.subtotal, vd.costo_unitario, v.tipo_pago
        FROM venta_detalle vd
        JOIN ventas v ON vd.venta_id = v.id
        WHERE strftime('{formato}', v.fecha_venta, 'localtime') = ?
        """,
        (valor,),
    )
    lineas = cursor.fetchall()

    costo_ventas = 0.0
    ganancia_en_mano = 0.0
    ganancia_por_cobrar = 0.0
    ventas_sin_costo = 0.0
    lineas_sin_costo = 0

    for l in lineas:
        cant = float(l["cantidad"] or 0.0)
        sub = float(l["subtotal"] or 0.0)
        costo_u = l["costo_unitario"]
        tipo = l["tipo_pago"]

        if costo_u is not None and float(costo_u) > 0:
            costo_linea = round(cant * float(costo_u), 2)
            ganancia_linea = round(sub - costo_linea, 2)
            costo_ventas += costo_linea
            if tipo in ("efectivo", "nequi"):
                ganancia_en_mano += ganancia_linea
            elif tipo == "credito":
                ganancia_por_cobrar += ganancia_linea
        else:
            ventas_sin_costo += sub
            lineas_sin_costo += 1

    ganancia_en_mano = round(ganancia_en_mano, 2)
    ganancia_por_cobrar = round(ganancia_por_cobrar, 2)
    ganancia_total = round(ganancia_en_mano + ganancia_por_cobrar, 2)

    return {
        "total_vendido": round(total_vendido, 2),
        "costo_ventas": round(costo_ventas, 2),
        "ganancia_en_mano": ganancia_en_mano,
        "ganancia_por_cobrar": ganancia_por_cobrar,
        "ganancia_total": ganancia_total,
        "ventas_sin_costo": round(ventas_sin_costo, 2),
        "lineas_sin_costo": int(lineas_sin_costo),
    }


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
        WHERE strftime('%Y-%m-%d', v.fecha_venta, 'localtime') = ?
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
                "hora": a_hora_local(v_fecha),
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
                "hora": a_hora_local(v_fecha),
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
                "hora": a_hora_local(v_fecha),
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
          AND strftime('%Y-%m-%d', cxc.fecha_movimiento, 'localtime') = ?
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
            "hora": a_hora_local(a_fecha),
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

    ganancia_dia = _calcular_ganancia(conn, "%Y-%m-%d", fecha_str)

    res = {
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
    res.update(ganancia_dia)
    return res


def obtener_resumen_periodo(
    anio: int,
    mes: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """
    Consolida las métricas operativas de caja y ganancia para un periodo mensual o anual.

    Parámetros:
    - anio: Año del periodo (entero entre 2000 y 2100).
    - mes: Mes del periodo (1 a 12), o None para consolidar el año completo.
    - conn: Conexión activa a SQLite (obligatoria).

    Retorna un diccionario con:
    - periodo: 'YYYY-MM' o 'YYYY'.
    - ventas_efectivo, ventas_nequi, ventas_credito, total_ventas_credito, anticipos_credito,
      abonos_cxc, total_efectivo_en_caja, total_ingresos, numero_ventas.
    - total_vendido, costo_ventas, ganancia_en_mano, ganancia_por_cobrar, ganancia_total,
      ventas_sin_costo, lineas_sin_costo.
    - desglose: lista ordenada de subperiodos con movimientos (por día si mes != None, por mes si mes == None).
    """
    if conn is None:
        raise ValueError("Se requiere una conexión activa a la base de datos (conn).")

    if not isinstance(anio, int) or isinstance(anio, bool) or not (2000 <= anio <= 2100):
        raise ValueError(f"El año debe ser un número entero entre 2000 y 2100 (recibido: {anio}).")

    if mes is not None:
        if not isinstance(mes, int) or isinstance(mes, bool) or not (1 <= mes <= 12):
            raise ValueError(f"El mes debe ser un número entero entre 1 y 12 (recibido: {mes}).")
        periodo_str = f"{anio:04d}-{mes:02d}"
        formato_sql = "%Y-%m"
        sub_formato = "%Y-%m-%d"
    else:
        periodo_str = f"{anio:04d}"
        formato_sql = "%Y"
        sub_formato = "%Y-%m"

    cursor = conn.cursor()

    # 1. Ventas del periodo completo
    cursor.execute(
        f"""
        SELECT id, fecha_venta, tipo_pago, total, monto_pagado
        FROM ventas
        WHERE strftime('{formato_sql}', fecha_venta, 'localtime') = ?
        ORDER BY fecha_venta ASC, id ASC
        """,
        (periodo_str,),
    )
    ventas_rows = cursor.fetchall()

    ventas_efectivo = 0.0
    ventas_nequi = 0.0
    ventas_credito_neto = 0.0
    total_ventas_credito_bruto = 0.0
    anticipos_credito = 0.0

    for r in ventas_rows:
        v_tipo = r["tipo_pago"]
        v_total = float(r["total"] or 0.0)
        v_pagado = float(r["monto_pagado"] or 0.0)

        if v_tipo == "efectivo":
            ventas_efectivo += v_total
        elif v_tipo == "nequi":
            ventas_nequi += v_total
        elif v_tipo == "credito":
            neto_financiado = round(v_total - v_pagado, 2)
            total_ventas_credito_bruto += v_total
            ventas_credito_neto += neto_financiado
            anticipos_credito += v_pagado

    # 2. Abonos recibidos en CxC durante el periodo
    cursor.execute(
        f"""
        SELECT id, fecha_movimiento, monto
        FROM cuentas_por_cobrar
        WHERE tipo_movimiento = 'abono'
          AND strftime('{formato_sql}', fecha_movimiento, 'localtime') = ?
        ORDER BY fecha_movimiento ASC, id ASC
        """,
        (periodo_str,),
    )
    abonos_rows = cursor.fetchall()

    abonos_cxc = sum(float(r["monto"] or 0.0) for r in abonos_rows)

    ventas_efectivo = round(ventas_efectivo, 2)
    ventas_nequi = round(ventas_nequi, 2)
    ventas_credito_neto = round(ventas_credito_neto, 2)
    total_ventas_credito_bruto = round(total_ventas_credito_bruto, 2)
    anticipos_credito = round(anticipos_credito, 2)
    abonos_cxc = round(abonos_cxc, 2)

    total_efectivo_en_caja = round(ventas_efectivo + anticipos_credito + abonos_cxc, 2)
    total_ingresos = round(total_efectivo_en_caja + ventas_nequi, 2)
    numero_ventas = len(ventas_rows)

    ganancia_periodo = _calcular_ganancia(conn, formato_sql, periodo_str)

    # 3. Desglose ordenado por subperiodo con movimientos
    cursor.execute(
        f"""
        SELECT DISTINCT strftime('{sub_formato}', fecha_venta, 'localtime') AS p
        FROM ventas
        WHERE strftime('{formato_sql}', fecha_venta, 'localtime') = ?
        """,
        (periodo_str,),
    )
    p_ventas = {row[0] for row in cursor.fetchall() if row[0]}

    cursor.execute(
        f"""
        SELECT DISTINCT strftime('{sub_formato}', fecha_movimiento, 'localtime') AS p
        FROM cuentas_por_cobrar
        WHERE tipo_movimiento = 'abono'
          AND strftime('{formato_sql}', fecha_movimiento, 'localtime') = ?
        """,
        (periodo_str,),
    )
    p_abonos = {row[0] for row in cursor.fetchall() if row[0]}

    sub_periodos = sorted(p_ventas | p_abonos)

    desglose: List[Dict[str, Any]] = []
    for sub_p in sub_periodos:
        cursor.execute(
            f"""
            SELECT tipo_pago, total, monto_pagado
            FROM ventas
            WHERE strftime('{sub_formato}', fecha_venta, 'localtime') = ?
            """,
            (sub_p,),
        )
        sub_v_rows = cursor.fetchall()

        sub_v_efectivo = 0.0
        sub_v_nequi = 0.0
        sub_anticipos = 0.0
        for sv in sub_v_rows:
            sv_tipo = sv["tipo_pago"]
            sv_total = float(sv["total"] or 0.0)
            sv_pagado = float(sv["monto_pagado"] or 0.0)
            if sv_tipo == "efectivo":
                sub_v_efectivo += sv_total
            elif sv_tipo == "nequi":
                sub_v_nequi += sv_total
            elif sv_tipo == "credito":
                sub_anticipos += sv_pagado

        cursor.execute(
            f"""
            SELECT COALESCE(SUM(monto), 0.0) AS total_abonos
            FROM cuentas_por_cobrar
            WHERE tipo_movimiento = 'abono'
              AND strftime('{sub_formato}', fecha_movimiento, 'localtime') = ?
            """,
            (sub_p,),
        )
        sub_abonos_row = cursor.fetchone()
        sub_abonos = float(sub_abonos_row["total_abonos"] if sub_abonos_row else 0.0)

        sub_total_efectivo_en_caja = round(sub_v_efectivo + sub_anticipos + sub_abonos, 2)
        sub_total_ingresos = round(sub_total_efectivo_en_caja + sub_v_nequi, 2)

        gan_sub = _calcular_ganancia(conn, sub_formato, sub_p)

        desglose.append({
            "periodo": sub_p,
            "total_vendido": gan_sub["total_vendido"],
            "total_ingresos": sub_total_ingresos,
            "ganancia_en_mano": gan_sub["ganancia_en_mano"],
            "ganancia_por_cobrar": gan_sub["ganancia_por_cobrar"],
            "ganancia_total": gan_sub["ganancia_total"],
        })

    return {
        "periodo": periodo_str,
        "ventas_efectivo": ventas_efectivo,
        "ventas_nequi": ventas_nequi,
        "ventas_credito": ventas_credito_neto,
        "total_ventas_credito": total_ventas_credito_bruto,
        "anticipos_credito": anticipos_credito,
        "abonos_cxc": abonos_cxc,
        "total_efectivo_en_caja": total_efectivo_en_caja,
        "total_ingresos": total_ingresos,
        "numero_ventas": numero_ventas,
        "total_vendido": ganancia_periodo["total_vendido"],
        "costo_ventas": ganancia_periodo["costo_ventas"],
        "ganancia_en_mano": ganancia_periodo["ganancia_en_mano"],
        "ganancia_por_cobrar": ganancia_periodo["ganancia_por_cobrar"],
        "ganancia_total": ganancia_periodo["ganancia_total"],
        "ventas_sin_costo": ganancia_periodo["ventas_sin_costo"],
        "lineas_sin_costo": ganancia_periodo["lineas_sin_costo"],
        "desglose": desglose,
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

        # 1. Evaluar scoring integral con imputación FIFO y reglas de veto en vivo
        ev = scoring_service.evaluar_cliente(c_id, conn)
        dias_transcurridos = ev["dias_transcurridos"]
        dias_mora_efectiva = ev["dias_mora_efectiva"]
        score_cliente = ev["score"]
        cat_riesgo = ev["clase_final"]
        clase_puntaje = ev["clase_puntaje"]
        veto_aplicado = ev["veto_aplicado"]

        # 2. Clasificar banda de mora según los umbrales de P-Q9 / V1.1
        banda, etiqueta_banda = clasificar_banda_mora(dias_mora_efectiva)

        # 3. Acumular en resúmenes
        resumen_por_banda[banda] += c_saldo
        conteo_por_banda[banda] += 1

        cupo_disponible = max(0.0, round(c_limite - c_saldo, 2))

        venc = scoring_service.obtener_vencimiento(c_id, conn)
        fecha_vencimiento = venc["fecha_vencimiento"] if venc else None
        dias_para_vencer = venc["dias_para_vencer"] if venc else None

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
            "clase_puntaje": clase_puntaje,
            "veto_aplicado": veto_aplicado,
            "banda": banda,
            "estado_banda": etiqueta_banda,
            "fecha_vencimiento": fecha_vencimiento,
            "dias_para_vencer": dias_para_vencer,
        })

    total_cartera = round(sum(d["saldo_actual"] for d in deudores), 2)

    return {
        "total_cartera_por_cobrar": total_cartera,
        "total_deudores": len(deudores),
        "resumen_por_banda": {k: round(v, 2) for k, v in resumen_por_banda.items()},
        "conteo_por_banda": conteo_por_banda,
        "deudores": deudores,
    }


ENCABEZADO_COMPROBANTE = "Mi Tienda — Sistema POS & Scoring"


def _lineas_pie_comprobante(tipo: str) -> list[str]:
    """
    Retorna las líneas de pie de página según el tipo de movimiento (cargo o abono).
    """
    if tipo == "abono":
        return [
            "¡Gracias por su pago oportuno y su confianza!",
            "Conserve este soporte para cualquier aclaración.",
        ]
    return [
        "Conserve este soporte para cualquier aclaración.",
    ]


def _partir_texto(texto: str, fuente: str, tamano: float, ancho_max: float) -> list[str]:
    """
    Parte un texto en múltiples líneas según el ancho máximo permitido,
    sin truncar con elipsis ni perder palabras.
    """
    if not texto:
        return []
    return simpleSplit(str(texto), fuente, tamano, ancho_max)


def generar_comprobante_pdf(
    movimiento_id: int,
    conn: sqlite3.Connection,
    ruta_salida: Optional[str] = None,
) -> str:
    """
    RF-CXC-04. Genera el comprobante en PDF de un movimiento (cargo o abono) de
    cuentas_por_cobrar en formato tirilla térmica 80mm.
    Reconstruye:
    - saldo_anterior = saldo_resultante + monto (para abonos) o saldo_resultante - monto (para cargos)
      directamente del registro inmutable.
    - cajero: obtenido de usuarios.nombre vía movimiento.usuario_id
      (o 'No registrado' si es NULL).
    Si ruta_salida es None, escribe en un archivo temporal (.pdf) y retorna la ruta absoluta.
    """
    if conn is None:
        raise ValueError("Se requiere una conexión activa a la base de datos (conn).")

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            cxc.id,
            cxc.cliente_id,
            cxc.venta_id,
            cxc.usuario_id,
            cxc.tipo_movimiento,
            cxc.monto,
            cxc.saldo_resultante,
            cxc.descripcion,
            cxc.fecha_movimiento,
            cli.nombre AS cliente_nombre,
            cli.telefono AS cliente_telefono,
            u.nombre AS cajero_nombre
        FROM cuentas_por_cobrar cxc
        JOIN clientes cli ON cxc.cliente_id = cli.id
        LEFT JOIN usuarios u ON cxc.usuario_id = u.id
        WHERE cxc.id = ?
        """,
        (movimiento_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Movimiento de cuentas_por_cobrar con ID {movimiento_id} no encontrado.")

    tipo = row["tipo_movimiento"]
    monto = float(row["monto"])
    saldo_resultante = float(row["saldo_resultante"])

    # Reconstrucción inmutable del saldo anterior
    if tipo == "abono":
        saldo_anterior = round(saldo_resultante + monto, 2)
        concepto_titulo = ">>> ABONO A CARTERA <<<"
        label_monto = "Valor Abonado:"
    else:
        saldo_anterior = round(saldo_resultante - monto, 2)
        concepto_titulo = ">>> CARGO POR VENTA A CRÉDITO <<<"
        label_monto = "Valor Cargado:"

    cajero = row["cajero_nombre"] if row["cajero_nombre"] else "No registrado"
    cliente = row["cliente_nombre"] or "Cliente General"
    telefono = row["cliente_telefono"] or "No registrado"
    descripcion = row["descripcion"] or ("Abono de cartera" if tipo == "abono" else "Venta a crédito")
    fecha_mov = a_hora_local(row["fecha_movimiento"]) if row["fecha_movimiento"] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Ruta de destino
    if ruta_salida is None:
        directorio = carpeta_comprobantes()
        ruta_salida = os.path.join(directorio, f"comprobante_cxc_{movimiento_id:06d}.pdf")
    else:
        ruta_salida = os.path.abspath(ruta_salida)

    # Dimensiones térmicas: 80 mm de ancho (~226.77 pt)
    w = 80 * mm
    x_left = 6 * mm
    x_right = w - 6 * mm
    x_center = w / 2.0
    ancho_imprimible = x_right - x_left

    # Partir textos sin truncar (RF-CXC-04)
    ancho_datos = ancho_imprimible - 18 * mm
    cajero_lineas = _partir_texto(cajero, "Helvetica", 8, ancho_datos) or ["No registrado"]
    cliente_lineas = _partir_texto(cliente, "Helvetica", 8, ancho_datos) or ["Cliente General"]
    tel_lineas = _partir_texto(str(telefono), "Helvetica", 8, ancho_datos) or ["No registrado"]
    desc_lineas = _partir_texto(descripcion, "Helvetica-Oblique", 7.5, ancho_imprimible) or [descripcion]
    lineas_pie = _lineas_pie_comprobante(tipo)

    # Cálculo dinámico del alto de página (mínimo 160 mm)
    margen_sup = 8 * mm
    margen_inf = 8 * mm
    lineas_var_drop = (
        len(cajero_lineas) * 3.5 +
        len(cliente_lineas) * 3.5 +
        len(tel_lineas) * 3.5 +
        len(desc_lineas) * 3.2 +
        len(lineas_pie) * 3.5 +
        3.0
    ) * mm

    alto_calculado = 66 * mm + lineas_var_drop + margen_sup + margen_inf
    h = max(160 * mm, alto_calculado)

    c = canvas.Canvas(ruta_salida, pagesize=(w, h))
    y = h - margen_sup

    # 1. Encabezado del comprobante (una sola línea)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(x_center, y, ENCABEZADO_COMPROBANTE)
    y -= 4 * mm

    # Separador punteado
    c.setDash(2, 2)
    c.setLineWidth(0.5)
    c.line(x_left, y, x_right, y)
    y -= 4 * mm

    # 2. Folio y Fecha
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x_center, y, f"#MOV-{movimiento_id:06d}")
    y -= 3.5 * mm
    c.setFont("Helvetica", 8)
    c.drawCentredString(x_center, y, str(fecha_mov))
    y -= 3 * mm

    # Separador
    c.line(x_left, y, x_right, y)
    y -= 4 * mm

    # 3. Datos del cajero y cliente (sin truncar)
    c.setFont("Helvetica", 8)
    c.drawString(x_left, y, "Cajero:")
    c.drawRightString(x_right, y, cajero_lineas[0])
    y -= 3.5 * mm
    for l in cajero_lineas[1:]:
        c.drawRightString(x_right, y, l)
        y -= 3.5 * mm
    y -= 0.5 * mm

    c.drawString(x_left, y, "Cliente:")
    c.drawRightString(x_right, y, cliente_lineas[0])
    y -= 3.5 * mm
    for l in cliente_lineas[1:]:
        c.drawRightString(x_right, y, l)
        y -= 3.5 * mm
    y -= 0.5 * mm

    c.drawString(x_left, y, "Teléfono:")
    c.drawRightString(x_right, y, tel_lineas[0])
    y -= 3.5 * mm
    for l in tel_lineas[1:]:
        c.drawRightString(x_right, y, l)
        y -= 3.5 * mm

    # Separador
    c.line(x_left, y, x_right, y)
    y -= 4 * mm

    # 4. Concepto y Tipo de Movimiento (sin truncar descripción)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString(x_center, y, concepto_titulo)
    y -= 3.5 * mm
    c.setFont("Helvetica-Oblique", 7.5)
    for l in desc_lineas:
        c.drawCentredString(x_center, y, l)
        y -= 3.2 * mm

    # Separador
    c.line(x_left, y, x_right, y)
    y -= 4.5 * mm

    # 5. Detalle Financiero Reconstruido
    c.setFont("Helvetica", 8)
    c.drawString(x_left, y, "Saldo Anterior:")
    c.drawRightString(x_right, y, f"$ {saldo_anterior:,.2f} COP")
    y -= 4 * mm

    c.drawString(x_left, y, label_monto)
    c.drawRightString(x_right, y, f"$ {monto:,.2f} COP")
    y -= 3 * mm

    c.line(x_left, y, x_right, y)
    y -= 4.5 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(x_left, y, "NUEVO SALDO:")
    c.drawRightString(x_right, y, f"$ {saldo_resultante:,.2f} COP")
    y -= 3 * mm

    # Separador
    c.line(x_left, y, x_right, y)
    y -= 5 * mm

    # 6. Pie de página dinámico por tipo
    for i, l in enumerate(lineas_pie):
        if i == 0 and tipo == "abono":
            c.setFont("Helvetica-Oblique", 7)
        else:
            c.setFont("Helvetica", 6.5)
        pie_sublineas = _partir_texto(l, "Helvetica", 6.5, ancho_imprimible) or [l]
        for subl in pie_sublineas:
            c.drawCentredString(x_center, y, subl)
            y -= 3.5 * mm

    c.save()
    return ruta_salida

