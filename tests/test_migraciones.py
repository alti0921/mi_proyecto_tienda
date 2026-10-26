import glob
import sqlite3
import pytest
from db.connection import get_connection
from db.migraciones import aplicar_migraciones


def test_get_connection_activa_foreign_keys(tmp_path):
    """Verifica que get_connection active siempre PRAGMA foreign_keys = ON."""
    db_file = str(tmp_path / "test_fk.db")
    conn = get_connection(db_file)
    try:
        cur = conn.cursor()
        fk = cur.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
    finally:
        conn.close()


def test_migracion_plazo_en_base_legada(tmp_path):
    """
    Verifica la migración 001_plazo_pactado_dias sobre una base de datos con esquema legado:
    - Retorna ['001_plazo_pactado_dias'].
    - Agrega plazo_pactado_dias con valor por defecto 8 a los clientes existentes.
    - Preserva intactos todos los datos previos.
    - Genera exactamente un respaldo .bak-* antes de mutar la base.
    - La copia de respaldo no contiene la columna nueva.
    - Una segunda llamada es idempotente (retorna [] y no genera nuevo respaldo).
    - El CHECK en la columna añadida rechaza valores inválidos (ej. plazo 10 lanza IntegrityError).
    """
    db_file = str(tmp_path / "tienda_legada.db")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    # Esquema antiguo de clientes (sin plazo_pactado_dias)
    conn.execute("""
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
    """)

    conn.execute("""
        INSERT INTO clientes (nombre, telefono, limite_credito, saldo_actual)
        VALUES ('Cliente Uno', '3001234567', 100000.0, 5000.0)
    """)
    conn.execute("""
        INSERT INTO clientes (nombre, telefono, limite_credito, saldo_actual)
        VALUES ('Cliente Dos', '3007654321', 200000.0, 0.0)
    """)
    conn.commit()

    # 1. Aplicar migraciones
    aplicadas = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas == ["001_plazo_pactado_dias"]

    # 2. Verificar que la columna existe y ambos clientes tienen plazo 8
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, telefono, limite_credito, saldo_actual, plazo_pactado_dias FROM clientes ORDER BY id")
    filas = cur.fetchall()
    assert len(filas) == 2

    assert filas[0]["nombre"] == "Cliente Uno"
    assert filas[0]["telefono"] == "3001234567"
    assert filas[0]["limite_credito"] == 100000.0
    assert filas[0]["saldo_actual"] == 5000.0
    assert filas[0]["plazo_pactado_dias"] == 8

    assert filas[1]["nombre"] == "Cliente Dos"
    assert filas[1]["telefono"] == "3007654321"
    assert filas[1]["limite_credito"] == 200000.0
    assert filas[1]["saldo_actual"] == 0.0
    assert filas[1]["plazo_pactado_dias"] == 8

    # 3. Verificar que existe exactamente un archivo .bak-*
    archivos_bak = glob.glob(f"{db_file}.bak-*")
    assert len(archivos_bak) == 1
    bak_path = archivos_bak[0]

    # Abrir el respaldo y verificar que NO tiene la columna
    conn_bak = sqlite3.connect(bak_path)
    cur_bak = conn_bak.cursor()
    cur_bak.execute("PRAGMA table_info(clientes)")
    columnas_bak = [c[1] for c in cur_bak.fetchall()]
    conn_bak.close()
    assert "plazo_pactado_dias" not in columnas_bak

    # 4. Segunda llamada: idempotencia (retorna [] y no crea otro respaldo)
    aplicadas_segunda = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas_segunda == []
    assert len(glob.glob(f"{db_file}.bak-*")) == 1

    # 5. UPDATE con plazo 10 lanza sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE clientes SET plazo_pactado_dias = 10 WHERE id = 1")

    conn.close()


def test_migracion_sin_tabla_clientes_no_hace_nada(tmp_path):
    """Verifica que sobre una base sin tabla clientes retorna [] y no crea respaldo."""
    db_file = str(tmp_path / "vacia.db")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        aplicadas = aplicar_migraciones(conn, db_path=db_file)
        assert aplicadas == []
        assert len(glob.glob(f"{db_file}.bak-*")) == 0
    finally:
        conn.close()


