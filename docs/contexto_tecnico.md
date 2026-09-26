# Contexto Técnico del Proyecto — Sistema de Scoring Crediticio para Tiendas de Barrio

**Proyecto:** Desarrollo de un sistema de información con motor analítico de scoring crediticio para la gestión operativa y financiera de micronegocios minoristas de Barranquilla
**Autores:** Altime Andrés Heredia Jaimes, Andrés Felipe Segura Angulo
**Repositorio:** `alti0921/mi_proyecto_tienda`
**Última actualización de este documento:** 2026-09-26
**Propósito:** Consolidar el estado técnico completo del proyecto en un solo documento, para que cualquier sesión futura (con Claude, con Gemini/Antigravity, o con los propios estudiantes) tenga el contexto necesario sin tener que re-derivarlo desde cero.

> ⚠️ **Regla de oro para cualquier IA o desarrollador que continúe este proyecto:** antes de escribir código nuevo, leer este documento completo, en particular la Sección 4 (reglas y parches ya corregidos) y la Sección 6 (inconsistencia abierta sin resolver). No repetir bugs ya corregidos aquí.

---

## 1. Resumen del estado actual y módulos finalizados

### 1.1 Fases del proyecto y su estado

| Fase | Contenido | Estado |
|---|---|---|
| **Fase 1** — Diagnóstico | 15 encuestas de campo a tenderos, calibración empírica de variables (P-Q1 a P-Q9), ajuste de Alcance/Delimitaciones, respuesta a observaciones metodológicas del profesor | ✅ Cerrada y aprobada |
| **Fase 2** — Diseño de arquitectura | Blueprint de Arquitectura (4 capas), Modelo Entidad-Relación (E-R) | ✅ Completa **excepto wireframes** |
| **Fase 2** — Wireframes | 5 pantallas: Login, POS, Perfil cliente/CxC, Inventario, Reportes | ❌ **Pendiente — único entregable de Fase 2 que falta** |
| **Fase 3** — Construcción modular | `db/schema.sql`, `/models`, `services/scoring_service.py`, `services/inventario_service.py`, `tests/` | ✅ Auditado, corregido y con 18/18 tests en verde |
| **Fase 3** — Construcción modular (siguiente) | `services/cxc_service.py`, `services/pos_service.py`, `/ui` (Tkinter) | ❌ Pendiente — **luz verde ya otorgada para iniciar** |

**Nota de clasificación de fases:** el código ya construido (`schema.sql`, `/models`, `/services`, `/tests`) técnicamente pertenece a Fase 3 (Construcción modular), no a los entregables formales de Fase 2. Esto ya fue discutido y resuelto: el código se trata como "avance de Fase 3 fundamentado en un diseño de Fase 2 ya formalizado" (el Blueprint y el E-R). El único punto que sigue abierto de Fase 2 en sí son los wireframes.

### 1.2 Módulos de código finalizados y verificados

| Módulo | Estado | Cobertura de tests |
|---|---|---|
| `db/schema.sql` (7 tablas) | ✅ Verificado línea por línea | N/A (fuente de verdad) |
| `models/*.py` (dataclasses puras) | ✅ Verificado contra schema | Implícita vía tests de servicios |
| `services/scoring_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_scoring.py` — 7 tests |
| `services/inventario_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_inventario.py` — 10 tests |
| **Total suite** | ✅ **18/18 passed** | Confirmado en terminal (pytest 9.1.1, Python 3.12.10) |

### 1.3 Documentos de Fase 2 ya entregados (recién compartidos)

- **Blueprint de Arquitectura del Sistema** — describe la arquitectura de 4 capas (Presentación/Lógica de negocio/Dominio/Persistencia), justificada contra RNF-05, RNF-03 y Testabilidad. Confirma que `/ui` está "pendiente de construcción (wireframes en curso)".
- **Modelo Entidad-Relación (E-R)** — construido 1:1 desde `db/schema.sql` (218 líneas), incluye notas de cardinalidad (FKs nullable) y diccionario de datos con trazabilidad a requisitos funcionales (RF).

---

## 2. Decisiones clave de arquitectura y lógica de código acordadas

