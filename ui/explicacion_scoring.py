"""
Módulo de explicación en lenguaje natural del puntaje y clasificación crediticia.
Función pura independiente de Tkinter y de la base de datos.
"""

from typing import Optional, Dict, Any

MAPA_VINCULOS = {
    "solo_apodo": "solo apodo",
    "conocido_referido": "conocido o referido",
    "registro_completo": "registro completo",
}


def explicar_clase(ev: Dict[str, Any], nivel_vinculo: Optional[str] = None) -> str:
    """
    Genera la explicación textual de la clasificación crediticia del cliente
    a partir del resultado de evaluar_cliente y su nivel de vínculo demográfico.
    """
    clase_final = ev.get("clase_final", "--")

    # Formato de score: 1 decimal con coma decimal
    score_val = ev.get("score")
    if score_val is not None:
        score_fmt = f"{float(score_val):.1f}".replace(".", ",")
    else:
        score_fmt = "--"

    # Regla 1: Veto aplicado por mora efectiva
    veto = ev.get("veto_aplicado")
    if veto:
        dias_mora = ev.get("dias_mora_efectiva", 0)
        clase_puntaje = ev.get("clase_puntaje", "--")
        return (
            f"Clase {clase_final} por regla {veto}: {dias_mora} días de mora efectiva "
            f"(por puntaje sería {clase_puntaje}, con {score_fmt})"
        )

    # Regla 2: Cliente en cold-start
    es_cold_start = bool(ev.get("es_cold_start"))
    if es_cold_start:
        ciclos = 0
        if "cold_start" in ev and isinstance(ev["cold_start"], dict):
            ciclos = ev["cold_start"].get("ciclos_completados", 0)
        elif "ciclos_completados" in ev:
            ciclos = ev.get("ciclos_completados", 0)

        n = max(0, 3 - int(ciclos))
        frase_ciclo = "le falta 1 ciclo" if n == 1 else f"le faltan {n} ciclos"
        frase_ciclos_completa = f"{frase_ciclo} de pago a tiempo para calcular el puntaje completo"

        if nivel_vinculo is not None:
            vinculo_legible = MAPA_VINCULOS.get(nivel_vinculo, str(nivel_vinculo).replace("_", " "))
            vinculo_str = f" por vínculo ({vinculo_legible})"
        else:
            vinculo_str = " por vínculo"

        return f"Cliente nuevo: clase {clase_final} indicativa{vinculo_str}; {frase_ciclos_completa}"

    # Regla 3: Caso normal
    sw1 = round(float(ev["sw1"])) if ev.get("sw1") is not None else 0
    sw2 = round(float(ev["sw2"])) if ev.get("sw2") is not None else 0
    sw3 = round(float(ev["sw3"])) if ev.get("sw3") is not None else 0

    return f"Clase {clase_final}: puntaje {score_fmt} (pago {sw1}, frecuencia {sw2}, vínculo {sw3})"
