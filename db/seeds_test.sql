-- ============================================================================
-- DATOS SEMILLA DE PRUEBA (Test Seed Data)
-- Para entornos de testing y desarrollo local (no ejecutar en producción)
-- ============================================================================

-- 3 Productos de prueba representativos con stock y stock_minimo
INSERT INTO productos (codigo_barras, nombre, categoria, precio_venta, costo, stock, stock_minimo, activo)
VALUES 
('7501000100011', 'Arroz Superior 1kg', 'canasta_basica', 25.00, 18.50, 100, 10, 1),
('7501000100028', 'Aceite Vegetal 1L', 'cesta_mixta', 48.00, 37.00, 50, 5, 1),
('7501000100035', 'Vino Tinto Reserva 750ml', 'consumo_suntuario', 220.00, 150.00, 15, 2, 1);

-- 1 Cliente Inicial de Prueba (Escala 0-100, Clase B, conocido_referido)
INSERT INTO clientes (nombre, telefono, direccion, limite_credito, saldo_actual, score_crediticio, categoria_riesgo, nivel_vinculo, activo)
VALUES ('Abarrotes y Novedades Doña María', '555-019-2834', 'Av. Hidalgo #102, Col. Centro', 1500.00, 0.00, 75, 'B', 'conocido_referido', 1);

-- Usuarios de Prueba para Testing y Desarrollo Local (no ejecutar en producción)
-- Administrador: admin / admin123
INSERT INTO usuarios (username, password_hash, nombre, rol, activo)
VALUES ('admin', 'sha256$a1b2c3d4e5f60718$9879a6c081970a685052bdaf0cba84347009c2f6f758c7a05257f5dcd6485ca8', 'Administrador del Sistema', 'admin', 1);

-- Vendedor: vendedor / vend123
INSERT INTO usuarios (username, password_hash, nombre, rol, activo)
VALUES ('vendedor', 'sha256$a1b2c3d4e5f60718$02c1e6c6218d17f6b83d239ddddd4b74d2fdbcbaf9f23df23f8a1515e95aeeda', 'Vendedor de Mostrador', 'vendedor', 1);

