"""
Pruebas unitarias para la función pura de explicación en lenguaje natural del scoring.
"""

from datetime import date
from ui.explicacion_scoring import explicar_clase, texto_vencimiento


def test_explicacion_normal_y_veto():
    """
    Verifica la explicación de scoring en casos normales y casos con regla de veto aplicada.
    """
    ev_normal = {
        "es_cold_start": False,
        "score": 69.75,
        "sw1": 80,
        "sw2": 65,
        "sw3": 60,
        "dias_transcurridos": 0,
        "dias_mora_efectiva": 0,
        "clase_puntaje": "B",
        "clase_final": "B",
        "veto_aplicado": None,
        "cold_start": None,
    }
    res_normal = explicar_clase(ev_normal)
    assert res_normal == "Clase B: puntaje 69,8 (pago 80, frecuencia 65, vínculo 60)"

    ev_veto = {
        "es_cold_start": False,
        "score": 68.8,
        "sw1": 70,
        "sw2": 70,
        "sw3": 65,
        "dias_transcurridos": 16,
        "dias_mora_efectiva": 8,
        "clase_puntaje": "B",
        "clase_final": "C",
        "veto_aplicado": "R1",
        "cold_start": None,
    }
    res_veto = explicar_clase(ev_veto)
    assert res_veto.startswith("Clase C por regla R1: 8 días de mora efectiva")
    assert "por puntaje sería B, con 68,8" in res_veto


def test_explicacion_cold_start():
    """
    Verifica la explicación para clientes en cold-start según ciclos completados y vínculo.
    """
    ev_cs_1 = {
        "es_cold_start": True,
        "score": 20.0,
        "sw1": None,
        "sw2": None,
        "sw3": None,
        "dias_transcurridos": 0,
        "dias_mora_efectiva": 0,
        "clase_puntaje": "C",
        "clase_final": "C",
        "veto_aplicado": None,
        "cold_start": {
            "es_cold_start": True,
            "ciclos_completados": 1,
            "score_semilla": 20.0,
            "cupo_semilla": 30000.0,
            "plazo_dias": 8,
        },
    }
    res_cs_1 = explicar_clase(ev_cs_1, nivel_vinculo="solo_apodo")
    assert "Cliente nuevo" in res_cs_1
    assert "solo apodo" in res_cs_1
    assert "le faltan 2 ciclos" in res_cs_1

    ev_cs_2 = {
        "es_cold_start": True,
        "score": 20.0,
        "sw1": None,
        "sw2": None,
        "sw3": None,
        "dias_transcurridos": 0,
        "dias_mora_efectiva": 0,
        "clase_puntaje": "C",
        "clase_final": "C",
        "veto_aplicado": None,
        "cold_start": {
            "es_cold_start": True,
            "ciclos_completados": 2,
            "score_semilla": 20.0,
            "cupo_semilla": 30000.0,
            "plazo_dias": 8,
        },
    }
    res_cs_2 = explicar_clase(ev_cs_2, nivel_vinculo="solo_apodo")
    assert "le falta 1 ciclo" in res_cs_2


def test_texto_vencimiento():
    """
    Verifica los diferentes formatos de salida de texto_vencimiento:
    None, faltan N días, falta 1 día, vence hoy, vencido hace 1 día, vencido hace N días.
    """
    # 1. Caso sin saldo / fecha None
    assert texto_vencimiento(None, None) == "Sin saldo pendiente"

    f = date(2026, 10, 25)

    # 2. Faltan N días (d > 1)
    res_n = texto_vencimiento(f, 4)
    assert res_n == "25/10/2026 (faltan 4 días)"

    # 3. Falta 1 día (d == 1)
    res_1 = texto_vencimiento(f, 1)
    assert res_1 == "25/10/2026 (falta 1 día)"

    # 4. Vence hoy (d == 0)
    res_0 = texto_vencimiento(f, 0)
    assert res_0 == "25/10/2026 (vence hoy)"

    # 5. Vencido hace 1 día (d == -1)
    res_m1 = texto_vencimiento(f, -1)
    assert res_m1 == "25/10/2026 (vencido hace 1 día)"

    # 6. Vencido hace N días (d < -1)
    res_mn = texto_vencimiento(f, -6)
    assert res_mn == "25/10/2026 (vencido hace 6 días)"

