import sqlite3
from typing import Optional, List
from models.producto import Producto

# Categorías válidas según el CHECK constraint de la tabla productos
CATEGORIAS_VALIDAS = ("canasta_basica", "cesta_mixta", "consumo_suntuario")


def _row_to_producto(row: sqlite3.Row) -> Producto:
    """Convierte una fila de sqlite3.Row al dataclass Producto con stock y stock_minimo como int."""
    return Producto(
        id=row["id"],
        codigo_barras=row["codigo_barras"],
        nombre=row["nombre"],
        categoria=row["categoria"],
        precio_venta=float(row["precio_venta"]),
        costo=float(row["costo"]),
        stock=int(row["stock"]),
        stock_minimo=int(row["stock_minimo"]),
        activo=bool(row["activo"]),
    )


def _validar_producto(
    nombre: str,
    categoria: str,
    precio_venta: float,
    costo: float,
    stock: float,
    stock_minimo: float,
) -> None:
    """
    Valida las reglas de negocio e integridad de los campos de un producto.
    Lanza ValueError si alguna validación falla.
    """
    if not nombre or not nombre.strip():
        raise ValueError("El nombre del producto no puede estar vacío.")
    if categoria not in CATEGORIAS_VALIDAS:
        raise ValueError(
            f"Categoría '{categoria}' no válida. Debe ser una de: {CATEGORIAS_VALIDAS}."
        )
    if precio_venta < 0:
        raise ValueError(f"El precio de venta no puede ser negativo (recibido: {precio_venta}).")
    if costo < 0:
        raise ValueError(f"El costo no puede ser negativo (recibido: {costo}).")
    if stock < 0:
        raise ValueError(f"El stock inicial no puede ser negativo (recibido: {stock}).")
    if stock_minimo < 0:
        raise ValueError(f"El stock mínimo no puede ser negativo (recibido: {stock_minimo}).")


def crear_producto(
    nombre: str,
    categoria: str,
    precio_venta: float,
    costo: float,
    conn: sqlite3.Connection,
    codigo_barras: Optional[str] = None,
    stock: float = 0.0,
    stock_minimo: float = 5.0,
) -> Producto:
    """
    Crea y persiste un nuevo producto en la base de datos (RF-INV-01).
    Aplica política de redondeo a entero consistente en BD y en el dataclass retornado.
    """
    _validar_producto(nombre, categoria, precio_venta, costo, stock, stock_minimo)

    stock_final = int(round(stock))
    stock_min_final = int(round(stock_minimo))

    # Verificar duplicado de código de barras manualmente para dar mensaje claro
    if codigo_barras is not None:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM productos WHERE codigo_barras = ?", (codigo_barras,)
        )
        if cursor.fetchone():
            raise ValueError(
                f"Ya existe un producto con el código de barras '{codigo_barras}'."
            )

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO productos (codigo_barras, nombre, categoria, precio_venta, costo, stock, stock_minimo, activo)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (codigo_barras, nombre.strip(), categoria, precio_venta, costo, stock_final, stock_min_final),
        )
        nuevo_id = cursor.lastrowid
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return Producto(
        id=nuevo_id,
        codigo_barras=codigo_barras,
        nombre=nombre.strip(),
        categoria=categoria,
        precio_venta=precio_venta,
        costo=costo,
        stock=stock_final,
        stock_minimo=stock_min_final,
        activo=True,
    )


def obtener_producto(producto_id: int, conn: sqlite3.Connection) -> Optional[Producto]:
    """
    Obtiene un producto activo por su ID. Retorna None si no existe o está inactivo.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM productos WHERE id = ? AND activo = 1", (producto_id,)
    )
    row = cursor.fetchone()
    return _row_to_producto(row) if row else None


def obtener_producto_por_codigo(
    codigo_barras: str, conn: sqlite3.Connection
) -> Optional[Producto]:
    """
    Obtiene un producto activo por su código de barras.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM productos WHERE codigo_barras = ? AND activo = 1", (codigo_barras,)
    )
    row = cursor.fetchone()
    return _row_to_producto(row) if row else None


def listar_productos(conn: sqlite3.Connection, solo_activos: bool = True) -> List[Producto]:
    """
    Lista todos los productos. Por defecto solo retorna los activos.
    """
    cursor = conn.cursor()
    if solo_activos:
        cursor.execute("SELECT * FROM productos WHERE activo = 1 ORDER BY nombre ASC")
    else:
        cursor.execute("SELECT * FROM productos ORDER BY nombre ASC")
    return [_row_to_producto(row) for row in cursor.fetchall()]


