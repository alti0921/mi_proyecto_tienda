# Contexto Técnico del Proyecto — Sistema de Scoring Crediticio para Tiendas de Barrio

**Proyecto:** Desarrollo de un sistema de información con motor analítico de scoring crediticio para la gestión operativa y financiera de micronegocios minoristas de Barranquilla
**Autores:** Altime Andrés Heredia Jaimes, Andrés Felipe Segura Angulo
**Repositorio:** `alti0921/mi_proyecto_tienda`
**Última actualización de este documento:** 2026-09-30
**Propósito:** Consolidar el estado técnico completo del proyecto en un solo documento, para que cualquier sesión futura (con Claude, con Gemini/Antigravity, o con los propios estudiantes) tenga el contexto necesario sin tener que re-derivarlo desde cero.

> ⚠️ **Regla de oro para cualquier IA o desarrollador que continúe este proyecto:** antes de escribir código nuevo, leer este documento completo, en particular la Sección 4 (reglas y parches ya corregidos), la Sección 8 (wireframes de Fase 2, con controles y permisos por rol) y la Sección 10 (arquitectura real de `/ui` y el patrón de rol reactivo). No repetir bugs ya corregidos aquí.

---

## 1. Resumen del estado actual y módulos finalizados

### 1.1 Fases del proyecto y su estado

| Fase | Contenido | Estado |
|---|---|---|
| **Fase 1** — Diagnóstico | 15 encuestas de campo a tenderos, calibración empírica de variables (P-Q1 a P-Q9), ajuste de Alcance/Delimitaciones, respuesta a observaciones metodológicas del profesor | ✅ Cerrada y aprobada |
| **Fase 2** — Diseño de arquitectura | Blueprint de Arquitectura (4 capas), Modelo Entidad-Relación (E-R) | ✅ Completa |
| **Fase 2** — Wireframes | 5 pantallas: Login, POS, Perfil cliente/CxC, Inventario, Reportes — documento `Wireframes_Fase2.docx` con diagramas de caja, tabla de trazabilidad RF por componente y permisos por rol | ✅ **Completa y cerrada formalmente** |
| **Fase 3** — Construcción modular (backend) | `db/schema.sql`, `/models`, `services/scoring_service.py`, `services/inventario_service.py`, `services/cxc_service.py`, `services/pos_service.py`, `services/auth_service.py`, `services/reportes_service.py`, `tests/` | ✅ Auditado, corregido y con **62/62 tests backend en verde** |
| **Fase 3** — Construcción de interfaz | `/ui` (Tkinter): `app.py`, `sesion.py`, `estilos.py`, `widgets_comunes.py` y las 5 pantallas (`login.py`, `pos.py`, `perfil_cliente.py`, `inventario.py`, `reportes.py`) | ✅ **Completa y cerrada formalmente — 84/84 tests en verde** (ver Sección 10) |
| **Fase 3** — Comprobante en PDF (RF-CXC-04) | Generación de comprobante en PDF de formato tirilla térmica 80mm vía `services/reportes_service.py` con `reportlab` e integración en UI | ✅ **Completo y certificado — tirilla térmica 80mm con cajero auditable** |

**Nota de clasificación de fases:** el código ya construido (`schema.sql`, `/models`, `/services`, `/tests`, `/ui`) técnicamente pertenece a Fase 3 (Construcción modular), no a los entregables formales de Fase 2. El Blueprint, el E-R y los wireframes son los tres entregables de Fase 2, y los tres están cerrados. El backend y la interfaz gráfica se tratan como "avance de Fase 3 fundamentado en un diseño de Fase 2 ya formalizado".

### 1.2 Módulos de código finalizados y verificados

| Módulo | Estado | Cobertura de tests |
|---|---|---|
| `db/schema.sql` (7 tablas) | ✅ Verificado línea por línea, incluye `usuarios.username COLLATE NOCASE` y `cuentas_por_cobrar.usuario_id` | N/A (fuente de verdad) |
| `models/*.py` (dataclasses puras, incluye `Usuario` y `CuentaPorCobrar.usuario_id`) | ✅ Verificado contra schema, exportado en `models/__init__.py` | Implícita vía tests de servicios |
| `services/scoring_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_scoring.py` — 8 tests |
| `services/inventario_service.py` | ✅ Auditado y corregido (ver Sección 4) | `tests/test_inventario.py` — 13 tests |
| `services/cxc_service.py` | ✅ Auditado y corregido, incluye `actualizar_cliente`, `buscar_clientes` y `usuario_id` auditable | `tests/test_cxc.py` — 13 tests |
| `services/pos_service.py` | ✅ Auditado y corregido — backend de ventas completo, propaga `usuario_id` | `tests/test_pos.py` — 12 tests |
| `services/auth_service.py` | ✅ Construido y auditado — hash SHA-256 + salt, `COLLATE NOCASE` | `tests/test_auth.py` — 8 tests |
| `services/reportes_service.py` | ✅ Construido y auditado — arqueo, consolidado de cartera y `generar_comprobante_pdf` (80mm) | `tests/test_reportes.py` — 8 tests |
| `ui/*.py` (5 pantallas + andamiaje) | ✅ Construido y auditado (ver Sección 10) | `tests/test_ui.py` — 22 tests |
| **Total suite** | ✅ **84/84 passed** | Confirmado en terminal (pytest 9.1.1, Python 3.12.10) |

### 1.3 Documentos de Fase 2 entregados

- **Blueprint de Arquitectura del Sistema** — describe la arquitectura de 4 capas (Presentación/Lógica de negocio/Dominio/Persistencia), justificada contra RNF-05, RNF-03 y Testabilidad.
- **Modelo Entidad-Relación (E-R)** — construido 1:1 desde `db/schema.sql`, incluye notas de cardinalidad (FKs nullable) y diccionario de datos con trazabilidad a requisitos funcionales (RF).
- **`Wireframes_Fase2.docx`** — 5 pantallas dibujadas (diagramas de caja de baja fidelidad), cada una con tabla de componentes mapeados a su RF y a la función pública de `/services` que lo satisface. Ver estructura completa en Sección 8.