1. **Sistema experto basado en reglas, NO Machine Learning.** El motor de scoring traduce directamente los puntos de quiebre identificados empíricamente en la Fase 1 (15 encuestas) en cortes de puntuación. No hay entrenamiento de modelos ni aprendizaje estadístico.

2. **Arquitectura en 4 capas (Layered Architecture):**
   - `/ui` (Presentación) → `/services` (Lógica de negocio) → `/models` (Dominio, dataclasses puras sin acoplamiento a SQLite) → `/db` (Persistencia, SQLite + schema.sql)
   - Justificación: RNF-05 (integridad centralizada en schema.sql vía FK/CHECK), RNF-03 (rendimiento — `/services` optimizable sin tocar UI), Testabilidad (`/tests` valida `/services` y `/models` sin simular UI).

3. **Patrón Append-Only para `cuentas_por_cobrar`.** Ningún registro de movimiento de cartera se edita ni se borra jamás; se aplica mediante triggers SQL a nivel de base de datos (`bloquear_edicion_cxc`, `bloquear_borrado_cxc`), no solo por convención en el código. Esto es lo que garantiza RNF-05 y RF-CXC-01 de forma verificable.

4. **`Abono` NO es una tabla separada.** Es una vista/filtro lógico de `cuentas_por_cobrar` donde `tipo_movimiento = 'abono'`. `CuentaPorCobrar` (el dataclass) es un DTO/Read-Model, nunca se persiste directamente como objeto — se inserta como filas con `tipo_movimiento IN ('cargo','abono')`.

5. **No existe una tabla `inventario_movimiento`.** Los cambios de stock se aplican mediante `UPDATE productos SET stock = stock ± cantidad WHERE id = ?` **dentro de la misma transacción** que genera la venta o el cargo. Ver Sección 6 para una inconsistencia abierta relacionada con esta decisión.

6. **Atomicidad transaccional obligatoria.** Cualquier operación que toque `cuentas_por_cobrar` o `productos.stock` debe actualizar el campo cacheado correspondiente (`clientes.saldo_actual`, `productos.stock`) **dentro de la misma transacción** (commit/rollback conjunto). Este patrón ya está probado en `registrar_snapshot()` y debe replicarse en `cxc_service.py` y `pos_service.py`.

7. **Separación conceptual P-Q6 vs. P-Q9 (fundamental para el scoring):**
   - **P-Q6** define el **plazo pactado inicial** de pago tras la compra: `PLAZO_ESTANDAR_DIAS = 8` días.
   - **P-Q9** define la **tolerancia de mora adicional** *después* de vencido ese plazo, antes de congelar el crédito.
   - La variable operativa correcta es la **mora efectiva**: `dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS)`. El umbral literal de P-Q9 (7 a 10 días, 66.7% de tenderos congela) se aplica **directamente** sobre esta mora efectiva, sin ninguna conversión a "días calendario equivalentes" (esa conversión confusa fue eliminada de toda la documentación).

8. **Redondeo direccional conservador en inventario**, para evitar la congelación por "banker's rounding" de Python:
   - Salidas/ventas (`cantidad < 0`) → `math.floor()`
   - Entradas (`cantidad >= 0`) → `math.ceil()`
   - Limitación conocida y aceptada: `ceil()` en entradas puede sobreestimar inventario fraccional — formalizado como **RS-05** ("Aprovisionamiento de Inventario en Unidades Enteras") en el ERS, documentado también en el docstring del código. Aceptado como limitación conocida, no como bug pendiente.

9. **Escala de scoring: 0–100 puntos / categorías A-B-C-D** (no escala FICO 300-850, no etiquetas Bajo-Medio-Alto). Fórmula ponderada:
   `S = 0.40×SW1 + 0.35×SW2 + 0.25×SW3`

10. **Protocolo Cold-Start:** clientes nuevos o con menos de 3 ciclos de pago reciben un cupo semilla en vez del cálculo ponderado completo — pero **nunca** si ya tienen saldo activo en mora más allá del plazo pactado (ver bug corregido en Sección 4).

---

## 3. Fragmentos y estructuras de código críticas (NO ROMPER)

### 3.1 `db/schema.sql` — fuente de verdad de columnas y tipos

