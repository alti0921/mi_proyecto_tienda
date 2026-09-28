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
| `services/scoring_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_scoring.py` — 8 tests |
| `services/inventario_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_inventario.py` — 10 tests |
| `services/cxc_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_cxc.py` — 9 tests |
| `services/pos_service.py` | ✅ Auditado y corregido (ver Sección 4) — **backend completo** | `tests/test_pos.py` — 12 tests |
| **Total suite** | ✅ **40/40 passed** | Confirmado en terminal (pytest 9.1.1, Python 3.12.10) |

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

### 3.3 `services/cxc_service.py` — ledger de cartera (final, 10/10 tests en verde)

```python
NIVELES_VINCULO_VALIDOS = ("registro_completo", "conocido_referido", "solo_apodo")

def crear_cliente(nombre, conn, telefono=None, direccion=None,
                   nivel_vinculo="solo_apodo", limite_credito=0.0) -> Cliente:
    # Valida nombre no vacío, nivel_vinculo permitido, limite_credito >= 0
    # INSERT con saldo_actual=0.0, score_crediticio=60, categoria_riesgo='B' por defecto
    ...

def registrar_cargo(cliente_id, monto, conn, venta_id=None, descripcion=None) -> CuentaPorCobrar:
    """
    Salvaguarda de cupo (RF-CXC-06): rechaza CUALQUIER cargo cuyo saldo
    resultante supere clientes.limite_credito -- SIN excepción para
    limite_credito == 0.0 (cliente sin cupo asignado = cupo cero, no cupo infinito).
    """
    # monto <= 0 -> ValueError
    # cliente inexistente/inactivo -> ValueError
    nuevo_saldo = round(saldo_actual + monto, 2)
    if nuevo_saldo > limite_credito:   # sin guarda "limite_credito > 0" -- ver Sección 4
        raise ValueError(f"El cargo excede el límite de crédito del cliente "
                          f"(Cupo: {limite_credito}, Saldo resultante: {nuevo_saldo}).")
    # INSERT cuentas_por_cobrar (tipo_movimiento='cargo') + UPDATE clientes.saldo_actual
    # -- atómico, mismo try/commit/rollback que registrar_snapshot
    ...

def registrar_abono(cliente_id, monto, conn, venta_id=None, descripcion=None) -> CuentaPorCobrar:
    # monto <= 0 o monto > saldo_actual -> ValueError
    # INSERT cuentas_por_cobrar (tipo_movimiento='abono') + UPDATE clientes.saldo_actual
    # -- atómico
    ...

def consultar_saldo(cliente_id, conn) -> float: ...
def obtener_historial_cxc(cliente_id, conn) -> List[CuentaPorCobrar]: ...
```

**Separación de responsabilidades confirmada:** `pos_service.py` es el "cerebro comercial" — evalúa `calcular_score()` fresco, aplica la matriz de decisión (bloqueo Clase D, abono mínimo Clase C) y autoriza o no la venta. `cxc_service.py` es el ledger — nunca decide, solo ejecuta y protege la integridad contable con una salvaguarda dura de cupo como última línea de defensa (para que ninguna llamada directa, administrativa o futura, pueda saltarse el límite de crédito).

**Importante — `evaluar_cold_start()` NO persiste el cupo semilla.** Es una función de solo lectura: devuelve una sugerencia en memoria (`cupo_semilla`, `plazo_dias=15`), pero nunca ejecuta `UPDATE clientes SET limite_credito = ...`. La asignación efectiva del cupo a un cliente cold-start requiere una acción operativa explícita. Esto es una decisión de diseño deliberada (ver RF-SCR-02 corregido en Sección 5) — un sistema de riesgo crediticio no debe auto-asignar cupo sin que una persona lo confirme.

### 3.4 `services/pos_service.py` — orquestador transaccional de ventas (final, 12/12 tests en verde, backend completo)

