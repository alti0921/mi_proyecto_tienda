import sqlite3
from typing import Optional, Tuple, Dict, Any
from models.scoring import ScoringHistorial

# Constante global de negocio: Plazo estándar / Período de gracia en días
PLAZO_ESTANDAR_DIAS: int = 8

def calcular_sw1(cliente_id: int, conn: sqlite3.Connection) -> float:
    """
    Calcula SW1: Comportamiento de Pago Histórico (Peso W1 = 40%).
    SW1 = 0.60 * V1.1 (días de mora efectiva tras plazo de gracia de 8 días) + 0.40 * V1.2 (antigüedad de saldo).
    Devuelve un valor flotante en la escala 0 - 100.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        return 0.0
    
    saldo_actual = float(row["saldo_actual"] or 0.0)
    
    if saldo_actual <= 0:
        # Sin saldo pendiente / Al día
        v1_1 = 100.0
        v1_2 = 100.0
    else:
        # Obtener los días transcurridos desde el cargo pendiente más antiguo sin abonar totalmente
        cursor.execute("""
            SELECT fecha_movimiento,
                   CAST(julianday('now') - julianday(fecha_movimiento) AS INTEGER) AS dias_transcurridos
            FROM cuentas_por_cobrar
            WHERE cliente_id = ? AND tipo_movimiento = 'cargo'
            ORDER BY fecha_movimiento ASC
            LIMIT 1
        """, (cliente_id,))
        cxc_row = cursor.fetchone()
        
        dias_transcurridos = cxc_row["dias_transcurridos"] if (cxc_row and cxc_row["dias_transcurridos"] is not None) else 0
        if dias_transcurridos < 0:
            dias_transcurridos = 0

        # Cálculo de mora efectiva descontando el plazo de gracia (8 días)
        dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS)

        # Evaluación V1.1: 4 Niveles de Mora Efectiva según P-Q9
        if 0 <= dias_mora_efectiva <= 3:
            v1_1 = 100.0  # 0 - 3 días (Al día / mora mínima)
        elif 4 <= dias_mora_efectiva <= 6:
            v1_1 = 70.0   # 4 - 6 días (Alerta preventiva)
        elif 7 <= dias_mora_efectiva <= 10:
            v1_1 = 30.0   # 7 - 10 días: Umbral de congelamiento según P-Q9 (66.7% de tenderos)
        else:
            v1_1 = 0.0    # Mayor a 10 días: Mora crítica

        # Evaluación V1.2: Antigüedad de Saldo Pendiente
        if dias_transcurridos < 30:
            v1_2 = 100.0
        elif 30 <= dias_transcurridos <= 59:
            v1_2 = 60.0
        elif 60 <= dias_transcurridos <= 90:
            v1_2 = 20.0
        else:
            v1_2 = 0.0

    sw1 = 0.60 * v1_1 + 0.40 * v1_2
    return round(sw1, 2)


def calcular_sw2(cliente_id: int, conn: sqlite3.Connection) -> float:
    """
    Calcula SW2: Frecuencia y Volumetría de Compra (Peso W2 = 35%).
    SW2 = 0.50 * V2.1 (frecuencia mensual) + 0.50 * V2.2 (categorías de producto).
    Devuelve un valor flotante en la escala 0 - 100.
    """
    cursor = conn.cursor()
    
    # V2.1: Frecuencia de compras en los últimos 30 días
    cursor.execute("""
        SELECT COUNT(*) AS total_ventas
        FROM ventas
        WHERE cliente_id = ?
          AND fecha_venta >= datetime('now', '-30 days')
    """, (cliente_id,))
    freq_row = cursor.fetchone()
    total_ventas = freq_row["total_ventas"] if freq_row else 0
    
    if total_ventas >= 12:
        v2_1 = 100.0
    elif 6 <= total_ventas <= 11:
        v2_1 = 75.0
    elif 2 <= total_ventas <= 5:
        v2_1 = 40.0
    elif total_ventas == 1:
        v2_1 = 10.0
    else:
        v2_1 = 0.0

    # V2.2: Predominancia de tipos de producto adquiridos
    cursor.execute("""
        SELECT p.categoria, COUNT(*) AS cantidad
        FROM ventas v
        JOIN venta_detalle vd ON v.id = vd.venta_id
        JOIN productos p ON vd.producto_id = p.id
        WHERE v.cliente_id = ?
        GROUP BY p.categoria
    """, (cliente_id,))
    cat_rows = cursor.fetchall()
    
    if not cat_rows:
        v2_2 = 60.0  # Valor base neutral si no hay detalle aún
    else:
        conteo = {row["categoria"]: row["cantidad"] for row in cat_rows}
        total_items = sum(conteo.values())
        basica = conteo.get("canasta_basica", 0)
        suntuario = conteo.get("consumo_suntuario", 0)
        
        if (basica / total_items) >= 0.60:
            v2_2 = 100.0
        elif (suntuario / total_items) >= 0.50:
            v2_2 = 20.0
        else:
            v2_2 = 60.0

    sw2 = 0.50 * v2_1 + 0.50 * v2_2
    return round(sw2, 2)


def calcular_sw3(cliente_id: int, conn: sqlite3.Connection) -> float:
    """
    Calcula SW3: Confianza Relacional / Nivel de Vínculo (Peso W3 = 25%).
    Mapeo directo de clientes.nivel_vinculo:
      - 'registro_completo': 100 pts
      - 'conocido_referido': 60 pts
      - 'solo_apodo': 20 pts
    """
    cursor = conn.cursor()
    cursor.execute("SELECT nivel_vinculo FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        return 20.0
    
    vinculo = (row["nivel_vinculo"] or "").lower()
    if vinculo == "registro_completo":
        return 100.0
    elif vinculo == "conocido_referido":
        return 60.0
    else:
        return 20.0


def aplicar_matriz_decision(score: float) -> Dict[str, Any]:
    """
    Traduce la puntuación S (0 - 100 pts) a las Salidas y Decisiones de la Matriz Calibrada:
      - 80.0 a 100.0 -> Clase A (Riesgo Bajo / Incremento cupo +20%)
      - 60.0 a 79.9  -> Clase B (Riesgo Medio / Mantener cupo)
      - 40.0 a 59.9  -> Clase C (Riesgo Alto / Congelamiento, abono previo 50%)
      - 0.0 a 39.9   -> Clase D (Riesgo Crítico / Bloqueo automático)
    """
    score_redondeado = round(score, 2)
    
    if score_redondeado >= 80.0:
        return {
            "categoria_riesgo": "A",
            "nivel_riesgo": "Riesgo Bajo (Clase A)",
            "aprobado": True,
            "accion": "Crédito aprobado. Sugerencia de incremento de cupo de hasta un 20%.",
            "sugerencia_cupo": "+20%",
            "factor_cupo": 1.20,
            "congelado": False,
            "bloqueado": False,
            "abono_minimo_pct": 0.0
        }
    elif 60.0 <= score_redondeado < 80.0:
        return {
            "categoria_riesgo": "B",
            "nivel_riesgo": "Riesgo Medio (Clase B)",
            "aprobado": True,
            "accion": "Crédito aprobado. Mantener cupo habitual a plazo estándar (8 a 15 días).",
            "sugerencia_cupo": "Mantener",
            "factor_cupo": 1.00,
            "congelado": False,
            "bloqueado": False,
            "abono_minimo_pct": 0.0
        }
    elif 40.0 <= score_redondeado < 60.0:
        return {
            "categoria_riesgo": "C",
            "nivel_riesgo": "Riesgo Alto (Clase C)",
            "aprobado": False,
            "accion": "Congelamiento de cupo. Requiere abono previo del 50% para despachar nuevo fiado.",
            "sugerencia_cupo": "Congelado",
            "factor_cupo": 1.00,
            "congelado": True,
            "bloqueado": False,
            "abono_minimo_pct": 0.50
        }
    else:
        return {
            "categoria_riesgo": "D",
            "nivel_riesgo": "Riesgo Crítico (Clase D)",
            "aprobado": False,
            "accion": "Bloqueo automático de crédito. Cliente resaltado en alerta roja.",
            "sugerencia_cupo": "Bloqueado",
            "factor_cupo": 0.00,
            "congelado": True,
            "bloqueado": True,
            "abono_minimo_pct": 1.00
        }


def evaluar_cold_start(cliente_id: int, conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Protocolo de Arranque en Frío (RF-SCR-02):
    Evalúa a clientes sin historial previo (menos de 3 ciclos de pago oportunos registrados en CxC).
    IMPORTANTE: Si el cliente presenta saldo activo con más de 8 días de mora,
    se desactiva el Cold-Start para ser evaluado inmediatamente por el cálculo general de mora.
    """
    cursor = conn.cursor()

    # 1. Desactivación de Cold-Start si existe mora activa mayor al plazo estándar (8 días)
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = ?", (cliente_id,))
    cli_row = cursor.fetchone()
    saldo_actual = float(cli_row["saldo_actual"] or 0.0) if cli_row else 0.0

    if saldo_actual > 0:
        cursor.execute("""
            SELECT CAST(julianday('now') - julianday(fecha_movimiento) AS INTEGER) AS dias_transcurridos
            FROM cuentas_por_cobrar
            WHERE cliente_id = ? AND tipo_movimiento = 'cargo'
            ORDER BY fecha_movimiento ASC
            LIMIT 1
        """, (cliente_id,))
        cxc_row = cursor.fetchone()
        dias_transcurridos = cxc_row["dias_transcurridos"] if (cxc_row and cxc_row["dias_transcurridos"] is not None) else 0
        if dias_transcurridos > PLAZO_ESTANDAR_DIAS:
            return {"es_cold_start": False}

    # 2. Contar ciclos de abono registrados
    cursor.execute("""
        SELECT COUNT(*) AS total_ciclos
        FROM cuentas_por_cobrar
        WHERE cliente_id = ? AND tipo_movimiento = 'abono'
    """, (cliente_id,))
    row = cursor.fetchone()
    total_ciclos = row["total_ciclos"] if row else 0

    if total_ciclos >= 3:
        return {"es_cold_start": False}

    sw3 = calcular_sw3(cliente_id, conn)
    cursor.execute("SELECT nivel_vinculo FROM clientes WHERE id = ?", (cliente_id,))
    cli_info = cursor.fetchone()
    vinculo = (cli_info["nivel_vinculo"] or "").lower() if cli_info else "solo_apodo"

    # Diferenciación de Categoría y Cupo en Cold-Start según nivel_vinculo
    if vinculo == "registro_completo":
        cupo_semilla = 50000.0
        cat_riesgo = "A"
    elif vinculo == "conocido_referido":
        cupo_semilla = 40000.0
        cat_riesgo = "B"
    else:  # 'solo_apodo' u otros
        cupo_semilla = 30000.0
        cat_riesgo = "C"

    score_semilla = sw3
    decision_cold_start = {
        "categoria_riesgo": cat_riesgo,
        "nivel_riesgo": "Cold-Start Semilla",
        "aprobado": True,
        "accion": f"Asignación de cupo semilla conservador (${cupo_semilla:,.0f} COP) a plazo máximo de 15 días.",
        "sugerencia_cupo": "Cupo Semilla",
        "factor_cupo": 1.00,
        "congelado": False,
        "bloqueado": False,
        "abono_minimo_pct": 0.0
    }

    return {
        "es_cold_start": True,
        "ciclos_completados": total_ciclos,
        "score_semilla": score_semilla,
        "cupo_semilla": cupo_semilla,
        "plazo_dias": 15,
        "decision": decision_cold_start
    }


