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