def actualizar_producto(
    producto_id: int,
    conn: sqlite3.Connection,
    nombre: Optional[str] = None,
    categoria: Optional[str] = None,
    precio_venta: Optional[float] = None,
    costo: Optional[float] = None,
    stock_minimo: Optional[float] = None,
    codigo_barras: Optional[str] = None,
) -> Producto:
    """
    Actualiza los campos del catálogo de un producto (RF-INV-01).
    Asegura consistencia de stock_minimo entero tanto en BD como en memoria.
    No modifica el stock directamente — usa ajustar_stock() para eso.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM productos WHERE id = ? AND activo = 1", (producto_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Producto ID {producto_id} no encontrado o inactivo.")

    # Valores actuales como base para validar
    nuevo_nombre = nombre.strip() if nombre is not None else row["nombre"]
    nueva_categoria = categoria if categoria is not None else row["categoria"]
    nuevo_precio = precio_venta if precio_venta is not None else float(row["precio_venta"])
    nuevo_costo = costo if costo is not None else float(row["costo"])
    nuevo_stock_minimo = stock_minimo if stock_minimo is not None else float(row["stock_minimo"])
    nuevo_codigo = codigo_barras if codigo_barras is not None else row["codigo_barras"]

    _validar_producto(nuevo_nombre, nueva_categoria, nuevo_precio, nuevo_costo, 0, nuevo_stock_minimo)
    nuevo_stock_min_int = int(round(nuevo_stock_minimo))

    # Verificar unicidad del nuevo código de barras si cambió
    if codigo_barras is not None and codigo_barras != row["codigo_barras"]:
        cursor.execute(
            "SELECT id FROM productos WHERE codigo_barras = ? AND id != ?",
            (codigo_barras, producto_id),
        )
        if cursor.fetchone():
            raise ValueError(
                f"Ya existe otro producto con el código de barras '{codigo_barras}'."
            )

    try:
        cursor.execute(
            """
            UPDATE productos
            SET nombre = ?, categoria = ?, precio_venta = ?, costo = ?,
                stock_minimo = ?, codigo_barras = ?
            WHERE id = ?
            """,
            (nuevo_nombre, nueva_categoria, nuevo_precio, nuevo_costo,
             nuevo_stock_min_int, nuevo_codigo, producto_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return Producto(
        id=producto_id,
        codigo_barras=nuevo_codigo,
        nombre=nuevo_nombre,
        categoria=nueva_categoria,
        precio_venta=nuevo_precio,
        costo=nuevo_costo,
        stock=int(row["stock"]),
        stock_minimo=nuevo_stock_min_int,
        activo=True,
    )


def ajustar_stock(
    producto_id: int,
    cantidad: float,
    conn: sqlite3.Connection,
) -> Producto:
    """
    Ajusta el stock de un producto sumando o restando una cantidad.
    Calcula stock_final = int(round(nuevo_stock)) una sola vez,
    usando ese mismo valor tanto en el UPDATE SQL como en el Producto retornado.
    Debe llamarse siempre dentro de la misma transacción que la venta.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM productos WHERE id = ? AND activo = 1", (producto_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Producto ID {producto_id} no encontrado o inactivo.")

    nuevo_stock = float(row["stock"]) + cantidad
    stock_final = int(round(nuevo_stock))
    if stock_final < 0:
        raise ValueError(
            f"Stock insuficiente para '{row['nombre']}'. "
            f"Disponible: {int(row['stock'])}, solicitado: {abs(int(cantidad))}."
        )

    cursor.execute(
        "UPDATE productos SET stock = ? WHERE id = ?",
        (stock_final, producto_id),
    )
    return Producto(
        id=producto_id,
        codigo_barras=row["codigo_barras"],
        nombre=row["nombre"],
        categoria=row["categoria"],
        precio_venta=float(row["precio_venta"]),
        costo=float(row["costo"]),
        stock=stock_final,
        stock_minimo=int(row["stock_minimo"]),
        activo=True,
    )


def desactivar_producto(producto_id: int, conn: sqlite3.Connection) -> bool:
    """
    Desactiva (baja lógica) un producto sin eliminar su historial en ventas.
    Retorna True si se desactivó exitosamente, False si no existía.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM productos WHERE id = ? AND activo = 1", (producto_id,)
    )
    if not cursor.fetchone():
        return False

    try:
        cursor.execute(
            "UPDATE productos SET activo = 0 WHERE id = ?", (producto_id,)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

    return True


def listar_alertas_stock(conn: sqlite3.Connection) -> List[Producto]:
    """
    Retorna todos los productos activos con stock <= stock_minimo (RF-INV-03).
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM productos
        WHERE activo = 1 AND stock <= stock_minimo
        ORDER BY stock ASC
        """
    )
    return [_row_to_producto(row) for row in cursor.fetchall()]