def calcular_score(cliente_id: int, conn: sqlite3.Connection) -> Tuple[float, str]:
    """
    Calcula el Scoring Crediticio Global S (0 - 100 pts) para un cliente.
    S = 0.40 * SW1 + 0.35 * SW2 + 0.25 * SW3.
    Retorna la tupla (score, categoria_riesgo).
    """
    cold_start = evaluar_cold_start(cliente_id, conn)
    if cold_start.get("es_cold_start"):
        score = float(cold_start["score_semilla"])
        cat_riesgo = cold_start["decision"]["categoria_riesgo"]
        return (score, cat_riesgo)

    sw1 = calcular_sw1(cliente_id, conn)
    sw2 = calcular_sw2(cliente_id, conn)
    sw3 = calcular_sw3(cliente_id, conn)

    score_global = round(0.40 * sw1 + 0.35 * sw2 + 0.25 * sw3, 2)
    decision = aplicar_matriz_decision(score_global)
    cat_riesgo = decision["categoria_riesgo"]

    return (score_global, cat_riesgo)


def registrar_snapshot(
    cliente_id: int,
    sw1: float,
    sw2: float,
    sw3: float,
    score_ant: int,
    score_nuevo: int,
    cat_ant: str,
    cat_nueva: str,
    motivo: str,
    conn: sqlite3.Connection
) -> ScoringHistorial:
    """
    Registra una entrada inmutable de trazabilidad en scoring_historial (Append-Only).
    Garantiza el casteo explícito a entero (int) de los puntajes antes de persistir en SQLite.
    """
    score_ant_int = int(round(score_ant))
    score_nuevo_int = int(round(score_nuevo))

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scoring_historial (
                cliente_id, score_anterior, score_nuevo, categoria_anterior, categoria_nueva,
                sw1, sw2, sw3, motivo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cliente_id, score_ant_int, score_nuevo_int, cat_ant, cat_nueva, sw1, sw2, sw3, motivo))
        
        snapshot_id = cursor.lastrowid

        # Actualizar estado actual del cliente asegurando tipo entero
        cursor.execute("""
            UPDATE clientes
            SET score_crediticio = ?,
                categoria_riesgo = ?
            WHERE id = ?
        """, (score_nuevo_int, cat_nueva, cliente_id))

        # Confirmación atómica de la transacción
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return ScoringHistorial(
        id=snapshot_id,
        cliente_id=cliente_id,
        sw1=sw1,
        sw2=sw2,
        sw3=sw3,
        score_anterior=score_ant_int,
        score_nuevo=score_nuevo_int,
        categoria_anterior=cat_ant,
        categoria_nueva=cat_nueva,
        motivo=motivo
    )