def test_migracion_002_agrega_costo_unitario(tmp_path):
    """
    Verifica la migración 002_costo_unitario_venta_detalle sobre una base con venta_detalle sin la columna:
    - Retorna ['002_costo_unitario_venta_detalle'].
    - Genera exactamente un archivo de respaldo .bak-*.
    - Agrega costo_unitario con CHECK que permite NULL o >= 0.
    - Preserva intactos los datos de las filas previas con costo_unitario NULL.
    - Segunda llamada retorna [] e idempotente.
    """
    db_file = str(tmp_path / "tienda_sin_costo.db")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    # Tabla clientes con plazo_pactado_dias ya presente (para que 001 no aplique)
    conn.execute("""
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            plazo_pactado_dias INTEGER NOT NULL DEFAULT 8
        );
    """)

    # Tabla ventas
    conn.execute("""
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            cliente_id INTEGER,
            tipo_pago TEXT NOT NULL,
            total REAL NOT NULL,
            monto_pagado REAL NOT NULL DEFAULT 0.0,
            fecha_venta DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla venta_detalle sin costo_unitario
    conn.execute("""
        CREATE TABLE venta_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL,
            producto_id INTEGER,
            descripcion TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            subtotal REAL NOT NULL
        );
    """)

    conn.execute("INSERT INTO ventas (usuario_id, tipo_pago, total) VALUES (1, 'efectivo', 3000.0)")
    conn.execute("""
        INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
        VALUES (1, NULL, 'Galletas', 2.0, 1500.0, 3000.0)
    """)
    conn.commit()

    # 1. Aplicar migraciones
    aplicadas = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas == ["002_costo_unitario_venta_detalle"]

    # 2. Respaldo creado
    archivos_bak = glob.glob(f"{db_file}.bak-*")
    assert len(archivos_bak) == 1

    # 3. Columna existe y fila vieja preservada con costo_unitario NULL
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(venta_detalle)")
    cols = [c["name"] for c in cur.fetchall()]
    assert "costo_unitario" in cols

    cur.execute("SELECT id, venta_id, descripcion, cantidad, precio_unitario, subtotal, costo_unitario FROM venta_detalle")
    fila = cur.fetchone()
    assert fila["descripcion"] == "Galletas"
    assert fila["cantidad"] == 2.0
    assert fila["precio_unitario"] == 1500.0
    assert fila["subtotal"] == 3000.0
    assert fila["costo_unitario"] is None

    # 4. Segunda llamada: idempotente
    aplicadas_2 = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas_2 == []
    assert len(glob.glob(f"{db_file}.bak-*")) == 1

    conn.close()


def test_migraciones_001_y_002_un_solo_respaldo(tmp_path):
    """
    Verifica que al aplicar migraciones sobre una base con clientes sin plazo_pactado_dias
    y venta_detalle sin costo_unitario:
    - Retorna ['001_plazo_pactado_dias', '002_costo_unitario_venta_detalle'].
    - Existe exactamente un archivo .bak-*.
    - Una segunda llamada retorna [] y no crea otro archivo de respaldo.
    """
    db_file = str(tmp_path / "tienda_sin_001_ni_002.db")
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row

    # Tabla clientes sin plazo_pactado_dias
    conn.execute("""
        CREATE TABLE clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cedula TEXT UNIQUE NOT NULL,
            telefono TEXT,
            direccion TEXT,
            limite_credito REAL NOT NULL DEFAULT 0.0,
            saldo_actual REAL NOT NULL DEFAULT 0.0,
            activo BOOLEAN NOT NULL DEFAULT 1,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla venta_detalle sin costo_unitario
    conn.execute("""
        CREATE TABLE venta_detalle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL,
            producto_id INTEGER,
            descripcion TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            subtotal REAL NOT NULL
        );
    """)
    conn.commit()

    # 1. Aplicar migraciones
    aplicadas = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas == ["001_plazo_pactado_dias", "002_costo_unitario_venta_detalle"]

    # 2. Verificar que existe exactamente UN archivo .bak-*
    archivos_bak = glob.glob(f"{db_file}.bak-*")
    assert len(archivos_bak) == 1

    # 3. Segunda llamada: retorna [] y sigue existiendo exactamente un .bak-*
    aplicadas_segunda = aplicar_migraciones(conn, db_path=db_file)
    assert aplicadas_segunda == []
    assert len(glob.glob(f"{db_file}.bak-*")) == 1

    conn.close()

