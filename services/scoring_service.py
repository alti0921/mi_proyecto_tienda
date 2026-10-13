import sqlite3
from typing import Optional, Tuple, Dict, Any
from models.scoring import ScoringHistorial

# Constantes de negocio: Plazo por defecto y plazos válidos permitidos (RF-CXC-07)
PLAZO_POR_DEFECTO_DIAS: int = 8
PLAZOS_PACTADOS_VALIDOS: Tuple[int, int] = (8, 15)

def calcular_v1_1(dias_mora_efectiva: int) -> float:
    """
    Calcula el puntaje de V1.1 (0 a 100) según los 4 niveles empíricos de P-Q9:
    - 0 a 3 días: 100.0 pts (al día / tolerancia leve)
    - 4 a 6 días: 70.0 pts (alerta preventiva)
    - 7 a 10 días: 30.0 pts (umbral de congelamiento según 66.7% de tenderos)
    - >10 días: 0.0 pts (mora crítica)
    """
    if 0 <= dias_mora_efectiva <= 3:
        return 100.0
    elif 4 <= dias_mora_efectiva <= 6:
        return 70.0
    elif 7 <= dias_mora_efectiva <= 10:
        return 30.0
    else:
        return 0.0


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


def _obtener_dias_transcurridos(cliente_id: int, conn: sqlite3.Connection) -> int:
    """
    Calcula los días transcurridos desde el CARGO PENDIENTE MÁS ANTIGUO del cliente,
    aplicando imputación FIFO (First In, First Out) de los abonos registrados.

    Regla FIFO:
    En una microtienda de barrio, los abonos parciales o totales cubren cronológicamente
    las compras a crédito más antiguas. Un cargo antiguo que ya ha sido completamente
    saldado por abonos históricos no debe seguir contando como mora activa ni inflar
    la antigüedad del saldo.

    Algoritmo:
    1. Si el cliente no existe o saldo_actual <= 0: retorna 0.
    2. Suma el total de todos los abonos del cliente.
    3. Acumula en orden cronológico los montos de los cargos. El primer cargo cuya
       suma acumulada supere total_abonos + 0.01 COP es el cargo pendiente más antiguo.
    4. Retorna la diferencia en días (truncada a entero, mínimo 0) de ese cargo.
    5. Si saldo_actual > 0 pero no se identifica ningún cargo pendiente (datos inconsistentes),
       utiliza el cargo más reciente; si no existen cargos, retorna 0.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT saldo_actual FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row:
        return 0

    saldo_actual = float(row["saldo_actual"] or 0.0)
    if saldo_actual <= 0:
        return 0

    cursor.execute("""
        SELECT tipo_movimiento, monto,
               (julianday('now') - julianday(fecha_movimiento)) AS dif
        FROM cuentas_por_cobrar
        WHERE cliente_id = ?
        ORDER BY fecha_movimiento ASC, id ASC
    """, (cliente_id,))
    movimientos = cursor.fetchall()

    total_abonos = sum(
        float(m["monto"] or 0.0) for m in movimientos if m["tipo_movimiento"] == "abono"
    )

    cargos = [m for m in movimientos if m["tipo_movimiento"] == "cargo"]
    acumulado_cargos = 0.0
    cargo_pendiente = None

    for c in cargos:
        acumulado_cargos += float(c["monto"] or 0.0)
        if acumulado_cargos > total_abonos + 0.01:
            cargo_pendiente = c
            break

    if cargo_pendiente is not None:
        dif = cargo_pendiente["dif"]
        dias = int(dif) if dif is not None else 0
        return max(0, dias)

    if saldo_actual > 0 and cargos:
        dif = cargos[-1]["dif"]
        dias = int(dif) if dif is not None else 0
        return max(0, dias)

    return 0


def obtener_plazo_pactado(cliente_id: int, conn: sqlite3.Connection) -> int:
    """
    Obtiene el plazo pactado de pago del cliente (8 o 15 días, RF-CXC-07).
    Si el cliente no existe o no tiene plazo configurado, retorna PLAZO_POR_DEFECTO_DIAS (8).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT plazo_pactado_dias FROM clientes WHERE id = ?", (cliente_id,))
    row = cursor.fetchone()
    if not row or row["plazo_pactado_dias"] is None:
        return PLAZO_POR_DEFECTO_DIAS
    return int(row["plazo_pactado_dias"])


