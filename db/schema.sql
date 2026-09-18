-- Activar claves foráneas en SQLite
PRAGMA foreign_keys = ON;

-- Limpieza de tablas previas (en orden por dependencias)
DROP TABLE IF EXISTS scoring_historial;
DROP TABLE IF EXISTS cuentas_por_cobrar;
DROP TABLE IF EXISTS venta_detalle;
DROP TABLE IF EXISTS ventas;
DROP TABLE IF EXISTS clientes;
DROP TABLE IF EXISTS productos;
DROP TABLE IF EXISTS usuarios;

-- 1. Tabla: usuarios
-- Requisito: RF-AUT-01 (Autenticación y roles)
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL DEFAULT 'vendedor' CHECK (rol IN ('admin', 'vendedor')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla: productos
-- Requisito: RF-INV-02 (Gestión de inventario con clasificación de categorías)
CREATE TABLE productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_barras TEXT UNIQUE,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL CHECK (categoria IN ('canasta_basica', 'cesta_mixta', 'consumo_suntuario')),
    precio_venta REAL NOT NULL CHECK (precio_venta >= 0),
    costo REAL NOT NULL DEFAULT 0.0 CHECK (costo >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla: clientes
-- Requisito: RF-CXC-02 (Gestión de clientes y línea de crédito)
CREATE TABLE clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    telefono TEXT,
    direccion TEXT,
    limite_credito REAL NOT NULL DEFAULT 0.0 CHECK (limite_credito >= 0),
    saldo_actual REAL NOT NULL DEFAULT 0.0 CHECK (saldo_actual >= 0),
    score_crediticio INTEGER NOT NULL DEFAULT 500 CHECK (score_crediticio BETWEEN 300 AND 850),
    categoria_riesgo TEXT NOT NULL DEFAULT 'Medio' CHECK (categoria_riesgo IN ('Bajo', 'Medio', 'Alto')),
    activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla: ventas
-- Requisitos: RF-POS-02, RF-POS-03 (Registro de ventas y tipos de pago)
CREATE TABLE ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    cliente_id INTEGER,
    tipo_pago TEXT NOT NULL CHECK (tipo_pago IN ('efectivo', 'tarjeta', 'credito')),
    total REAL NOT NULL CHECK (total >= 0),
    monto_pagado REAL NOT NULL DEFAULT 0.0 CHECK (monto_pagado >= 0),
    fecha_venta DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- 5. Tabla: venta_detalle
-- Requisito: RF-POS-02 (Detalle de venta; producto_id es NULLABLE para permitir venta por monto global)
CREATE TABLE venta_detalle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL,
    producto_id INTEGER, -- NULLABLE intencionalmente para admitir ítems globales
    descripcion TEXT NOT NULL,
    cantidad REAL NOT NULL CHECK (cantidad > 0),
    precio_unitario REAL NOT NULL CHECK (precio_unitario >= 0),
    subtotal REAL NOT NULL CHECK (subtotal >= 0),
    FOREIGN KEY (venta_id) REFERENCES ventas(id) ON DELETE CASCADE,
    FOREIGN KEY (producto_id) REFERENCES productos(id)
);

-- 6. Tabla: cuentas_por_cobrar
-- Requisito: RF-CXC-01 (Registro inmutable / Append-Only de cargos y abonos)
CREATE TABLE cuentas_por_cobrar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    venta_id INTEGER,
    tipo_movimiento TEXT NOT NULL CHECK (tipo_movimiento IN ('cargo', 'abono')),
    monto REAL NOT NULL CHECK (monto > 0),
    saldo_resultante REAL NOT NULL CHECK (saldo_resultante >= 0),
    descripcion TEXT,
    fecha_movimiento DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id),
    FOREIGN KEY (venta_id) REFERENCES ventas(id)
);

-- 7. Tabla: scoring_historial
-- Requisito: RF-SCR-01 (Trazabilidad e historial de cálculos de scoring)
CREATE TABLE scoring_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    score_anterior INTEGER NOT NULL,
    score_nuevo INTEGER NOT NULL,
    categoria_anterior TEXT,
    categoria_nueva TEXT,
    motivo TEXT NOT NULL,
    fecha_calculo DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
);

-- ============================================================================
-- TRIGGERS DE INMUTABILIDAD (Append-Only para cuentas_por_cobrar)
-- ============================================================================

-- Trigger 1: Bloquear cualquier intento de UPDATE en cuentas_por_cobrar
CREATE TRIGGER bloquear_edicion_cxc
BEFORE UPDATE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite editar registros.');
END;

-- Trigger 2: Bloquear cualquier intento de DELETE en cuentas_por_cobrar
CREATE TRIGGER bloquear_borrado_cxc
BEFORE DELETE ON cuentas_por_cobrar
BEGIN
    SELECT RAISE(ABORT, 'Operación no permitida: La tabla cuentas_por_cobrar es inmutable (Append-Only). No se permite eliminar registros.');
END;

-- ============================================================================
-- DATOS SEMILLA (Seed Data)
-- ============================================================================

-- Usuario Administrador Inicial (password hash simulado para desarrollo)
INSERT INTO usuarios (username, password_hash, nombre, rol, activo)
VALUES ('admin', 'scrypt:32768:8:1$hash_admin_secret_key$', 'Administrador del Sistema', 'admin', 1);

-- 3 Productos de prueba representativos de las distintas categorías
INSERT INTO productos (codigo_barras, nombre, categoria, precio_venta, costo, stock, activo)
VALUES 
('7501000100011', 'Arroz Superior 1kg', 'canasta_basica', 25.00, 18.50, 100, 1),
('7501000100028', 'Aceite Vegetal 1L', 'cesta_mixta', 48.00, 37.00, 50, 1),
('7501000100035', 'Vino Tinto Reserva 750ml', 'consumo_suntuario', 220.00, 150.00, 15, 1);

-- 1 Cliente Inicial de Prueba
INSERT INTO clientes (nombre, telefono, direccion, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, activo)
VALUES ('Abarrotes y Novedades Doña María', '555-019-2834', 'Av. Hidalgo #102, Col. Centro', 1500.00, 0.00, 680, 'Bajo', 1);
