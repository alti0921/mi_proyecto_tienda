# Fase 1: Diagnóstico Operativo y Calibración del Motor de Scoring Crediticio

A partir de la consolidación de la lista de chequeo observacional (12 ítems) y las entrevistas semiestructuradas (15 preguntas) aplicadas a los tenderos en los 8 barrios analizados de Barranquilla, se procedió a traducir los hallazgos empíricos en reglas de negocio parametrizables. Este proceso dio origen al diseño calibrado del Motor Experto de Scoring Crediticio (*Rule-Based Expert System*).

---

## 1. Sustentación de Variables y Ponderaciones

El algoritmo asigna un puntaje dinámico en una escala de 0 a 100 puntos mediante la siguiente función de evaluación:

$$S = (W_1 \times SW_1) + (W_2 \times SW_2) + (W_3 \times SW_3)$$

Donde las ponderaciones y subvariables se fundamentan directamente en la evidencia de campo:

* **Comportamiento de Pago Histórico ($W_1 = 40\%$):** Constituye la dimensión de mayor peso. La pregunta Q9 reveló que el 66.7% de los tenderos aplica un congelamiento de crédito nuevo al alcanzar entre 7 y 10 días de mora. Asimismo, el 73.3% ubica el umbral de cartera perdida o abandonada entre 60 y 90 días (Q12). La variable exige la implementación de un historial Append-Only inmutable, resolviendo que el 66.7% de los negocios actualmente borra o tacha el saldo anterior en papel sin dejar trazabilidad (Chequeo #6).
* **Frecuencia y Volumetría de Compra ($W_2 = 35\%$):** Basado en Q10, se identificó que la disposición a fiar no es uniforme; los tenderos priorizan a los clientes de compra diaria y aquellos que adquieren productos de la canasta básica familiar por encima de compradores esporádicos o de consumo suntuario (licor, mecato).
* **Confianza Relacional / Cualitativa ($W_3 = 25\%$):** Aunque el 53.3% de los tenderos solo anota el apodo o nombre del cliente (Chequeo #5), los hallazgos de la pregunta Q11 demostraron que la vecindad o el parentesco "ya no bastan" si el cliente es mal pagador. Por esta razón, la dimensión relacional se acotó al 25%, cediendo la prioridad al comportamiento histórico y la volumetría.

### Fórmula de Mora Efectiva ($V_{1.1}$)
$$\text{Días de Mora Efectiva} = \max(0, \text{Días Transcurridos} - 8)$$

---

## 2. Matriz de Variables y Ponderaciones Calibrada

| Dimensión | Peso ($W_i$) | Variable Interna | Criterios Operativos (Mora Efectiva) | Puntaje (0 - 100) | Interpretación Operativa / Referencia de Campo |
| :--- | :---: | :--- | :--- | :---: | :--- |
| **$W_1$: Comportamiento de Pago Histórico** | **40%** | **$V_{1.1}$: Días de Mora Efectiva** | • 0 días (Al día / dentro del plazo de gracia de 8 días)<br>• 1 a 3 días (Alerta preventiva)<br>• 4 a 7 días (Umbral de congelamiento de nuevo fiado)<br>• Más de 7 días (Mora crítica / Bloqueo) | 100 pts<br>70 pts<br>30 pts<br>0 pts | • Coincide con la venta a plazo regular.<br>• Retraso leve sobre la fecha pactada.<br>• Cumple el congelamiento identificado en P-Q9 (7-10 días calendario acumulados).<br>• Transición a riesgo crítico. |
| **$W_1$: Comportamiento de Pago Histórico** | **40%** | **$V_{1.2}$: Antigüedad de Saldo** | • $< 30$ días de antigüedad<br>• 30 - 59 días<br>• 60 - 90 días (Umbral Cartera Perdida)<br>• $> 90$ días (Incobrable) | 100 pts<br>60 pts<br>20 pts<br>0 pts | Base de antigüedad histórica (P-Q12). |
| **$W_2$: Frecuencia y Volumetría** | **35%** | **$V_{2.1}$: Frecuencia de Compra** | • Diario / Frecuente (12 o más transacciones/mes)<br>• Regular (6 - 11 transacciones/mes)<br>• Ocasional (2 - 5 transacciones/mes)<br>• Esporádico (1 transacción/mes) | 100 pts<br>75 pts<br>40 pts<br>10 pts | P-Q10: Prioridad de fiado a clientes de alta rotación diaria. |
| **$W_2$: Frecuencia y Volumetría** | **35%** | **$V_{2.2}$: Tipo de Producto** | • Canasta Básica (arroz, aceite, proteína)<br>• Cesta Mixta (Básicos + Snacks)<br>• Consumo Suntuario (Licores, cigarrillos, mecato) | 100 pts<br>60 pts<br>20 pts | P-Q10: Disposición superior a fiar artículos de primera necesidad. |
| **$W_3$: Confianza Relacional** | **25%** | **$V_{3.1}$: Vínculo y Captura de Datos** | • Registro Completo (Nombre + Teléfono/Dirección)<br>• Vecino / Conocido directo<br>• Solo Apodo / Referencia informal | 100 pts<br>60 pts<br>20 pts | Chequeo #5 y P-Q11: 53.3% solo usa apodo. La relación cede ante el pago. |

---

## 3. Mecanismo de Arranque en Frío (Cold-Start) y Escala de Decisiones

Para garantizar la operabilidad con clientes nuevos sin historial previo registrado en la aplicación:

* **Evaluación Semilla:** Se evalúa únicamente la variable $V_{3.1}$.
* **Cupo Asignado:** Se asigna un límite conservador de \$30.000 a \$50.000 COP a un plazo máximo de 8 a 15 días (rangos mínimos identificados en Q6).
* **Transición:** Al cumplir 3 ciclos de pago oportunos, el cliente entra al cálculo general de las tres dimensiones.

### Matriz de Decisión y Salidas del Sistema

| Rango de Score | Clasificación de Riesgo | Decisión Operativa / Salida del Sistema |
| :---: | :---: | :--- |
| **80 - 100 pts** | **Riesgo Bajo / Clase A** | Crédito approved. Sugerencia de incremento de cupo hasta en un 20%. |
| **60 - 79 pts** | **Riesgo Medio / Clase B** | Crédito aprobado. Mantener cupo habitual a plazo estándar (8 a 15 días). |
| **40 - 59 pts** | **Riesgo Alto / Clase C** | Congelamiento de cupo. Requiere abono previo del 50% para despachar nuevo fiado. |
| **0 - 39 pts** | **Crítico / Clase D** | Bloqueo automático de crédito. La interfaz destaca al cliente en rojo, atendiendo al requerimiento directo de visualización de alertas (Q14). |