```sql
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin', 'vendedor')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_barras TEXT UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL CHECK (categoria IN ('canasta_basica', 'cesta_mixta', 'consumo_suntuario')),
    precio_venta REAL NOT NULL CHECK (precio_venta >= 0),
    costo REAL NOT NULL DEFAULT 0.0 CHECK (costo >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    stock_minimo INTEGER NOT NULL DEFAULT 5 CHECK (stock_minimo >= 0),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    direccion TEXT,
    limite_credito REAL NOT NULL DEFAULT 0.0 CHECK (limite_credito >= 0),
    saldo_actual REAL NOT NULL DEFAULT 0.0 CHECK (saldo_actual >= 0),
    score_crediticio INTEGER NOT NULL DEFAULT 60 CHECK (score_crediticio BETWEEN 0 AND 100),
    categoria_riesgo TEXT NOT NULL DEFAULT 'B' CHECK (categoria_riesgo IN ('A', 'B', 'C', 'D')),
    nivel_vinculo TEXT NOT NULL DEFAULT 'solo_apodo' CHECK (nivel_vinculo IN ('registro_completo', 'conocido_referido', 'solo_apodo')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ventas.tipo_pago CHECK (tipo_pago IN ('efectivo', 'nequi', 'credito'))
-- venta_detalle.producto_id es NULLABLE (permite venta por monto global sin producto catalogado, RF-POS-02)

CREATE TABLE cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    venta_id INTEGER REFERENCES ventas(id),
    tipo_movimiento TEXT NOT NULL CHECK (tipo_movimiento IN ('cargo', 'abono')),
    monto REAL NOT NULL CHECK (monto > 0),
    saldo_resultante REAL NOT NULL CHECK (saldo_resultante >= 0),
    descripcion TEXT,
    fecha_movimiento DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scoring_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    score_anterior INTEGER NOT NULL,
    score_nuevo INTEGER NOT NULL,
    categoria_anterior TEXT,
    categoria_nueva TEXT,
    sw1 REAL, sw2 REAL, sw3 REAL,
    motivo TEXT NOT NULL,
    fecha_calculo DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cxc_cliente_fecha ON cuentas_por_cobrar(cliente_id, fecha_movimiento);

CREATE TRIGGER bloquear_edicion_cxc
BEFORE UPDATE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite editar registros.');
END;

CREATE TRIGGER bloquear_borrado_cxc
BEFORE DELETE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite eliminar registros.');
END;
```

*(Nota: `venta_id` en `cuentas_por_cobrar` es NULLABLE — un abono no siempre está ligado a una venta específica, confirmado en el E-R.)*

### 3.2 `services/scoring_service.py` — motor de decisión (final, 7/7 tests en verde)

```python
PLAZO_ESTANDAR_DIAS = 8

def calcular_v1_1(dias_mora_efectiva: int) -> float:
    """
    Calcula el puntaje de V1.1 (0 a 100) según los 4 niveles empíricos de P-Q9,
    aplicados directamente sobre la mora efectiva (sin conversión a días calendario):
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

def calcular_sw1(cliente_id, conn) -> float:
    # dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS)
    # v1_1 = calcular_v1_1(dias_mora_efectiva)
    # v1_2 (antigüedad del saldo): <30d→100, 30-59→60, 60-90→20, >90→0
    # SW1 = 0.60 * v1_1 + 0.40 * v1_2
    ...

def calcular_sw2(cliente_id, conn) -> float:
    # V2.1 frecuencia (ventas últimos 30 días): >=12→100, 6-11→75, 2-5→40, 1→10, 0→0
    # V2.2 dominancia de categoría: canasta_basica>=60%→100, suntuario>=50%→20, else→60 (neutral si no hay venta_detalle→60)
    # SW2 = 0.50*V2.1 + 0.50*V2.2
    ...

def calcular_sw3(cliente_id, conn) -> float:
    # nivel_vinculo: registro_completo→100, conocido_referido→60, solo_apodo→20
    ...

def aplicar_matriz_decision(score: float) -> dict:
    # 80-100     -> Clase A (aprobado, +20% cupo sugerido)
    # 60-79.9    -> Clase B (aprobado, mantener cupo)
    # 40-59.9    -> Clase C (congelado, abono_minimo_pct=0.50)
    # 0-39.9     -> Clase D (bloqueado, alerta roja)
    ...

def evaluar_cold_start(cliente_id, conn) -> dict:
    # Desactiva cold-start si saldo_actual > 0 AND dias_mora > PLAZO_ESTANDAR_DIAS  (bug corregido, ver Sección 4)
    # Si total_ciclos(abonos) >= 3 -> ya no es cold-start
    # cupo_semilla por nivel_vinculo: registro_completo=$50.000/A, conocido_referido=$40.000/B, solo_apodo=$30.000/C
    # plazo_dias = 15
    ...

def calcular_score(cliente_id, conn) -> tuple[float, str]:
    # S = 0.40*SW1 + 0.35*SW2 + 0.25*SW3, con bypass de cold-start cuando aplica
    ...

def registrar_snapshot(cliente_id, sw1, sw2, sw3, score_ant, score_nuevo, cat_ant, cat_nueva, motivo, conn) -> ScoringHistorial:
    # int(round(...)) al castear antes de INSERT/UPDATE
    # Atómico: INSERT en scoring_historial + UPDATE de clientes.score_crediticio/categoria_riesgo
    # dentro del mismo try/except con commit/rollback conjunto
    ...
```