def calcular_mora_efectiva(cliente_id: int, conn: sqlite3.Connection) -> int:
    """
    Calcula los días de mora efectiva descontando el plazo pactado del cliente (8 o 15 días, RF-CXC-07)
    sobre los días transcurridos del cargo pendiente más antiguo (FIFO).
    """
    dias_transcurridos = _obtener_dias_transcurridos(cliente_id, conn)
    plazo_pactado = obtener_plazo_pactado(cliente_id, conn)
    return max(0, dias_transcurridos - plazo_pactado)


def calcular_sw1(cliente_id: int, conn: sqlite3.Connection) -> float:
    """
    Calcula SW1: Comportamiento de Pago Histórico (Peso W1 = 40%).
    SW1 = 0.60 * V1.1 (días de mora efectiva tras el plazo pactado del cliente) + 0.40 * V1.2 (antigüedad de saldo).
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
        dias_transcurridos = _obtener_dias_transcurridos(cliente_id, conn)
        dias_mora_efectiva = calcular_mora_efectiva(cliente_id, conn)

        # Evaluación V1.1: 4 Niveles de Mora Efectiva según P-Q9
        v1_1 = calcular_v1_1(dias_mora_efectiva)

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


def aplicar_reglas_veto(clase_puntaje: str, dias_mora_efectiva: int) -> Tuple[str, Optional[str]]:
    """
    Aplica las reglas de veto R1 y R2 sobre la clase obtenida por puntaje:
      - R2: dias_mora_efectiva > 10 -> Clase final 'D'.
      - R1: 7 <= dias_mora_efectiva <= 10 -> La más restrictiva entre clase_puntaje y 'C'.
    Orden de severidad: A < B < C < D.
    Retorna la tupla (clase_final, veto_aplicado).
    veto_aplicado es 'R1', 'R2' o None si la clase no fue modificada por una regla de veto.
    Lanza ValueError si clase_puntaje no está en ('A', 'B', 'C', 'D') o dias_mora_efectiva < 0.
    """
    if clase_puntaje not in ("A", "B", "C", "D"):
        raise ValueError(
            f"Clase de puntaje no válida: '{clase_puntaje}'. Debe ser una de ('A', 'B', 'C', 'D')."
        )
    if dias_mora_efectiva < 0:
        raise ValueError(
            f"Los días de mora efectiva no pueden ser negativos (recibido: {dias_mora_efectiva})."
        )

    if dias_mora_efectiva > 10:
        if clase_puntaje != "D":
            return ("D", "R2")
        return ("D", None)
    elif 7 <= dias_mora_efectiva <= 10:
        if clase_puntaje in ("A", "B"):
            return ("C", "R1")
        return (clase_puntaje, None)
    else:
        return (clase_puntaje, None)


def decision_por_clase(clase: str) -> Dict[str, Any]:
    """
    Retorna la parametrización de riesgo y decisión comercial para una clase dada ('A', 'B', 'C', 'D').
    Lanza ValueError si la clase no es válida.
    """
    if clase == "A":
        return {
            "categoria_riesgo": "A",
            "nivel_riesgo": "Riesgo Bajo (Clase A)",
            "aprobado": True,
            "accion": "Crédito aprobado. Sugerencia de incremento de cupo de hasta un 20%.",
            "sugerencia_cupo": "+20%",
            "factor_cupo": 1.20,
            "congelado": False,
            "bloqueado": False,
            "abono_minimo_pct": 0.0,
        }
    elif clase == "B":
        return {
            "categoria_riesgo": "B",
            "nivel_riesgo": "Riesgo Medio (Clase B)",
            "aprobado": True,
            "accion": "Crédito aprobado. Mantener cupo habitual a plazo estándar (8 a 15 días).",
            "sugerencia_cupo": "Mantener",
            "factor_cupo": 1.00,
            "congelado": False,
            "bloqueado": False,
            "abono_minimo_pct": 0.0,
        }
    elif clase == "C":
        return {
            "categoria_riesgo": "C",
            "nivel_riesgo": "Riesgo Alto (Clase C)",
            "aprobado": False,
            "accion": "Congelamiento de cupo. Requiere abono previo del 50% para despachar nuevo fiado.",
            "sugerencia_cupo": "Congelado",
            "factor_cupo": 1.00,
            "congelado": True,
            "bloqueado": False,
            "abono_minimo_pct": 0.50,
        }
    elif clase == "D":
        return {
            "categoria_riesgo": "D",
            "nivel_riesgo": "Riesgo Crítico (Clase D)",
            "aprobado": False,
            "accion": "Bloqueo automático de crédito. Cliente resaltado en alerta roja.",
            "sugerencia_cupo": "Bloqueado",
            "factor_cupo": 0.00,
            "congelado": True,
            "bloqueado": True,
            "abono_minimo_pct": 1.00,
        }
    else:
        raise ValueError(f"Clase de riesgo no válida: '{clase}'. Debe ser una de ('A', 'B', 'C', 'D').")


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
        clase = "A"
    elif 60.0 <= score_redondeado < 80.0:
        clase = "B"
    elif 40.0 <= score_redondeado < 60.0:
        clase = "C"
    else:
        clase = "D"
    return decision_por_clase(clase)


def evaluar_cold_start(cliente_id: int, conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Protocolo de Arranque en Frío (RF-SCR-02):
    Evalúa a clientes sin historial previo (menos de 3 ciclos de pago oportunos registrados en CxC).
    IMPORTANTE: Si el cliente presenta saldo activo con más de 8 días de mora,
    se desactiva el Cold-Start para ser evaluado inmediatamente por el cálculo general de mora.
    """
    # 1. Desactivación de Cold-Start si existe mora activa mayor al plazo estándar (8 días)
    if calcular_mora_efectiva(cliente_id, conn) > 0:
        return {"es_cold_start": False}

    cursor = conn.cursor()

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