```python
def asignar_limite_credito(cliente_id: int, nuevo_limite: float, conn: sqlite3.Connection) -> Cliente:
    """Confirmación operativa y auditable del cupo (cierra RF-SCR-02). Commit propio,
    se usa como acción independiente, no compuesta dentro de registrar_venta."""
    ...

def _validar_credito_clase_c(cliente_id: int, conn: sqlite3.Connection) -> None:
    """
    RF-SCR-04: exige que el ÚLTIMO movimiento en cuentas_por_cobrar del cliente sea un
    abono que cubra >= 50% del saldo que existía justo antes de ese abono
    (saldo_previo = saldo_resultante + monto_abono, reconstruido desde el ledger inmutable).
    Sin parámetros de bypass -- 100% determinista contra la BD.
    """
    ...

def registrar_venta(
    usuario_id: int,
    tipo_pago: str,
    items: List[Union[LineaVentaInput, Dict[str, Any], Any]],
    conn: sqlite3.Connection,
    cliente_id: Optional[int] = None,
    monto_pagado: float = 0.0,
) -> Venta:
    """
    Orquestador atómico. Flujo:
    1. Valida items (cantidad>0, precio>=0) y monto_pagado (>=0, y para
       efectivo/nequi: monto_pagado >= total; para credito: monto_pagado < total,
       si no exige tipo de pago de contado).
    2. Si credito: valida cliente activo, calcula_score() fresco, aplica matriz:
       - Clase D -> ValueError (RF-SCR-03)
       - Clase C y NO cold-start -> _validar_credito_clase_c() (RF-SCR-04)
       - Clase A/B o cold-start -> autoriza
    3. Bloque atómico (un solo commit/rollback):
       a. inventario_service.ajustar_stock(-cantidad) por cada producto_id
       b. INSERT ventas, INSERT venta_detalle
       c. Si credito: monto_a_fiar = round(total - monto_pagado, 2)
          cxc_service.registrar_cargo(cliente_id, monto_a_fiar, conn, venta_id, auto_commit=False)
          scoring_service.registrar_snapshot(..., auto_commit=False)
       d. conn.commit() unificado / except: conn.rollback() + re-raise
    """
    ...
```

**Composición transaccional (Opción B):** `registrar_cargo`, `registrar_abono` y `registrar_snapshot` reciben ahora `auto_commit: bool = True`. Llamadas aisladas/tests siguen comiteando solas (retrocompatible); `pos_service.py` las invoca con `auto_commit=False` para que el commit/rollback quede centralizado en `registrar_venta`. Verificado con `test_atomicidad_post_cargo_fallo_en_snapshot`, que fuerza el fallo **después** de que `registrar_cargo` ya se ejecutó (el escenario que realmente expone el bug de commits anidados) y confirma reversión total: 0 ventas, 0 detalle, stock intacto, 0 cargos, saldo sin alterar.

**Abono inicial en venta a crédito:** el cargo a `cuentas_por_cobrar` se calcula sobre `monto_a_fiar = total - monto_pagado`, nunca sobre `total` completo — evita cobrar de más cuando el cliente paga una parte en efectivo al momento de la venta.

### 3.5 `services/inventario_service.py` — gestión de stock (final, 10/10 tests en verde)

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

