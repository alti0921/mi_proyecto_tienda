# Documentación Técnica: Modelo de Base de Datos (Paso 1 - Actualizado)

## 1. Visión General de la Arquitectura de Base de Datos

El sistema utiliza **SQLite3** como motor relacional empotrado, garantizando integridad referencial mediante la ejecución obligatoria del comando `PRAGMA foreign_keys = ON;` al aperturar cada conexión. 

El diseño sigue una **arquitectura por capas** desacoplada, auditable y calibrada en función del **Motor Experto de Scoring Crediticio** y la especificación de requisitos del sistema (ERS). Modela la operación de Punto de Venta (POS), control de inventario con alertas de stock mínimo, gestión crediticia inmutable y evaluación del riesgo basada en reglas de negocio.

---

## 2. Matriz de Trazabilidad (Tablas vs. Requisitos Funcionales del ERS)

La siguiente tabla describe la correspondencia exacta entre los Requisitos Funcionales del ERS y las tablas y columnas implementadas en la base de datos relacional:

| Requisito Funcional | Descripción del Requisito | Tabla(s) Asociada(s) | Columnas Clave & Notas de Diseño |
| :--- | :--- | :--- | :--- |
| **RF-AUT-01** | Autenticación, control de acceso y gestión de roles de usuario | `usuarios` | `username` (único), `password_hash`, `rol` (`'admin'`, `'vendedor'`). |
| **RF-INV-02** | Gestión de inventario, categorías y umbrales de stock mínimo | `productos` | `categoria` (`'canasta_basica'`, `'cesta_mixta'`, `'consumo_suntuario'`), `stock_minimo` ($\ge 0$). |
| **RF-POS-02** | Registro de ventas con soporte para ítems de catálogo y ventas por monto global | `ventas`, `venta_detalle` | `venta_detalle.producto_id` es **NULLABLE** para registrar ítems sin ID de producto en ventas globales. |
| **RF-POS-03** | Selección y validación del tipo de pago en punto de venta | `ventas` | `tipo_pago` con restricción CHECK: (`'efectivo'`, `'nequi'`, `'credito'`). |
| **RF-CXC-01** | Gestión de perfil de clientes, saldos, líneas de crédito y nivel de vínculo | `clientes` | `limite_credito`, `saldo_actual`, `nivel_vinculo` (`'registro_completo'`, `'conocido_referido'`, `'solo_apodo'`). |
| **RF-CXC-02** | Registro inmutable en libro mayor de Cuentas por Cobrar (Cargos y Abonos) | `cuentas_por_cobrar` | Ledger Append-Only resguardado con **Triggers SQLite** e índice `idx_cxc_cliente_fecha`. |
| **RF-SCR-01** | Historial, desgloses ($SW_1, SW_2, SW_3$) y evaluación de Scoring (0-100 pts) | `clientes`, `scoring_historial` | `score_crediticio` ($0\text{-}100$), `categoria_riesgo` (`'A'`, `'B'`, `'C'`, `'D'`), columnas de desglose `sw1`, `sw2`, `sw3`. |

---

## 3. Detalle de Entidades y Esquema Relacional

### 3.1. `usuarios`
Control de acceso y autenticación al sistema POS y administrativo.
* `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `username` (`TEXT UNIQUE NOT NULL`)
* `password_hash` (`TEXT NOT NULL`)
* `nombre` (`TEXT NOT NULL`)
* `rol` (`TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin', 'vendedor'))`)
* `activo` (`INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))`)
* `created_at` (`DATETIME DEFAULT CURRENT_TIMESTAMP`)

### 3.2. `productos`
Gestiona el inventario y catálogo de productos con clasificación de impacto en scoring y alerta de desabastecimiento.
* `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `codigo_barras` (`TEXT UNIQUE`)
* `nombre` (`TEXT NOT NULL`)
* `categoria` (`TEXT NOT NULL CHECK (categoria IN ('canasta_basica', 'cesta_mixta', 'consumo_suntuario'))`)
* `precio_venta` (`REAL NOT NULL CHECK (precio_venta >= 0)`)
* `costo` (`REAL NOT NULL DEFAULT 0.0 CHECK (costo >= 0)`)
* `stock` (`INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)`)
* `stock_minimo` (`INTEGER NOT NULL DEFAULT 5 CHECK (stock_minimo >= 0)`)
* `activo` (`INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))`)
* `created_at` (`DATETIME DEFAULT CURRENT_TIMESTAMP`)

### 3.3. `clientes`
Expediente crediticio y nivel de relación cualitativa del cliente/micronegocio.
* `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `nombre` (`TEXT NOT NULL`)
* `telefono` (`TEXT`)
* `direccion` (`TEXT`)
* `limite_credito` (`REAL NOT NULL DEFAULT 0.0 CHECK (limite_credito >= 0)`)
* `saldo_actual` (`REAL NOT NULL DEFAULT 0.0 CHECK (saldo_actual >= 0)`)
* `score_crediticio` (`INTEGER NOT NULL DEFAULT 60 CHECK (score_crediticio BETWEEN 0 AND 100)`)
* `categoria_riesgo` (`TEXT NOT NULL DEFAULT 'B' CHECK (categoria_riesgo IN ('A', 'B', 'C', 'D'))`)
* `nivel_vinculo` (`TEXT NOT NULL DEFAULT 'solo_apodo' CHECK (nivel_vinculo IN ('registro_completo', 'conocido_referido', 'solo_apodo'))`)
* `activo` (`INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))`)
* `created_at` (`DATETIME DEFAULT CURRENT_TIMESTAMP`)