### 3.3 `services/inventario_service.py` — gestión de stock (final, 10/10 tests en verde)

```python
import math

def ajustar_stock(producto_id, cantidad, conn) -> Producto:
    """
    Aplica redondeo direccional conservador:
    - Venta/Salida (cantidad < 0): math.floor(nuevo_stock)
    - Entrada (cantidad >= 0): math.ceil(nuevo_stock)
    Limitación conocida (RS-05): ceil() en entradas puede sobreestimar
    inventario fraccional — aceptado como limitación documentada.
    """
    nuevo_stock = float(row["stock"]) + cantidad
    if cantidad < 0:
        stock_final = math.floor(nuevo_stock)
    else:
        stock_final = math.ceil(nuevo_stock)
    if stock_final < 0:
        raise ValueError(...)
    cursor.execute("UPDATE productos SET stock = ? WHERE id = ?", (stock_final, producto_id))
    return Producto(..., stock=stock_final, ...)  # Sin commit() — la transacción del caller controla esto

# También: crear_producto, obtener_producto, obtener_producto_por_codigo,
# listar_productos, actualizar_producto, desactivar_producto (baja lógica),
# listar_alertas_stock (stock <= stock_minimo)
```

### 3.4 Modelos de dominio confirmados

- `models/producto.py` → `Producto`: `stock: int`, `stock_minimo: int` (corregido de float a int para calzar con el schema), más `@property margen` y `@property alerta_stock_bajo`.
- `models/cuenta_por_cobrar.py` → `CuentaPorCobrar` (DTO/Read-Model, no se persiste directo) y `Abono` (NO es tabla — filtro de `cuentas_por_cobrar` donde `tipo_movimiento='abono'`).
- Los 6 dataclasses (`Cliente`, `Producto`, `Venta`/`VentaDetalle`, `CuentaPorCobrar`/`Abono`, `ScoringHistorial`) exportados en `models/__init__.py`.

---

## 4. Reglas especiales y parches ya corregidos (NO reintroducir estos bugs)