---

## 2. Decisiones clave de arquitectura y lógica de código acordadas

1. **Sistema experto basado en reglas, NO Machine Learning.** El motor de scoring traduce directamente los puntos de quiebre identificados empíricamente en la Fase 1 (15 encuestas) en cortes de puntuación. No hay entrenamiento de modelos ni aprendizaje estadístico.

2. **Arquitectura en 4 capas (Layered Architecture):**
   - `/ui` (Presentación) → `/services` (Lógica de negocio) → `/models` (Dominio, dataclasses puras sin acoplamiento a SQLite) → `/db` (Persistencia, SQLite + schema.sql)
   - Justificación: RNF-05 (integridad centralizada en schema.sql vía FK/CHECK), RNF-03 (rendimiento — `/services` optimizable sin tocar UI), Testabilidad (`/tests` valida `/services` y `/models` sin simular UI).

3. **Patrón Append-Only para `cuentas_por_cobrar`.** Ningún registro de movimiento de cartera se edita ni se borra jamás; se aplica mediante triggers SQL a nivel de base de datos (`bloquear_edicion_cxc`, `bloquear_borrado_cxc`), no solo por convención en el código. Esto es lo que garantiza RNF-05 y RF-CXC-01/02 de forma verificable, y se refleja en el wireframe (Pantalla 3) como una tabla sin controles de editar/borrar.

4. **`Abono` NO es una tabla separada.** Es una vista/filtro lógico de `cuentas_por_cobrar` donde `tipo_movimiento = 'abono'`. `CuentaPorCobrar` (el dataclass) es un DTO/Read-Model, nunca se persiste directamente como objeto — se inserta como filas con `tipo_movimiento IN ('cargo','abono')`.

5. **No existe una tabla `inventario_movimiento`.** Los cambios de stock se aplican mediante `UPDATE productos SET stock = stock ± cantidad WHERE id = ?` **dentro de la misma transacción** que genera la venta o el ajuste manual de inventario.