### 3.6 Modelos de dominio confirmados

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
| 11 | **`ventas` sin restricción de `cliente_id` en ventas a crédito**: el schema permitía `tipo_pago='credito'` con `cliente_id=NULL`, lo cual generaría cargos huérfanos imposibles de cobrar (`cuentas_por_cobrar.cliente_id` es `NOT NULL`) | Se agregó `CHECK (tipo_pago != 'credito' OR cliente_id IS NOT NULL)` en `db/schema.sql` | Test `test_venta_credito_requiere_cliente_integrity_error` — PASSED (verifica `sqlite3.IntegrityError`) |
| 12 | **Salvaguarda de `limite_credito` con vacío en el caso por defecto**: `registrar_cargo()` en `cxc_service.py` implementó primero `if limite_credito > 0 and nuevo_saldo > limite_credito`, lo que dejaba **sin protección exactamente a los clientes nuevos** (`limite_credito=0.0` por defecto en `crear_cliente`) — el caso más común, ya que cero cupo se interpretaba como "sin límite" en vez de "cupo cero" | Se eliminó la guarda `limite_credito > 0`; ahora `if nuevo_saldo > limite_credito` se aplica siempre, de modo que `limite_credito=0.0` bloquea cualquier cargo fiado | Test `test_registrar_cargo_cliente_sin_cupo_asignado_rechaza_cualquier_cargo` — PASSED |
| 13 | **Commits anidados rompían la atomicidad compuesta**: `registrar_cargo`, `registrar_abono` y `registrar_snapshot` hacían su propio `conn.commit()` interno; al componerlos dentro de `pos_service.registrar_venta()`, un fallo tardío (ej. en `registrar_snapshot`) no podía revertir lo ya comiteado por `registrar_cargo`, dejando ventas/cargos huérfanos sin su snapshot | Se agregó `auto_commit: bool = True` a las tres funciones; `pos_service.py` las invoca con `auto_commit=False` y centraliza un único `conn.commit()`/`conn.rollback()` en `registrar_venta` | Test `test_atomicidad_post_cargo_fallo_en_snapshot` — fuerza el fallo *después* de `registrar_cargo` y confirma reversión total (0 ventas, 0 detalle, stock intacto, 0 cargos, saldo sin alterar) |
| 14 | **Venta a crédito con abono inicial cobraba de más**: el diseño original de `pos_service` pasaba `total` completo a `cxc_service.registrar_cargo`, sin descontar ningún anticipo en efectivo entregado en la misma venta a crédito | Se calcula `monto_a_fiar = round(total - monto_pagado, 2)` y ese es el único monto que se carga a `cuentas_por_cobrar`; se valida `0 <= monto_pagado < total` para crédito (si `monto_pagado >= total`, exige tipo de pago de contado) | Test `test_venta_credito_con_abono_inicial_registra_solo_saldo_pendiente` — PASSED |
| 15 | **Bypass potencial en RF-SCR-04**: la primera versión de `_validar_credito_clase_c` tenía un parámetro `abono_previo_verificado: bool = False` que, de estar expuesto en la firma pública de `registrar_venta`, habría permitido a cualquier llamador saltarse la exigencia de abono del 50% | Se eliminó el parámetro por completo; la función ahora es 100% determinista contra `cuentas_por_cobrar` sin ninguna vía de excepción externa | Confirmado explícitamente que `registrar_venta(usuario_id, tipo_pago, items, conn, cliente_id=None, monto_pagado=0.0)` no expone ninguna bandera de bypass |

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

## 6. ✅ Cierre de `cxc_service.py` — cambios en el ERS

Todas las inconsistencias detectadas durante la construcción de `cxc_service.py` quedaron resueltas y verificadas con código real (no narrativa):

