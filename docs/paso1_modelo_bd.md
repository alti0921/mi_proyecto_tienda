# Documentación Técnica: Modelo de Base de Datos (Paso 1)

## 1. Visión General de la Arquitectura de Base de Datos

El sistema utiliza **SQLite3** como motor relacional empotrado, garantizando integridad referencial mediante la ejecución obligatoria del comando `PRAGMA foreign_keys = ON;` al aperturar cada conexión. 

El diseño sigue un enfoque de **arquitectura por capas** desacoplada y auditable, estructurando las entidades para soportar las operaciones fundamentales de Punto de Venta (POS), control de inventario categorizado, otorgamiento de crédito a micronegocios y evaluación heurística del riesgo crediticio.

---

## 2. Matriz de Trazabilidad (Tablas vs. Requisitos Funcionales del ERS)

La siguiente tabla describe la correspondencia entre los Requisitos Funcionales del ERS (Especificación de Requisitos del Sistema) y las tablas diseñadas en la base de datos relacional:

| Requisito Funcional | Descripción del Requisito | Tabla(s) Asociada(s) | Notas de Diseño e Integridad |
| :--- | :--- | :--- | :--- |
| **RF-AUT-01** | Autenticación, control de acceso y gestión de roles de usuario | `usuarios` | Almacena `username` único, hashes de contraseñas y roles (`admin`, `vendedor`). |
| **RF-INV-02** | Gestión de inventario con clasificación de productos por categoría | `productos` | `CHECK` constraint que restringe categorías a: `'canasta_basica'`, `'cesta_mixta'`, `'consumo_suntuario'`. |
| **RF-POS-02** | Registro detallado de ventas con soporte para ítems individuales y montos globales | `ventas`, `venta_detalle` | La columna `venta_detalle.producto_id` es **NULLABLE**, permitiendo registrar ítems sin ID de producto cuando la venta es por monto global. |
| **RF-POS-03** | Selección y validación del tipo de pago en punto de venta | `ventas` | `CHECK` constraint que restringe el tipo de pago a: `'efectivo'`, `'tarjeta'`, `'credito'`. |
| **RF-CXC-01** | Registro inmutable en libro mayor de Cuentas por Cobrar (Cargos y Abonos) | `cuentas_por_cobrar` | Protegida contra modificaciones y eliminaciones mediante **Triggers Append-Only**. |
| **RF-CXC-02** | Gestión de perfil de clientes, saldos pendientes y límites de crédito | `clientes` | Mantiene el estado financiero actual (`limite_credito`, `saldo_actual`) y categorización de riesgo. |
| **RF-SCR-01** | Historial, trazabilidad y justificación de variaciones en el Scoring Crediticio | `scoring_historial` | Registra los cambios de score (`score_anterior`, `score_nuevo`), categorías y motivos de ajuste. |

---

## 3. Detalle de Entidades y Esquema Relacional

### 3.1. `usuarios`
Permite el control de acceso al sistema POS y administración.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `username` (TEXT UNIQUE NOT NULL)
- `password_hash` (TEXT NOT NULL)
- `nombre` (TEXT NOT NULL)
- `rol` (TEXT NOT NULL, CHECK: 'admin' o 'vendedor')
- `activo` (INTEGER NOT NULL DEFAULT 1)

### 3.2. `productos`
Gestiona el catálogo de productos y su impacto en el scoring según la categoría del producto.
- `categoria` con restricción CHECK: `categoria IN ('canasta_basica', 'cesta_mixta', 'consumo_suntuario')`.
- Control de precio de venta, costo y stock mínimo no negativo (`stock >= 0`).

### 3.3. `clientes`
Almacena el expediente crediticio del cliente/micronegocio.
- `limite_credito` (REAL >= 0)
- `saldo_actual` (REAL >= 0)
- `score_crediticio` (INTEGER entre 300 y 850)
- `categoria_riesgo` (TEXT: 'Bajo', 'Medio', 'Alto')

### 3.4. `ventas` y `venta_detalle`
Cabecera y detalle de las transacciones POS.
- En `venta_detalle`, el campo `producto_id` es opcional (`NULLABLE`). Si `producto_id IS NULL`, la venta corresponde a una entrada rápida de "Monto Global", conservando la descripción manual en la columna `descripcion`.

### 3.5. `cuentas_por_cobrar` (Ledger Inmutable)
Contabiliza los movimientos de crédito (Cargos cuando compra a crédito, Abonos cuando realiza pagos).
- `tipo_movimiento` (TEXT: 'cargo', 'abono')
- `monto` (REAL > 0)
- `saldo_resultante` (REAL >= 0)

### 3.6. `scoring_historial`
Log de auditoría para algoritmos heurísticos de crédito.
- Guarda la transición del score crediticio y la razón del cálculo (ej. puntualidad en abonos, consumo de canasta básica, excedente en límite de crédito).

---

## 4. Garantía de Inmutabilidad mediante Triggers Append-Only (`cuentas_por_cobrar`)

Para garantizar el cumplimiento de normativas contables e impedir la alteración o falsificación de saldos en la tabla `cuentas_por_cobrar`, la base de datos implementa un patrón **Append-Only** (solo inserción) mediante dos triggers SQLite a nivel de motor:

### Trigger 1: `bloquear_edicion_cxc`
```sql
CREATE TRIGGER bloquear_edicion_cxc
BEFORE UPDATE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite editar registros.');
END;
```

### Trigger 2: `bloquear_borrado_cxc`
```sql
CREATE TRIGGER bloquear_borrado_cxc
BEFORE DELETE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite eliminar registros.');
END;
```

### Explicación Operativa de los Triggers:
1. **`BEFORE UPDATE` / `BEFORE DELETE`**: Interceptan cualquier sentencia SQL `UPDATE` o `DELETE` dirigida a la tabla `cuentas_por_cobrar` **antes** de que altere los datos en disco.
2. **`RAISE(ABORT, ...)`**: Aborta inmediatamente la transacción en curso, revierte cualquier cambio pendiente y arroja una excepción con un mensaje descriptivo.
3. **Auditabilidad Garantizada**: Todo ajuste a la cuenta de un cliente (descuento, corrección o abono) debe realizarse registrando una **nueva transacción contable** (`INSERT`), manteniendo una trazabilidad histórica del 100%.

---

## 5. Datos Semilla (Seed Data)

El script `db/schema.sql` incluye la inserción inicial de datos de desarrollo:
- **1 Usuario Administrador**: Username `admin`.
- **3 Productos de prueba**: Repartidos en las tres categorías requeridas (`canasta_basica`, `cesta_mixta`, `consumo_suntuario`).
- **1 Cliente de prueba**: Con score inicial de 680 (Riesgo Bajo) y línea de crédito de $1,500.00.