6. **Atomicidad transaccional obligatoria, estandarizada vía `auto_commit: bool = True`.** Toda función que muta estado compartido (`registrar_cargo`, `registrar_abono`, `registrar_snapshot`, `ajustar_stock`) expone `auto_commit: bool = True` por defecto — para que una llamada aislada persista sola y de forma segura — y los orquestadores (`pos_service.registrar_venta`) la fijan explícitamente en `False` para centralizar un único `commit`/`rollback` de la transacción compuesta. Esta convención quedó formalizada como **política transversal del proyecto** (ver Sección 4, parches #13 y #17).

7. **Manejo unificado de errores de negocio vía `ValueError` en español.** Toda validación de reglas de negocio (cupo excedido, stock insuficiente, producto/cliente no encontrado, clase de riesgo bloqueada) se comunica como `ValueError` con mensaje descriptivo en español, listo para desplegarse tal cual en el área roja de error de la UI — nunca como valor booleano ni código numérico. Ver parche #18 (migración de `desactivar_producto`) como el caso más reciente de esta unificación.

8. **Separación conceptual P-Q6 vs. P-Q9 (fundamental para el scoring):**
   - **P-Q6** define el **plazo pactado inicial** de pago tras la compra: `PLAZO_ESTANDAR_DIAS = 8` días.
   - **P-Q9** define la **tolerancia de mora adicional** *después* de vencido ese plazo, antes de congelar el crédito.
   - La variable operativa correcta es la **mora efectiva**: `dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS)`. El umbral literal de P-Q9 (7 a 10 días, 66.7% de tenderos congela) se aplica **directamente** sobre esta mora efectiva.
   - `PLAZO_ESTANDAR_DIAS` y esta clasificación de 4 bandas se **reutilizan literalmente** (no se reimplementan) en `reportes_service.obtener_consolidado_cartera()`, para que el reporte de cartera y el motor de scoring nunca diverjan sobre la clasificación de un mismo cliente (ver Sección 3.7).

9. **Redondeo direccional conservador en inventario**, para evitar la congelación por "banker's rounding" de Python:
   - Salidas/ventas (`cantidad < 0`) → `math.floor()`
   - Entradas (`cantidad >= 0`) → `math.ceil()`
   - Formalizado como **RS-05** ("Aprovisionamiento de Inventario en Unidades Enteras") en el ERS, y reflejado en el wireframe de Inventario (Pantalla 4) como un stepper que solo acepta enteros.

10. **Escala de scoring: 0–100 puntos / categorías A-B-C-D** (no escala FICO 300-850, no etiquetas Bajo-Medio-Alto). Fórmula ponderada:
    `S = 0.40×SW1 + 0.35×SW2 + 0.25×SW3`

11. **Protocolo Cold-Start:** clientes nuevos o con menos de 3 ciclos de pago reciben un cupo semilla **sugerido** (nunca persistido automáticamente) en vez del cálculo ponderado completo — pero nunca si ya tienen saldo activo en mora más allá del plazo pactado. La confirmación operativa del cupo (`pos_service.asignar_limite_credito`) está restringida a rol `admin` en la UI (Pantalla 3).

---

## 3. Fragmentos y estructuras de código críticas (NO ROMPER)

### 3.1 `db/schema.sql` — fuente de verdad de columnas y tipos

```sql
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
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
-- ventas: CHECK (tipo_pago != 'credito' OR cliente_id IS NOT NULL)
-- venta_detalle.producto_id es NULLABLE (permite venta por monto global sin producto catalogado, RF-POS-02)

CREATE TABLE cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    venta_id INTEGER REFERENCES ventas(id),
    usuario_id INTEGER REFERENCES usuarios(id),
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

### 3.2 `services/scoring_service.py` — motor de decisión (final, 8/8 tests en verde)

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
    # Desactiva cold-start si saldo_actual > 0 AND dias_mora > PLAZO_ESTANDAR_DIAS
    # Si total_ciclos(abonos) >= 3 -> ya no es cold-start
    # cupo_semilla por nivel_vinculo: registro_completo=$50.000/A, conocido_referido=$40.000/B, solo_apodo=$30.000/C
    # plazo_dias = 15
    ...

def calcular_score(cliente_id, conn) -> tuple[float, str]:
    # S = 0.40*SW1 + 0.35*SW2 + 0.25*SW3, con bypass de cold-start cuando aplica
    ...

def registrar_snapshot(cliente_id, sw1, sw2, sw3, score_ant, score_nuevo, cat_ant, cat_nueva, motivo, conn, auto_commit: bool = True) -> ScoringHistorial:
    # int(round(...)) al castear antes de INSERT/UPDATE
    # Atómico: INSERT en scoring_historial + UPDATE de clientes.score_crediticio/categoria_riesgo
    ...
```

### 3.3 `services/cxc_service.py` — ledger de cartera (final, 12/12 tests en verde)

```python
NIVELES_VINCULO_VALIDOS = ("registro_completo", "conocido_referido", "solo_apodo")

def crear_cliente(nombre, conn, telefono=None, direccion=None,
                   nivel_vinculo="solo_apodo", limite_credito=0.0) -> Cliente:
    # Valida nombre no vacío, nivel_vinculo permitido, limite_credito >= 0
    # INSERT con saldo_actual=0.0, score_crediticio=60, categoria_riesgo='B' por defecto
    ...

def obtener_cliente(cliente_id, conn) -> Optional[Cliente]: ...

def buscar_clientes(termino: str, conn: sqlite3.Connection, solo_activos: bool = True) -> List[Cliente]:
    """
    RF-CXC-01. WHERE activo = 1 AND (nombre LIKE ? OR telefono LIKE ? OR direccion LIKE ?)
    con bindings parametrizados en tupla (patron, patron, patron) — misma convención que
    inventario_service.buscar_productos. solo_activos=True por defecto.
    """
    ...

def actualizar_cliente(cliente_id, conn, nombre=None, telefono=None, direccion=None,
                        nivel_vinculo=None, activo=None) -> Cliente:
    """
    RF-CXC-01, RF-CXC-03. Actualiza únicamente datos demográficos y de vínculo.
    Valida nivel_vinculo contra NIVELES_VINCULO_VALIDOS. Aísla por completo
    limite_credito y saldo_actual -- ningún parámetro de esta función puede tocarlos
    (esos campos solo cambian vía pos_service.asignar_limite_credito y
    registrar_cargo/registrar_abono respectivamente).
    """
    ...

def registrar_cargo(cliente_id, monto, conn, venta_id=None, descripcion=None, auto_commit: bool = True) -> CuentaPorCobrar:
    """
    Salvaguarda de cupo (RF-CXC-06): rechaza CUALQUIER cargo cuyo saldo
    resultante supere clientes.limite_credito -- SIN excepción para
    limite_credito == 0.0 (cliente sin cupo asignado = cupo cero, no cupo infinito).
    """
    nuevo_saldo = round(saldo_actual + monto, 2)
    if nuevo_saldo > limite_credito:
        raise ValueError(f"El cargo excede el límite de crédito del cliente "
                          f"(Cupo: {limite_credito}, Saldo resultante: {nuevo_saldo}).")
    ...

def registrar_abono(cliente_id, monto, conn, venta_id=None, descripcion=None, auto_commit: bool = True) -> CuentaPorCobrar:
    # monto <= 0 o monto > saldo_actual -> ValueError
    ...

def consultar_saldo(cliente_id, conn) -> float: ...
def obtener_historial_cxc(cliente_id, conn) -> List[CuentaPorCobrar]: ...
```

**Separación de responsabilidades confirmada:** `pos_service.py` es el "cerebro comercial" — evalúa `calcular_score()` fresco, aplica la matriz de decisión (bloqueo Clase D, abono mínimo Clase C) y autoriza o no la venta. `cxc_service.py` es el ledger — nunca decide, solo ejecuta y protege la integridad contable con una salvaguarda dura de cupo como última línea de defensa.

**Importante — `evaluar_cold_start()` NO persiste el cupo semilla.** Es una función de solo lectura: devuelve una sugerencia en memoria (`cupo_semilla`, `plazo_dias=15`), pero nunca ejecuta `UPDATE clientes SET limite_credito = ...`. La asignación efectiva requiere `pos_service.asignar_limite_credito()`, restringida a rol `admin` en el wireframe de Perfil/CxC.

### 3.4 `services/pos_service.py` — orquestador transaccional de ventas (final, 12/12 tests en verde, backend completo)

```python
def asignar_limite_credito(cliente_id: int, nuevo_limite: float, conn: sqlite3.Connection) -> Cliente:
    """Confirmación operativa y auditable del cupo (cierra RF-SCR-02). Acción independiente,
    no compuesta dentro de registrar_venta. Restringida a rol=admin en la UI."""
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
    items: List[Union[LineaVentaInput, Dict[str, Any]]],
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
       a. inventario_service.ajustar_stock(producto_id, -cantidad, conn, auto_commit=False)
       b. INSERT ventas, INSERT venta_detalle
       c. Si credito: monto_a_fiar = round(total - monto_pagado, 2)
          cxc_service.registrar_cargo(cliente_id, monto_a_fiar, conn, venta_id, auto_commit=False)
          scoring_service.registrar_snapshot(..., auto_commit=False)
       d. conn.commit() unificado / except: conn.rollback() + re-raise
    """
    ...
```

**Composición transaccional:** `registrar_cargo`, `registrar_abono`, `registrar_snapshot` y `ajustar_stock` reciben todas `auto_commit: bool = True` (política transversal, ver Sección 2.6). Llamadas aisladas/tests siguen comiteando solas; `pos_service.py` las invoca con `auto_commit=False` para que el commit/rollback quede centralizado en `registrar_venta`. Verificado con `test_atomicidad_post_cargo_fallo_en_snapshot`.

**Abono inicial en venta a crédito:** el cargo a `cuentas_por_cobrar` se calcula sobre `monto_a_fiar = total - monto_pagado`, nunca sobre `total` completo.

### 3.5 `services/inventario_service.py` — gestión de stock (final, 13/13 tests en verde)

```python
import math

def listar_productos(conn) -> List[Producto]:
    # activo=1 por defecto, ORDER BY nombre ASC
    ...

def buscar_productos(termino: str, conn) -> List[Producto]:
    # LIKE ? parametrizado sobre nombre o codigo_barras; término vacío -> catálogo activo completo
    ...

def listar_alertas_stock(conn) -> List[Producto]:
    # WHERE activo = 1 AND stock <= stock_minimo -- alimenta el badge global y el filtro
    # "Stock bajo" del wireframe de Inventario (RF-INV-03)
    ...

def crear_producto(nombre, categoria, precio_venta, costo, stock_inicial, stock_minimo, conn, codigo_barras=None) -> Producto:
    # Valida nombre no vacío, categoria in ('canasta_basica','cesta_mixta','consumo_suntuario'),
    # valores >= 0, redondea stock/stock_minimo a enteros, valida unicidad de codigo_barras
    ...

def actualizar_producto(producto_id, conn, nombre=None, categoria=None, precio_venta=None,
                         costo=None, stock_minimo=None, codigo_barras=None) -> Producto:
    # Aísla el stock físico (solo cambia vía ajustar_stock); valida unicidad de codigo_barras
    ...

def desactivar_producto(producto_id: int, conn: sqlite3.Connection) -> Producto:
    """
    Baja lógica (activo=0), preserva integridad referencial en venta_detalle.
    Migrado de retorno bool a ValueError(f"Producto ID {producto_id} no encontrado
    o inactivo.") -- unifica el manejo de errores con actualizar_producto,
    actualizar_cliente y asignar_limite_credito (ver Sección 4, parche #18).
    """
    ...

def ajustar_stock(producto_id: int, cantidad: float, conn: sqlite3.Connection, auto_commit: bool = True) -> Producto:
    """
    cantidad > 0 = entrada, cantidad < 0 = salida (el controlador de UI combina el
    selector Entrada/Salida + la magnitud del stepper en este único valor con signo
    antes de llamar la función).
    Redondeo direccional conservador:
    - Salida (cantidad < 0): math.floor(nuevo_stock)
    - Entrada (cantidad >= 0): math.ceil(nuevo_stock)
    Valida disponibilidad física en salidas:
      ValueError(f"Stock insuficiente para '{nombre}'. Disponible: {disponible}, solicitado: {solicitado}.")
    auto_commit: bool = True -- mismo patrón transversal que registrar_cargo/registrar_abono/
    registrar_snapshot; pos_service.registrar_venta() lo fija en False.
    """
    ...
```

### 3.6 `services/auth_service.py` — autenticación (final, 8/8 tests en verde)

```python
import hashlib
import hmac
import secrets

def hashear_password(password: str) -> str:
    # sha256$<salt_hex>$<hash_hex>, salt = secrets.token_hex(16)
    ...

def autenticar_usuario(username: str, password: str, conn: sqlite3.Connection) -> Optional[Usuario]:
    """
    username_limpio = username.strip().lower(); comparado contra usuarios.username,
    que ahora tiene COLLATE NOCASE en el schema -- evita el bug de usuarios con
    mayúsculas quedando inaccesibles (ver Sección 4, parche #16).
    Verificación con hmac.compare_digest (resistente a timing attacks).
    Retorna None de forma genérica ante: usuario inexistente, password incorrecto,
    o cuenta inactiva -- sin distinguir la causa (previene enumeración de usuarios).
    """
    ...
```

### 3.7 `services/reportes_service.py` — consolidados operativos (final, 4/4 tests en verde)

```python
def obtener_arqueo_diario(fecha: Optional[str], conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    RF-REP-01. fecha en 'YYYY-MM-DD' o 'now' (por defecto). Consolida:
    - ventas_efectivo, ventas_nequi, ventas_credito (neto financiado)
    - anticipos_credito (efectivo recibido al fiar), abonos_cxc (recaudo del día)
    - total_efectivo_en_caja = ventas_efectivo + anticipos_credito + abonos_cxc
    - total_ingresos_dia = total_efectivo_en_caja + ventas_nequi
    - movimientos: lista cronológica (hora, tipo, método, monto, efectivo ingresado,
      cliente, descripción), sin acciones de edición
    Verificado en test_obtener_arqueo_diario_consolidado_completo: efectivo $20.000 +
    Nequi $15.000 + crédito $50.000 (anticipo $10.000 / financiado $40.000) + abonos
    $15.000 -> caja física exacta $45.000, ingresos totales $60.000.
    """
    ...

def obtener_consolidado_cartera(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    RF-REP-02. Única fuente de verdad: importa y reutiliza literalmente
    PLAZO_ESTANDAR_DIAS, calcular_score() y aplicar_matriz_decision() de
    scoring_service -- no hardcodea días ni duplica lógica de riesgo.
    dias_mora_efectiva = max(0, dias_transcurridos - PLAZO_ESTANDAR_DIAS), clasificado en:
    - vigente_0_3       (0-3 días,  verde)
    - preventiva_4_6    (4-6 días,  amarillo)
    - congelada_7_10    (7-10 días, naranja, Clase C)
    - critica_mas_10    (>10 días,  rojo, Clase D / bloqueado)
    Retorna total_cartera_por_cobrar, total_deudores, resumen_por_banda,
    conteo_por_banda y la lista de deudores (cliente, saldo, dias_mora, clase,
    estado_banda). Excluye clientes con saldo $0.
    """
    ...
```

### 3.8 Modelos de dominio confirmados

- `models/producto.py` → `Producto`: `stock: int`, `stock_minimo: int`, más `@property margen` y `@property alerta_stock_bajo`.
- `models/cuenta_por_cobrar.py` → `CuentaPorCobrar` (DTO/Read-Model, no se persiste directo) y `Abono` (NO es tabla — filtro de `cuentas_por_cobrar` donde `tipo_movimiento='abono'`).
- `models/cliente.py` → `Cliente`, con `@property cupo_disponible = max(0.0, round(limite_credito - saldo_actual, 2))`.
- `models/usuario.py` → `Usuario` (incluye `rol`), usado por `auth_service.autenticar_usuario()`.
- Los 7 dataclasses (`Cliente`, `Producto`, `Venta`/`VentaDetalle`, `CuentaPorCobrar`/`Abono`, `ScoringHistorial`, `Usuario`) exportados en `models/__init__.py`.

---

## 4. Reglas especiales y parches ya corregidos (NO reintroducir estos bugs)

| # | Bug | Corrección aplicada | Verificación |
|---|---|---|---|
| 1 | **Escala FICO incorrecta**: `score_crediticio` se implementó inicialmente en 300-850 / Bajo-Medio-Alto | Migrado a escala 0-100 / categorías A-B-C-D, calibrada empíricamente | Confirmado en schema.sql |
| 2 | **`tipo_pago` con valores incorrectos**: incluía `'tarjeta'` y le faltaba `'nequi'` | Corregido a `('efectivo', 'nequi', 'credito')` | Confirmado en schema.sql y E-R |
| 3 | **Cold-Start indefinido**: un cliente con 0 abonos y deuda impaga se quedaba en Cold-Start para siempre | Chequeo agregado: `saldo_actual > 0` y `dias_mora > PLAZO_ESTANDAR_DIAS` → forzar `es_cold_start=False` | Test `test_cliente_moroso_sin_abonos` |
| 4 | **V1.1 perdió nivel intermedio** al añadir el plazo de gracia de 8 días | Recalibrado a 4 niveles (100/70/30/0) sobre mora efectiva | Test `test_v1_1_mora_efectiva_bordes` |
| 5-6 | **Truncamiento y "banker's rounding" de stock**: `int()`/`round()` estándar perdían o congelaban stock fraccional | `math.floor()` en salidas, `math.ceil()` en entradas | Test `test_ajustar_stock_fraccionario_consistencia_bd_y_dataclass` |
| 7 | **`ceil()` en entradas sobreestima inventario** (limitación menor, no bloqueante) | Documentada como **RS-05** en el ERS y en el wireframe de Inventario (stepper entero) | Aceptado explícitamente |
| 8 | **Fragmento de guía de arquitectura obsoleto** con nombres de campo viejos (`nombre_apodo`, `cupo_asignado`, etc.) | Confirmado como copy-paste accidental, no usado activamente | Confirmado por el usuario |
| 9 | **Fixture de test desactualizado** (`-8 días` caía en "al día" en vez de Clase C) | Fixture actualizado a `-12 días` | Verificado en la suite |
| 10 | **Traducción confusa "12-15 días calendario equivalentes"** | Eliminada — se aplica el rango de P-Q9 directamente sobre `dias_mora_efectiva` | Sincronizado en 4 documentos |
| 11 | **`ventas` sin restricción de `cliente_id` en ventas a crédito** | `CHECK (tipo_pago != 'credito' OR cliente_id IS NOT NULL)` | Test `test_venta_credito_requiere_cliente_integrity_error` |
| 12 | **Guarda `limite_credito > 0` dejaba sin protección a clientes nuevos** (`limite_credito=0.0` por defecto) | Eliminada la guarda; `nuevo_saldo > limite_credito` se aplica siempre | Test `test_registrar_cargo_cliente_sin_cupo_asignado_rechaza_cualquier_cargo` |
| 13 | **Commits anidados rompían la atomicidad compuesta** en `registrar_cargo`/`registrar_abono`/`registrar_snapshot` | `auto_commit: bool = True` en las tres; `pos_service` las invoca con `False` | Test `test_atomicidad_post_cargo_fallo_en_snapshot` |
| 14 | **Venta a crédito con abono inicial cobraba de más** (usaba `total` en vez de saldo neto) | `monto_a_fiar = round(total - monto_pagado, 2)`; valida `0 <= monto_pagado < total` para crédito | Test `test_venta_credito_con_abono_inicial_registra_solo_saldo_pendiente` |
| 15 | **Bypass potencial en RF-SCR-04**: parámetro `abono_previo_verificado: bool = False` en `_validar_credito_clase_c` | Eliminado por completo; función 100% determinista contra la BD | Confirmado en la firma pública de `registrar_venta` |
| 16 | **`autenticar_usuario()` sin `COLLATE NOCASE`**: `username.strip().lower()` comparado contra columna case-sensitive — un username futuro con mayúsculas quedaría inaccesible | `COLLATE NOCASE` agregado a `usuarios.username` en `db/schema.sql` | Confirmado en schema y suite 48/48 (momento de la introducción de `auth_service.py`) |
| 17 | **`ajustar_stock()` no seguía la convención transversal de `auto_commit`**: la primera versión delegaba el commit siempre al caller, sin exponer el parámetro — riesgo de que una llamada aislada futura (p. ej. desde Inventario) olvidara el `conn.commit()` manual y el ajuste no persistiera en disco | Estandarizado `auto_commit: bool = True`; `pos_service.registrar_venta()` lo fija en `False` explícitamente | Test `test_ajustar_stock_auto_commit_delegado` (commit `09fa84c`) |
| 18 | **`desactivar_producto()` retornaba `bool`** en vez de excepción: un `False` (producto no encontrado) no caía en el manejo genérico de `ValueError` del controlador de UI, arriesgando un fallo silencioso en el botón "Desactivar" | Migrado a `ValueError(f"Producto ID {producto_id} no encontrado o inactivo.")`, unificando con `actualizar_producto`, `actualizar_cliente` y `asignar_limite_credito` | Confirmado por Antigravity, incluido en la suite 57/57 |
| 19 | **(Patrón de `/ui`, no de `/services`) Restricciones de rol evaluadas una sola vez al construir el `Frame`**: el patrón multi-frame apilado (Sección 10) crea las 5 pantallas **una sola vez** y las reutiliza con `.tkraise()`. Si un widget restringido por rol (`BotonRestringidoPorRol`, la pestaña "Cartera/CxC") solo evaluara `sesion.usuario_actual.rol` en su `__init__`, un segundo login con otro rol **dentro de la misma ejecución de la app** (sin reiniciar el proceso) dejaría el control con el permiso del primer usuario | Se estandarizó un hook `al_mostrar()` invocado por `App.navegar_a()` en cada navegación, que dispara `BotonRestringidoPorRol.actualizar_estado()` y el bloqueo/desbloqueo de pestañas del `ttk.Notebook` de Reportes — la restricción se re-evalúa en caliente en cada entrada a la pantalla, nunca una sola vez | Tests `test_cambio_de_usuario_actualiza_permisos_en_caliente` y `test_reportes_bloqueo_reactivo_pestana_cartera_admin_vs_vendedor`, ambos simulando login→logout→login con rol distinto en la misma instancia de `App` |

---

## 5. Estado de la sincronización documental (4 documentos + código)

Confirmado por el usuario y verificado por Claude que los siguientes 4 frentes documentales están alineados con el código real (`calcular_v1_1`, `PLAZO_ESTANDAR_DIAS = 8`):

1. **Documento metodológico / tesis** (Fase de Desarrollo por Objetivos) — explicita la separación P-Q6/P-Q9.
2. **Documento de Sustentación** (Sección 1: Variables y Ponderaciones) — elimina la equivalencia "12-15 días calendario".
3. **Matriz de Variables y Ponderaciones Calibrada** (`docs/matriz_scoring.md` + Word) — columna de referencia de campo actualizada.
4. **ERS (IEEE-830)** — RF-SCR-01, RF-CXC-06 (nueva), RF-SCR-02 (corregida), RF-POS-04 (nueva) y RF-REP-01/02 sincronizados.

Commit de referencia: `fix(scoring): alinear V1.1 a rangos directos de mora efectiva (0-3, 4-6, 7-10, >10) segun P-Q9` en rama `master`.

**Nits menores no bloqueantes, aún sin corregir:**
- RF-INV-01 todavía dice "SKU" en vez de "codigo_barras" (el nombre real de la columna).
- RS-05 podría reflejarse también en la sección de Delimitaciones del documento de tesis formal, no solo en el ERS.

---

## 6. ✅ Cierre de `cxc_service.py` — cambios en el ERS

**Cambios formales al ERS (decisión tomada: Opción A — el sistema sugiere, el tendero confirma):**

**Nueva cláusula `RF-CXC-06`:**

| Campo | Contenido |
|---|---|
| ID | RF-CXC-06 |
| Módulo | CRM / Fiados |
| Nombre | Bloqueo por Cupo Excedido |
| Descripción | El sistema debe rechazar el registro de cualquier cargo a crédito cuyo saldo resultante supere el límite de crédito (cupo) asignado al cliente. Un cliente sin cupo asignado explícitamente (límite de crédito en $0) no debe poder recibir ningún cargo fiado, sin excepción. |
| Trazabilidad | Vinculado a RF-CXC-05 (Visualización de Cupo) |
| Prioridad | Alta |

**`RF-SCR-02` corregida** (antes implicaba persistencia automática del cupo semilla):

> **Redacción corregida:** "Para clientes sin historial, el sistema evaluará únicamente V3.1 y **sugerirá** al tendero un cupo semilla entre \$30.000 y \$50.000 COP, según el nivel de vínculo del cliente, válido para los primeros 3 ciclos de pago oportunos. La asignación efectiva del cupo al perfil del cliente **requiere confirmación operativa del tendero** (rol admin); el sistema no debe persistir el cupo de forma automática sin esa confirmación."

---

## 7. Nueva cláusula `RF-POS-04` (pago parcial en venta a crédito)

Agregada al ERS a raíz del hallazgo del bug #14 (Sección 4):

| Campo | Contenido |
|---|---|
| ID | RF-POS-04 |
| Módulo | POS |
| Nombre | Registro de Abono Inicial en Venta a Crédito |
| Descripción | Cuando una venta se registra con `tipo_pago='credito'` y el cliente entrega un monto en efectivo al momento de la venta (`monto_pagado > 0`), el sistema debe cargar a `cuentas_por_cobrar` únicamente el saldo neto financiado (`total - monto_pagado`), nunca el total de la venta. Debe validarse `0 ≤ monto_pagado < total`; si `monto_pagado ≥ total`, el sistema debe exigir un tipo de pago de contado en su lugar. |
| Trazabilidad | Vinculado a RF-POS-01, RF-CXC-06 |
| Prioridad | Alta |

---

## 8. ✅ Wireframes de Fase 2 — las 5 pantallas (`Wireframes_Fase2.docx`)

Documento completo: título + 5 pantallas, cada una con diagrama de caja de baja fidelidad, sección de "Distribución espacial" y tabla de trazabilidad Componente → Comportamiento → RF. Diseñadas y validadas visualmente en chat una por una, en el orden acordado, antes de incorporarse al `.docx`.

### 8.1 Pantalla 1 — Login / Autenticación
- Campos Usuario / Contraseña (con alternador mostrar/ocultar), área de error genérica única (no distingue causa, previene enumeración de usuarios).
- Botón "Iniciar sesión" → `auth_service.autenticar_usuario(username, password, conn)`.
- El `Usuario(rol)` retornado controla qué controles quedan visibles/habilitados en el resto de pantallas.
- **RF trazado:** RF-AUT-01.

### 8.2 Pantalla 2 — POS (Punto de Venta)
- Panel izquierdo (~60%): buscador de producto, botón "Venta x Monto" (venta sin producto catalogado), carrito editable, total fijo abajo.
- Panel derecho (~40%): selector de cliente + cupo (total/usado/disponible), tipo de pago (Efectivo/Nequi/Crédito), monto pagado, cambio a devolver, botón "Confirmar Venta", área de error unificada.
- **RF trazados:** RF-POS-01, RF-POS-02, RF-POS-03, RF-POS-04, RF-CXC-05, RF-CXC-06, RF-SCR-03, RF-SCR-04.
- **Backend:** `pos_service.registrar_venta(...)` como único punto de entrada.

### 8.3 Pantalla 3 — Perfil de Cliente / CxC
- Panel izquierdo (~55%): ficha del cliente (nombre/teléfono/dirección/nivel de vínculo vía `actualizar_cliente`), badge Score + Clase de Riesgo (color por clase), bloque de cupo con sugerencia Cold-Start precargada, campo "Nuevo cupo" + botón "Confirmar/Asignar Cupo" **restringido a rol=admin** (deshabilitado en gris para vendedor).
- Panel derecho (~45%): historial CxC append-only (sin editar/borrar), formulario "Registrar Abono" disponible para admin y vendedor, área de error de abono.
- **RF trazados:** RF-CXC-01 a 06, RF-SCR-01 a 06.
- **Backend:** `cxc_service.buscar_clientes/obtener_cliente/actualizar_cliente/registrar_abono/obtener_historial_cxc`, `scoring_service.calcular_score/aplicar_matriz_decision/evaluar_cold_start`, `pos_service.asignar_limite_credito`.
- **Nota de arquitectura:** el comprobante PDF por fila (RF-CXC-04) queda pendiente de `services/reportes_service.py` en su función de exportación — el botón se mantiene diagramado con un stub/visor de texto formateado mientras tanto.

### 8.4 Pantalla 4 — Gestión de Inventario
- Panel izquierdo (~62%): catálogo con buscador, filtro "Stock bajo", badge global de alertas (`listar_alertas_stock`), fila resaltada en ámbar para productos con `stock_actual ≤ stock_minimo`.
- Panel derecho (~38%), 3 bloques: Crear Producto (admin), Editar Precio/Costo/Mínimo + Desactivar (admin), Ajustar Stock con selector Entrada(+)/Salida(−) y stepper de **enteros** (admin y vendedor).
- **RF trazados:** RF-INV-01, RF-INV-02, RF-INV-03, RS-05.
- **Backend:** `inventario_service.listar_productos/buscar_productos/listar_alertas_stock/crear_producto/actualizar_producto/desactivar_producto/ajustar_stock`.

### 8.5 Pantalla 5 — Reportes Operativos
- Organización por pestañas (tabs) sobre un único contenedor — no paneles lado a lado, para que cada tabla dense use el 100% del ancho.
- **Tab 1 — Arqueo/Cierre Diario** (admin y vendedor): selector de fecha, 5 tarjetas KPI (Efectivo/Nequi/Crédito/Abonos CxC/TOTAL efectivo en caja resaltada), tabla de detalle cronológico.
- **Tab 2 — Cartera/CxC** (**exclusiva de admin**): filtros por clase y rango de mora, 4 tarjetas de banda con semáforo de color (vigente/preventiva/congelada/crítica) + tarjeta de Total Cartera, tabla de deudores ordenable.
- **RF trazados:** RF-REP-01, RF-REP-02.
- **Backend:** `reportes_service.obtener_arqueo_diario(fecha, conn)`, `reportes_service.obtener_consolidado_cartera(conn)` — este último reutiliza literalmente `PLAZO_ESTANDAR_DIAS`, `calcular_score()` y `aplicar_matriz_decision()` de `scoring_service` como única fuente de verdad para las 4 bandas de mora.

### 8.6 Matriz de permisos por rol (consolidada de las 5 pantallas)

| Acción | admin | vendedor |
|---|---|---|
| Iniciar sesión, POS (registrar venta) | ✅ | ✅ |
| Ver ficha de cliente, registrar abono | ✅ | ✅ |
| Asignar/confirmar cupo de cliente | ✅ | ❌ (deshabilitado en gris) |
| Crear producto, editar precio/costo/mínimo, desactivar producto | ✅ | ❌ (bloque deshabilitado en gris) |
| Ajustar stock (entrada/salida) | ✅ | ✅ |
| Tab Arqueo/Cierre Diario | ✅ | ✅ (su propio turno) |
| Tab Cartera/CxC (consolidado global de riesgo) | ✅ | ❌ (pestaña deshabilitada) |

---

## 9. ✅ Fase 3 — Backend certificado (57/57) como base de la construcción de `/ui`

**Backend 100% cerrado:** `db/schema.sql`, `/models`, `scoring_service.py`, `inventario_service.py`, `cxc_service.py`, `pos_service.py`, `auth_service.py` y `reportes_service.py` — todos auditados línea por línea, con atomicidad verificada de punta a punta (`auto_commit` estandarizado en las 4 funciones transaccionales) y sin ninguna vía de bypass de las reglas de negocio (RF-SCR-03/04, RF-CXC-06).

**Fase 2 100% cerrada:** Blueprint, E-R y las 5 pantallas de `Wireframes_Fase2.docx`, con cada componente trazado a su RF y a la función pública de `/services` que lo satisface (ver Sección 8).

Sobre esta base se construyó `/ui` (Tkinter), documentada completa en la Sección 10.

---

## 10. ✅ Fase 3 — `/ui` en Tkinter, construida y certificada (79/79 tests en verde)

Las 5 pantallas se construyeron en 5 hitos incrementales (Login → POS → Perfil/CxC → Inventario → Reportes), cada uno auditado por Claude contra los wireframes de la Sección 8 antes de aprobar el siguiente. Commits de referencia: `ac2f1d5` (Hito 1), `39fee6b` (Hito 2), `360d2c5` (Hito 3), `8afdd22` (Hito 4), `1185ac9` (Hito 5).

### 10.1 Estructura de archivos

```
ui/
├── app.py                 # Ventana raíz (tk.Tk), conn persistente, SesionActual única,
│                           # stack multi-frame apilado, App.navegar_a(nombre) -> hook al_mostrar() + tkraise()
├── sesion.py               # SesionActual(conn): usuario_actual, iniciar_sesion()/cerrar_sesion(),
│                           # @property es_admin, @property rol_actual
├── estilos.py              # Paleta centralizada (ttk.Style): COLORES_SCORING (A/B/C/D),
│                           # colores de error/alerta, tipografía Segoe UI
├── widgets_comunes.py       # AreaError, BotonRestringidoPorRol, BarraSuperior (todas reutilizadas
│                           # sin modificación en las 5 pantallas)
└── pantallas/
    ├── login.py             # RF-AUT-01
    ├── pos.py                # RF-POS-01 a 04, RF-CXC-05/06, RF-SCR-03/04
    ├── perfil_cliente.py     # RF-CXC-01 a 06, RF-SCR-01 a 06
    ├── inventario.py         # RF-INV-01 a 03, RS-05
    └── reportes.py           # RF-REP-01, RF-REP-02
```

### 10.2 Decisión arquitectónica clave: sin capa `/controladores` separada

Cada `Pantalla*` es un único `tk.Frame` que actúa como vista **y** manejador de evento. La lógica de negocio vive 100% en `/services`; el `Frame` solo arma el payload, llama la función, y en un `try/except ValueError` vuelca el resultado o el mensaje de error en su `AreaError`. Confirmado en la práctica a lo largo de los 5 hitos: ninguna pantalla necesitó una capa intermedia.

### 10.3 Patrón de rol reactivo (la lección más importante de esta fase)

El patrón de navegación es multi-frame **apilado y persistente**: las 5 pantallas se crean una sola vez al iniciar `App`, y `navegar_a()` solo hace `tkraise()` sobre instancias ya existentes. Esto significa que, dentro de una misma ejecución del programa, un segundo login con un rol distinto **reutiliza el mismo objeto `Frame`** que ya existía con el primer usuario.

Por eso, **todo control restringido por rol se re-evalúa en cada navegación, nunca solo en su construcción**: `App.navegar_a()` invoca `pantalla.al_mostrar()` antes de `tkraise()`, y ese hook dispara `BotonRestringidoPorRol.actualizar_estado()` y el bloqueo/desbloqueo de la pestaña "Cartera/CxC" del `ttk.Notebook` en Reportes. Ver parche #19 (Sección 4) — este fue el hallazgo real más importante detectado durante la auditoría de `/ui`, verificado con pruebas dedicadas que simulan login→logout→login con rol distinto dentro de la misma instancia de `App`.

### 10.4 Resumen por pantalla (comportamiento certificado, más allá de lo ya descrito en Sección 8)

- **Login:** único punto que abre la `conn` compartida de la sesión; produce el `Usuario(rol)` que el resto de la app consume vía `sesion.usuario_actual`.
- **POS:** carrito como lista en memoria (`self._carrito`, nunca leído desde el widget visual al confirmar); el badge de Clase de Riesgo/cupo en la ficha del cliente es **puramente informativo** — el botón "Confirmar Venta" permanece siempre `state="normal"`, y la única autoridad de rechazo es el `ValueError` que devuelve `pos_service.registrar_venta()` (verificado con `test_pos_boton_confirmar_activo_y_rechazo_clase_d_backend`). Tras cada venta: carrito vacío, catálogo y cupo del cliente refrescados.
- **Perfil de Cliente/CxC:** formularios de ficha demográfica y de asignación de cupo desacoplados, cada uno con su propio manejador y `AreaError`. El badge Score/Clase se recalcula (`calcular_score()` + `aplicar_matriz_decision()` frescos) tanto tras un abono **como tras editar `nivel_vinculo`** (que alimenta `SW3` directamente) — verificado con `test_perfil_cliente_cambio_vinculo_recalcula_score_en_caliente`. Historial CxC sin ningún binding de edición/borrado.
- **Inventario:** patrón maestro-detalle (`<<TreeviewSelect>>` alimenta los 3 bloques de acción); selector Entrada/Salida + magnitud del stepper se combinan en un entero con signo antes de llamar `ajustar_stock(..., auto_commit=True)`; categoría de producto restringida a `ttk.Combobox(state="readonly")`.
- **Reportes:** `ttk.Notebook` con bloqueo reactivo de la pestaña Cartera/CxC (ver 10.3); Tab 1 se refresca al cambiar de fecha y al reentrar a la pestaña; Tab 2 hace una única consulta a `obtener_consolidado_cartera()` y filtra por clase/mora en memoria, sin golpear la base de datos por cada cambio de filtro.

### 10.5 Suite de pruebas de interfaz (`tests/test_ui.py`) — 22 tests

Cubren: ciclo de vida de `SesionActual`, comportamiento de `AreaError`, habilitación/deshabilitación de `BotonRestringidoPorRol`, inicialización y navegación de `App`, el flujo completo de Login, la conmutación de permisos en caliente entre roles, catálogo/carrito/ventas del POS (efectivo, Nequi y crédito con anticipo parcial), edición de ficha y recálculo de scoring en Perfil de Cliente, cascada completa tras un abono, maestro-detalle y ajuste de stock con signo en Inventario, y el bloqueo reactivo de pestaña más el cálculo de KPIs en Reportes.

### 10.6 Implementación completa de RF-CXC-04 (Comprobante en PDF Real)

Se implementó exitosamente `reportes_service.generar_comprobante_pdf(movimiento_id, conn)` utilizando `reportlab`. Genera una tirilla térmica estándar de 80mm con:
- Cabecera y datos del micronegocio.
- Folio `#MOV-{id:06d}` y fecha inmutable.
- Cajero histórico auditable (obtenido vía `cuentas_por_cobrar.usuario_id` o 'No registrado' en registros legados).
- Cliente, teléfono y concepto.
- Reconstrucción determinista del saldo anterior:
  `saldo_anterior = saldo_resultante + monto` (abono) o `saldo_resultante - monto` (cargo).
- Detalle financiero con alineación decimal y nuevo saldo.
- La Pantalla 3 (`perfil_cliente.py`) invoca la generación y lanza el visor predeterminado del sistema operativo (`os.startfile` en Windows / `subprocess` en Unix), reportando cualquier incidencia en `AreaError`.

---

*Última actualización: cierre formal de Fase 3 completa al 100% — backend (62/62) y `/ui` en Tkinter (22/22) para un total de **84/84 tests en verde**, incluyendo la migración de `cuentas_por_cobrar.usuario_id` y la emisión de comprobantes en PDF térmico 80mm (RF-CXC-04). Generado a partir de la auditoría acumulada del proyecto.*