- `models/venta.py` confirmado alineado con schema (`tipo_pago IN ('efectivo','nequi','credito')`), `monto_cambio` restringido a `'efectivo'`.
- `models/inventario_movimiento.py` confirmado que **no existe** — sin código muerto.
- `PRAGMA foreign_keys=ON` confirmado activo tanto en `db/connection.py` (producción) como en `tests/conftest.py` (fixture `db_conn`).
- `db/seeds_test.sql` separado de `db/schema.sql` — producción arranca sin clientes/productos ficticios.
- Vacío de `cliente_id` en ventas a crédito y vacío de `limite_credito=0` en `registrar_cargo` corregidos (ver Sección 4, patches #11 y #12).

**Cambios formales al ERS resultantes de esta auditoría (decisión tomada: Opción A — el sistema sugiere, el tendero confirma):**

**Nueva cláusula `RF-CXC-06`:**

| Campo | Contenido |
|---|---|
| ID | RF-CXC-06 |
| Módulo | CRM / Fiados |
| Nombre | Bloqueo por Cupo Excedido |
| Descripción | El sistema debe rechazar el registro de cualquier cargo a crédito cuyo saldo resultante supere el límite de crédito (cupo) asignado al cliente. Un cliente sin cupo asignado explícitamente (límite de crédito en $0) no debe poder recibir ningún cargo fiado, sin excepción. |
| Trazabilidad | Vinculado a RF-CXC-05 (Visualización de Cupo) y Chequeo #11 (86.7% de tenderos sin cupo anotado visiblemente) |
| Prioridad | Alta |

**`RF-SCR-02` corregida (antes decía "asignando un cupo semilla", lo que implicaba persistencia automática — el código real solo sugiere):**

> *Redacción anterior:* "Para clientes sin historial, el sistema evaluará únicamente V3.1 asignando un cupo semilla de \$30.000 a \$50.000 COP por 3 ciclos de pago oportunos."
>
> **Redacción corregida:** "Para clientes sin historial, el sistema evaluará únicamente V3.1 y **sugerirá** al tendero un cupo semilla entre \$30.000 y \$50.000 COP, según el nivel de vínculo del cliente, válido para los primeros 3 ciclos de pago oportunos. La asignación efectiva del cupo al perfil del cliente **requiere confirmación operativa del tendero**; el sistema no debe persistir el cupo de forma automática sin esa confirmación."

Pendiente menor no bloqueante: `RF-SCR-02` tampoco menciona el `plazo_dias=15` que sí maneja `evaluar_cold_start()` en el código — se puede añadir en la misma revisión si quieren, pero no es urgente.

---

## 7. ✅ Backend certificado completo — siguiente paso: wireframes de Fase 2

**Backend 100% cerrado (40/40 tests en verde):** `db/schema.sql`, `/models`, `scoring_service.py`, `inventario_service.py`, `cxc_service.py` y `pos_service.py` — todos auditados línea por línea, con atomicidad verificada de punta a punta (incluyendo la composición correcta de transacciones anidadas vía `auto_commit`) y sin ninguna vía de bypass de las reglas de negocio (RF-SCR-03/04, RF-CXC-06).

`services/pos_service.py` (`registrar_venta`) es ahora el único punto de entrada para registrar una venta — orquesta inventario, CxC y scoring en una sola transacción atómica, y su firma pública no expone ningún parámetro que permita saltarse la evaluación de riesgo.

**Único entregable pendiente de Fase 2:**
Construir los **wireframes de las 5 pantallas**: Login, POS, Perfil cliente/CxC, Inventario, Reportes.

**Siguiente paso de Fase 3 (después de los wireframes):**
1. Iniciar `/ui` (Tkinter), consumiendo exclusivamente las funciones públicas ya auditadas de `services/`:
   - `pos_service.registrar_venta(...)` para el flujo de venta (POS).
   - `pos_service.asignar_limite_credito(...)` para que el tendero confirme el cupo semilla de un cliente cold-start (pantalla de Perfil cliente/CxC) — **este paso operativo debe tener un lugar visible en el wireframe correspondiente**, ya que sin él ningún cliente nuevo puede comprar fiado.
   - `cxc_service.crear_cliente(...)`, `obtener_cliente(...)`, `obtener_historial_cxc(...)` para registro y consulta de clientes.
   - `inventario_service.*` para el módulo de Inventario.
   - `scoring_service.calcular_score(...)` / `aplicar_matriz_decision(...)` para mostrar clase de riesgo en el perfil del cliente.
2. La UI no debe reimplementar ninguna validación de negocio (límites de cupo, clases de riesgo, atomicidad) — todo eso ya vive en `/services` y está probado; la capa `/ui` solo captura eventos, llama a los servicios y muestra resultados/errores.

---

*Última actualización: cierre completo del backend (`pos_service.py`, atomicidad compuesta, abono inicial, eliminación de bypass en RF-SCR-04). Generado por Claude a partir de la auditoría acumulada del proyecto.*