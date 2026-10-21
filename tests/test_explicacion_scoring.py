"""
Pruebas unitarias para la función pura de explicación en lenguaje natural del scoring.
"""

from ui.explicacion_scoring import explicar_clase


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