def evaluar_cliente(cliente_id: int, conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    ÚNICA fuente de la clase final y evaluación crediticia integral del cliente.
    Aplica ponderación de subvariables o protocolo Cold-Start, seguido de las
    reglas de veto R1 y R2 por mora efectiva.
    """
    dias_transcurridos = _obtener_dias_transcurridos(cliente_id, conn)
    dias_mora_efectiva = calcular_mora_efectiva(cliente_id, conn)
    cs = evaluar_cold_start(cliente_id, conn)

    if cs.get("es_cold_start"):
        score = float(cs["score_semilla"])
        clase_cs = cs["decision"]["categoria_riesgo"]
        return {
            "es_cold_start": True,
            "score": score,
            "sw1": None,
            "sw2": None,
            "sw3": None,
            "dias_transcurridos": dias_transcurridos,
            "dias_mora_efectiva": dias_mora_efectiva,
            "clase_puntaje": clase_cs,
            "clase_final": clase_cs,
            "veto_aplicado": None,
            "decision": cs["decision"],
            "cold_start": cs,
        }

    sw1 = calcular_sw1(cliente_id, conn)
    sw2 = calcular_sw2(cliente_id, conn)
    sw3 = calcular_sw3(cliente_id, conn)

    score = round(0.40 * sw1 + 0.35 * sw2 + 0.25 * sw3, 2)
    clase_puntaje = aplicar_matriz_decision(score)["categoria_riesgo"]
    clase_final, veto_aplicado = aplicar_reglas_veto(clase_puntaje, dias_mora_efectiva)

    decision = dict(decision_por_clase(clase_final))
    if veto_aplicado is not None:
        decision["accion"] = (
            f"Regla de veto {veto_aplicado}: {dias_mora_efectiva} días de mora efectiva. "
            + decision["accion"]
        )

    return {
        "es_cold_start": False,
        "score": score,
        "sw1": sw1,
        "sw2": sw2,
        "sw3": sw3,
        "dias_transcurridos": dias_transcurridos,
        "dias_mora_efectiva": dias_mora_efectiva,
        "clase_puntaje": clase_puntaje,
        "clase_final": clase_final,
        "veto_aplicado": veto_aplicado,
        "decision": decision,
        "cold_start": None,
    }


def calcular_score(cliente_id: int, conn: sqlite3.Connection) -> Tuple[float, str]:
    """
    Calcula el Scoring Crediticio Global S (0 - 100 pts) para un cliente.
    S = 0.40 * SW1 + 0.35 * SW2 + 0.25 * SW3.
    Retorna la tupla (score, categoria_riesgo).
    """
    resultado = evaluar_cliente(cliente_id, conn)
    return (resultado["score"], resultado["clase_final"])


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
    conn: sqlite3.Connection,
    auto_commit: bool = True,
) -> ScoringHistorial:
    """
    Registra una entrada inmutable de trazabilidad en scoring_historial (Append-Only).
    Garantiza el casteo explícito a entero (int) de los puntajes antes de persistir en SQLite.
    Si auto_commit es True, confirma o revierte la transacción internamente.
    Si es False, delega el control transaccional al orquestador.
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

        if auto_commit:
            conn.commit()
    except Exception as e:
        if auto_commit:
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