| # | Bug | Corrección aplicada | Verificación |
|---|---|---|---|
| 1 | **Escala FICO incorrecta**: `score_crediticio` se implementó inicialmente en 300-850 / Bajo-Medio-Alto | Migrado a escala 0-100 / categorías A-B-C-D, calibrada empíricamente | Confirmado en schema.sql (`CHECK score_crediticio BETWEEN 0 AND 100`, `categoria_riesgo IN ('A','B','C','D')`) |
| 2 | **`tipo_pago` con valores incorrectos**: incluía `'tarjeta'` (no está en el ERS) y le faltaba `'nequi'` | Corregido a `('efectivo', 'nequi', 'credito')` | Confirmado en schema.sql y en E-R |
| 3 | **Cold-Start indefinido**: `evaluar_cold_start` solo contaba filas `abono` para determinar ciclos, así que un cliente con 0 abonos y deuda impaga se quedaba en Cold-Start para siempre, recibiendo sugerencia de "+20% cupo" pese a 60 días en mora | Se agregó chequeo: si `saldo_actual > 0` y `dias_mora > PLAZO_ESTANDAR_DIAS` → forzar `es_cold_start=False` | Test de regresión `test_cliente_moroso_sin_abonos` — PASSED |
| 4 | **V1.1 perdió nivel intermedio**: al añadir el plazo de gracia de 8 días, se colapsó de 4 niveles (100/70/30/0) a 3 (100/30/0), perdiendo la "alerta preventiva" | Recalibrado a 4 niveles aplicados directamente sobre mora efectiva (ver `calcular_v1_1` en 3.2) | Test `test_v1_1_mora_efectiva_bordes` — PASSED (4 casos de borde: 6, 7, 10, 11 días de mora efectiva) |
| 5 | **Truncamiento de stock**: `int(nuevo_stock)` truncaba el float acumulado silenciosamente, perdiendo stock fraccional de forma permanente en llamadas repetidas | Se probó primero `int(round(...))` uniforme — insuficiente (ver bug #6) | — |
| 6 | **"Banker's rounding" (redondeo al par más cercano)**: `round(9.5) == 10` no 9 en Python, causando que ventas repetidas de -0.5 "congelaran" el stock en números pares indefinidamente | `math.floor()` para salidas (`cantidad < 0`), `math.ceil()` para entradas (`cantidad >= 0`) | Test reforzado `test_ajustar_stock_fraccionario_consistencia_bd_y_dataclass` — verifica decremento monótono 10→9→8→7→6 en 4 ventas consecutivas de -0.5 |
| 7 | **`ceil()` en entradas sobreestima inventario** (limitación menor, no bloqueante) | Documentado como limitación conocida — formalizado como **RS-05** ("Aprovisionamiento de Inventario en Unidades Enteras") en el ERS y en el docstring del código | Aceptado explícitamente por los estudiantes (Opción 1: documentar, no corregir más) |
| 8 | **Fragmento de guía de arquitectura obsoleto pegado accidentalmente** en un documento, con nombres de campo VIEJOS (pre-corrección): `nombre_apodo`, `cupo_asignado`, `score_actual`, `clase_riesgo`, `tipo_pago='fiado'`, `tipo_evento`/`fecha` en vez de `tipo_movimiento`/`fecha_movimiento`, `score_S`/`clase_resultante` | Confirmado como copy-paste accidental, no usado activamente — pero **riesgo de que Antigravity/Gemini lo use como referencia si vuelve a aparecer** | Confirmado por el usuario que no está en uso |
| 9 | **Fixture de test desactualizado**: `test_cliente_mora_activa` usaba -8 días, que con el plazo de gracia caía en "al día" (mora efectiva = 0) en vez de Clase C | Fixture actualizado a -12 días (mora_efectiva=4 → SW1=58.0 → S=48.7 → Clase C) | Verificado a mano y confirmado en la suite 18/18 |
| 10 | **Traducción confusa "12-15 días calendario"**: la documentación traducía la mora efectiva a un rango de "días calendario equivalentes", generando inconsistencia con el rango literal "7-10 días" de P-Q9 citado en la misma tabla | Eliminada la conversión — se aplica el rango de P-Q9 **directamente** sobre `dias_mora_efectiva = max(0, dias_transcurridos - 8)` | Sincronizado en 4 documentos: tesis metodológica, sustentación, matriz de scoring, ERS (RF-SCR-01, RF-REP-02) |

---

## 5. Estado de la sincronización documental (4 documentos + código)

Confirmado por el usuario y verificado por Claude que los siguientes 4 frentes documentales están alineados con el código real (`calcular_v1_1`, `PLAZO_ESTANDAR_DIAS = 8`):

1. **Documento metodológico / tesis** (Fase de Desarrollo por Objetivos) — explicita la separación P-Q6/P-Q9.
2. **Documento de Sustentación** (Sección 1: Variables y Ponderaciones) — elimina la equivalencia "12-15 días calendario".
3. **Matriz de Variables y Ponderaciones Calibrada** (`docs/matriz_scoring.md` + Word) — columna de referencia de campo actualizada.
4. **ERS (IEEE-830)** — RF-SCR-01 (4 escalones empíricos directos) y RF-REP-02 (niveles de riesgo según cortes reales de V1.1) sincronizados.

Commit de referencia: `fix(scoring): alinear V1.1 a rangos directos de mora efectiva (0-3, 4-6, 7-10, >10) segun P-Q9` en rama `master`.

**Nits menores no bloqueantes, aún sin corregir:**
- RF-INV-01 todavía dice "SKU" en vez de "codigo_barras" (el nombre real de la columna).
- RS-05 podría reflejarse también en la sección de Delimitaciones del documento de tesis formal, no solo en el ERS (para consistencia total entre los 3 documentos).

---

## 6. ⚠️ Inconsistencia abierta detectada — requiere verificación antes de construir `pos_service.py`

Un documento de auditoría reciente (revisión del "Paso 2 de la Arquitectura por Capas") describe las siguientes dataclasses de forma **distinta** a lo ya confirmado y verificado en `schema.sql`:

- **`models/venta.py` → `Venta`**: descrito con `tipo_pago IN ('efectivo', 'fiado', 'mixto')`.
  **Esto contradice el schema real**, donde `ventas.tipo_pago CHECK (tipo_pago IN ('efectivo', 'nequi', 'credito'))` (ver Sección 3.1 y el bug #2 ya corregido en Sección 4). Antes de construir `pos_service.py`, **confirmar con el código real de `models/venta.py`** cuál de los dos conjuntos de valores está efectivamente implementado — no asumir que el documento de auditoría describe el estado actual.

- **`models/inventario_movimiento.py` → `InventarioMovimiento`**: el mismo documento menciona esta clase como si existiera y registrara "trazabilidad de entrada/salida/kardex de inventario". Esto **contradice la decisión de arquitectura ya acordada** (Sección 2, punto 5): no hay tabla `inventario_movimiento` en `schema.sql`, ni aparece en el Blueprint (que solo lista `cliente.py, producto.py, venta.py, venta_detalle.py, cuenta_por_cobrar.py, scoring.py` en `/models`). Si esta clase existe en el repositorio, es código muerto sin tabla de respaldo — verificar y, si aplica, eliminarla o formalizar la tabla correspondiente antes de seguir.

**Acción recomendada:** antes de iniciar `cxc_service.py`/`pos_service.py`, pedir a Antigravity el contenido real y actual de `models/venta.py` y confirmar si `models/inventario_movimiento.py` existe en el árbol de archivos del repo. No construir sobre supuestos del documento narrativo.

---

## 7. Siguiente paso exacto en la hoja de ruta

**Paso inmediato (Fase 2, pendiente):**
Construir los **wireframes de las 5 pantallas**: Login, POS, Perfil cliente/CxC, Inventario, Reportes. Este es el único entregable formal de Fase 2 que falta.

**Paso siguiente (Fase 3, construcción — ya con luz verde otorgada):**
1. Resolver la inconsistencia de la Sección 6 (verificar `models/venta.py` real y la existencia o no de `models/inventario_movimiento.py`).
2. Construir `services/cxc_service.py`:
   - Debe generar cargos (`tipo_movimiento='cargo'`) al confirmar una venta a crédito y abonos (`tipo_movimiento='abono'`) al recibir pagos.
   - Cada operación debe actualizar `clientes.saldo_actual` **dentro de la misma transacción** que el INSERT en `cuentas_por_cobrar` (mismo patrón atómico que `registrar_snapshot`).
   - Debe respetar el patrón append-only (nunca UPDATE/DELETE sobre `cuentas_por_cobrar` — los triggers ya lo bloquean a nivel de BD, pero el código no debe ni intentarlo).
3. Construir `services/pos_service.py`:
   - Integrar `inventario_service.ajustar_stock()` (descuento de stock por venta), generación de cargo en `cxc_service` cuando `tipo_pago='credito'`, y recalificación de `scoring_service` tras cada venta a crédito.
   - Todo dentro de una única transacción atómica por venta (venta + detalle + ajuste de stock + cargo CxC, todo o nada).
4. Escribir `tests/test_cxc.py` y `tests/test_pos.py` siguiendo el mismo patrón de fixtures SQLite en memoria con schema real (no mocks) usado en `test_scoring.py` / `test_inventario.py`.
5. Recién después de esto, iniciar `/ui` (Tkinter), una vez existan los wireframes.

---

*Fin del documento de contexto técnico. Generado por Claude a partir de la auditoría acumulada del proyecto.*