### 3.4. `ventas` y `venta_detalle`
Cabecera y desglose operacional de transacciones POS.
* `ventas.tipo_pago`: Restringido a `CHECK (tipo_pago IN ('efectivo', 'nequi', 'credito'))`.
* `venta_detalle.producto_id`: Campo **NULLABLE**. Si `producto_id IS NULL`, corresponde a una venta por monto global (conservando la descripción dada en `descripcion`).

### 3.5. `cuentas_por_cobrar` (Ledger Inmutable)
Libro mayor para contabilizar créditos (cargos) y pagos (abonos).
* `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `cliente_id` (`INTEGER NOT NULL REFERENCES clientes(id)`)
* `venta_id` (`INTEGER REFERENCES ventas(id)`)
* `tipo_movimiento` (`TEXT NOT NULL CHECK (tipo_movimiento IN ('cargo', 'abono'))`)
* `monto` (`REAL NOT NULL CHECK (monto > 0)`)
* `saldo_resultante` (`REAL NOT NULL CHECK (saldo_resultante >= 0)`)
* `descripcion` (`TEXT`)
* `fecha_movimiento` (`DATETIME DEFAULT CURRENT_TIMESTAMP`)

### 3.6. `scoring_historial`
Registro de trazabilidad y desglose analítico para auditoría del algoritmo de scoring.
* `id` (`INTEGER PRIMARY KEY AUTOINCREMENT`)
* `cliente_id` (`INTEGER NOT NULL REFERENCES clientes(id)`)
* `score_anterior` (`INTEGER NOT NULL`)
* `score_nuevo` (`INTEGER NOT NULL`)
* `categoria_anterior` (`TEXT`)
* `categoria_nueva` (`TEXT`)
* `sw1` (`REAL`) — Subvariable $W_1$: Comportamiento de Pago Histórico (40%)
* `sw2` (`REAL`) — Subvariable $W_2$: Frecuencia y Volumetría de Compra (35%)
* `sw3` (`REAL`) — Subvariable $W_3$: Confianza Relacional / Nivel de Vínculo (25%)
* `motivo` (`TEXT NOT NULL`)
* `fecha_calculo` (`DATETIME DEFAULT CURRENT_TIMESTAMP`)

---

## 4. Índices de Rendimiento

Para optimizar las consultas del estado de cuenta e historial financiero de los clientes, se cuenta con el índice:

```sql
CREATE INDEX idx_cxc_cliente_fecha ON cuentas_por_cobrar(cliente_id, fecha_movimiento);
```

---

## 5. Garantía de Inmutabilidad mediante Triggers Append-Only (`cuentas_por_cobrar`)

Para garantizar la audibilidad contable e impedir la alteración o borrado de saldos, la tabla `cuentas_por_cobrar` está protegida por dos triggers relacionales:

### Trigger `bloquear_edicion_cxc`
```sql
CREATE TRIGGER bloquear_edicion_cxc
BEFORE UPDATE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite editar registros.');
END;
```

### Trigger `bloquear_borrado_cxc`
```sql
CREATE TRIGGER bloquear_borrado_cxc
BEFORE DELETE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite eliminar registros.');
END;
```

---

## 6. Datos Semilla (Seed Data)

El script `db/schema.sql` ejecuta la inserción inicial limpia:
- **1 Usuario Administrador**: Username `admin`.
- **3 Productos de prueba**: `Arroz Superior 1kg` (`canasta_basica`, `stock_minimo=10`), `Aceite Vegetal 1L` (`cesta_mixta`, `stock_minimo=5`), `Vino Tinto Reserva 750ml` (`consumo_suntuario`, `stock_minimo=2`).
- **1 Cliente de prueba**: `Abarrotes y Novedades Doña María` (`score_crediticio=75`, `categoria_riesgo='B'`, `nivel_vinculo='conocido_referido'`, `limite_credito=1500.00`).
