import sqlite3
import pytest
import os
from services.inventario_service import (
    crear_producto,
    obtener_producto,
    obtener_producto_por_codigo,
    listar_productos,
    actualizar_producto,
    ajustar_stock,
    desactivar_producto,
    listar_alertas_stock,
)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")

@pytest.fixture
def db_conn():
    """
    Fixture que crea una base de datos SQLite en memoria e inicializa
    el esquema completo definido en db/schema.sql.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    
    yield conn
    conn.close()


def test_crear_producto_exitoso(db_conn):
    """Verifica la creación exitosa de un producto con todos sus atributos."""
    prod = crear_producto(
        nombre="Leche Entera 1L",
        categoria="canasta_basica",
        precio_venta=4.50,
        costo=3.20,
        conn=db_conn,
        codigo_barras="7701234567890",
        stock=20.0,
        stock_minimo=5.0,
    )

    assert prod.id is not None
    assert prod.nombre == "Leche Entera 1L"
    assert prod.categoria == "canasta_basica"
    assert prod.precio_venta == 4.50
    assert prod.costo == 3.20
    assert prod.stock == 20
    assert isinstance(prod.stock, int)
    assert prod.stock_minimo == 5
    assert isinstance(prod.stock_minimo, int)
    assert prod.activo is True
    assert prod.codigo_barras == "7701234567890"


def test_crear_producto_codigo_barras_duplicado(db_conn):
    """Verifica que no se permita registrar dos productos con el mismo código de barras."""
    crear_producto(
        nombre="Galletas Festival",
        categoria="cesta_mixta",
        precio_venta=1.20,
        costo=0.80,
        conn=db_conn,
        codigo_barras="7709999999999",
        stock=15.0,
    )

    with pytest.raises(ValueError, match="Ya existe un producto con el código de barras"):
        crear_producto(
            nombre="Galletas Recreo",
            categoria="cesta_mixta",
            precio_venta=1.10,
            costo=0.75,
            conn=db_conn,
            codigo_barras="7709999999999",
            stock=10.0,
        )


def test_crear_producto_validaciones_negocio(db_conn):
    """Verifica que se rechacen nombres vacíos, categorías no válidas o números negativos."""
    # Nombre vacío
    with pytest.raises(ValueError, match="no puede estar vacío"):
        crear_producto("", "canasta_basica", 10.0, 5.0, db_conn)

    # Categoría inválida
    with pytest.raises(ValueError, match="Categoría 'invalida' no válida"):
        crear_producto("Producto X", "invalida", 10.0, 5.0, db_conn)

    # Precio negativo
    with pytest.raises(ValueError, match="precio de venta no puede ser negativo"):
        crear_producto("Producto X", "canasta_basica", -1.0, 5.0, db_conn)

    # Costo negativo
    with pytest.raises(ValueError, match="costo no puede ser negativo"):
        crear_producto("Producto X", "canasta_basica", 10.0, -2.0, db_conn)

    # Stock negativo
    with pytest.raises(ValueError, match="stock inicial no puede ser negativo"):
        crear_producto("Producto X", "canasta_basica", 10.0, 5.0, db_conn, stock=-5.0)

    # Stock mínimo negativo
    with pytest.raises(ValueError, match="stock mínimo no puede ser negativo"):
        crear_producto("Producto X", "canasta_basica", 10.0, 5.0, db_conn, stock_minimo=-1.0)


def test_obtener_producto_por_id_y_codigo(db_conn):
    """Verifica la consulta de producto por ID y por código de barras."""
    creado = crear_producto(
        nombre="Atún en Aceite",
        categoria="canasta_basica",
        precio_venta=6.0,
        costo=4.5,
        conn=db_conn,
        codigo_barras="7705555555555",
        stock=30.0,
    )

    # Consulta por ID
    por_id = obtener_producto(creado.id, db_conn)
    assert por_id is not None
    assert por_id.id == creado.id
    assert por_id.nombre == "Atún en Aceite"
    assert isinstance(por_id.stock, int)

    # Consulta por Código de Barras
    por_codigo = obtener_producto_por_codigo("7705555555555", db_conn)
    assert por_codigo is not None
    assert por_codigo.id == creado.id

    # Inexistente
    assert obtener_producto(9999, db_conn) is None
    assert obtener_producto_por_codigo("0000000000000", db_conn) is None


def test_actualizar_producto(db_conn):
    """Verifica la actualización parcial de atributos de catálogo de un producto."""
    prod = crear_producto(
        nombre="Jugo de Naranja 500ml",
        categoria="cesta_mixta",
        precio_venta=2.50,
        costo=1.80,
        conn=db_conn,
        codigo_barras="7708888888888",
        stock=12.0,
        stock_minimo=4.0,
    )

    actualizado = actualizar_producto(
        prod.id,
        db_conn,
        precio_venta=3.00,
        costo=2.00,
        stock_minimo=6.0,
    )

    assert actualizado.precio_venta == 3.00
    assert actualizado.costo == 2.00
    assert actualizado.stock_minimo == 6
    assert isinstance(actualizado.stock_minimo, int)
    assert actualizado.nombre == "Jugo de Naranja 500ml"  # Sin cambios
    assert actualizado.stock == 12  # El stock no se toca en actualizar_producto
    assert isinstance(actualizado.stock, int)


def test_actualizar_producto_codigo_duplicado(db_conn):
    """Verifica que al actualizar no se permita asignar un código de barras ya ocupado por otro producto."""
    p1 = crear_producto("Prod 1", "cesta_mixta", 2.0, 1.0, db_conn, codigo_barras="111")
    p2 = crear_producto("Prod 2", "cesta_mixta", 3.0, 2.0, db_conn, codigo_barras="222")

    with pytest.raises(ValueError, match="Ya existe otro producto con el código de barras"):
        actualizar_producto(p2.id, db_conn, codigo_barras="111")


def test_ajustar_stock(db_conn):
    """Verifica el incremento y decremento transaccional de stock."""
    prod = crear_producto(
        nombre="Pan Tajado",
        categoria="canasta_basica",
        precio_venta=3.50,
        costo=2.50,
        conn=db_conn,
        stock=10.0,
    )

    # Entrada de inventario (+5)
    ajustado = ajustar_stock(prod.id, 5.0, db_conn)
    db_conn.commit()
    assert ajustado.stock == 15
    assert isinstance(ajustado.stock, int)

    # Salida por venta (-3)
    ajustado = ajustar_stock(prod.id, -3.0, db_conn)
    db_conn.commit()
    assert ajustado.stock == 12
    assert isinstance(ajustado.stock, int)

    # Salida mayor al disponible -> Error de stock insuficiente
    with pytest.raises(ValueError, match="Stock insuficiente"):
        ajustar_stock(prod.id, -20.0, db_conn)


def test_ajustar_stock_fraccionario_consistencia_bd_y_dataclass(db_conn):
    """
    Verifica que al ajustar stock con cantidades fraccionarias:
    1. Se aplique el redondeo int(round(...)) de forma uniforme.
    2. El objeto retornado en memoria coincida exactamente con el valor persistido en SQLite.
    """
    prod = crear_producto(
        nombre="Queso Costeño por Peso",
        categoria="canasta_basica",
        precio_venta=12.0,
        costo=8.0,
        conn=db_conn,
        stock=10.0,
    )
    cursor = db_conn.cursor()

    # Primer ajuste fraccionario: 10 - 0.5 = 9.5 -> round = 10 (o 9.5 round par = 10 / round(9.5) = 10)
    # En Python: round(9.5) == 10, pero 10 + (-0.6) = 9.4 -> 9
    # Probemos con -0.5:
    prod_ajustado_1 = ajustar_stock(prod.id, -0.5, db_conn)
    db_conn.commit()

    cursor.execute("SELECT stock FROM productos WHERE id = ?", (prod.id,))
    stock_bd_1 = cursor.fetchone()["stock"]

    assert isinstance(prod_ajustado_1.stock, int)
    assert isinstance(stock_bd_1, int)
    assert prod_ajustado_1.stock == stock_bd_1

    # Segundo ajuste fraccionario: stock_bd_1 - 0.5
    prod_ajustado_2 = ajustar_stock(prod.id, -0.5, db_conn)
    db_conn.commit()

    cursor.execute("SELECT stock FROM productos WHERE id = ?", (prod.id,))
    stock_bd_2 = cursor.fetchone()["stock"]

    assert isinstance(prod_ajustado_2.stock, int)
    assert isinstance(stock_bd_2, int)
    assert prod_ajustado_2.stock == stock_bd_2


def test_desactivar_producto_baja_logica(db_conn):
    """Verifica que desactivar producto realice baja lógica y no aparezca en consultas activas."""
    prod = crear_producto(
        nombre="Cigarrillos Paquete",
        categoria="consumo_suntuario",
        precio_venta=8.0,
        costo=6.0,
        conn=db_conn,
        stock=5.0,
    )

    resultado = desactivar_producto(prod.id, db_conn)
    assert resultado is True

    # No debe retornar al consultar activo
    assert obtener_producto(prod.id, db_conn) is None

    # No debe aparecer en listar_productos activos
    activos = listar_productos(db_conn, solo_activos=True)
    ids_activos = [p.id for p in activos]
    assert prod.id not in ids_activos

    # Pero sí debe existir si consultamos todos (historial conservado)
    todos = listar_productos(db_conn, solo_activos=False)
    ids_todos = [p.id for p in todos]
    assert prod.id in ids_todos


def test_listar_alertas_stock_bajo(db_conn):
    """Verifica que se listen correctamente los productos cuyo stock <= stock_minimo."""
    # Producto con stock bajo (3 <= 5)
    p_bajo = crear_producto(
        nombre="Azúcar 1kg",
        categoria="canasta_basica",
        precio_venta=2.0,
        costo=1.5,
        conn=db_conn,
        stock=3.0,
        stock_minimo=5.0,
    )

    # Producto con stock exacto al mínimo (5 <= 5)
    p_limite = crear_producto(
        nombre="Sal 500g",
        categoria="canasta_basica",
        precio_venta=1.0,
        costo=0.6,
        conn=db_conn,
        stock=5.0,
        stock_minimo=5.0,
    )

    # Producto con stock holgado (20 > 5)
    p_ok = crear_producto(
        nombre="Harina de Maíz",
        categoria="canasta_basica",
        precio_venta=2.2,
        costo=1.7,
        conn=db_conn,
        stock=20.0,
        stock_minimo=5.0,
    )

    alertas = listar_alertas_stock(db_conn)
    ids_alertas = [p.id for p in alertas]

    assert p_bajo.id in ids_alertas
    assert p_limite.id in ids_alertas
    assert p_ok.id not in ids_alertas


def test_producto_propiedades_calculadas(db_conn):
    """Verifica las propiedades calculadas @property: margen y alerta_stock_bajo."""
    prod = crear_producto(
        nombre="Café Molido 250g",
        categoria="canasta_basica",
        precio_venta=7.50,
        costo=5.00,
        conn=db_conn,
        stock=4.0,
        stock_minimo=5.0,
    )

    # Margen = 7.50 - 5.00 = 2.50
    assert prod.margen == 2.50
    # Stock (4) <= stock_minimo (5) -> alerta activa
    assert prod.alerta_stock_bajo is True

    # Si ajustamos stock a 10
    prod_ajustado = ajustar_stock(prod.id, 6.0, db_conn)
    assert prod_ajustado.stock == 10
    assert isinstance(prod_ajustado.stock, int)
    assert prod_ajustado.alerta_stock_bajo is False
