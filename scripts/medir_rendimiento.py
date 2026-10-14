"""Script de medición de rendimiento bajo volúmenes objetivo (RNF-03).

Evalúa los tiempos de respuesta de las operaciones críticas del sistema
usando una base de datos temporal generada para pruebas.
"""

import csv
import os
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

from db.connection import get_connection
from services.inventario_service import crear_producto, buscar_productos, listar_productos
from services.cxc_service import crear_cliente, registrar_abono
from services.pos_service import asignar_limite_credito
from services.scoring_service import evaluar_cliente
from services.reportes_service import obtener_consolidado_cartera

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCHEMA_PATH = os.path.join(REPO_ROOT, "db", "schema.sql")
SEEDS_PATH = os.path.join(REPO_ROOT, "db", "seeds_test.sql")
TIENDA_DB_PATH = os.path.abspath(os.path.join(REPO_ROOT, "db", "tienda.db"))
CSV_PATH = os.path.join(REPO_ROOT, "scripts", "resultados_rendimiento.csv")


def crear_base_de_prueba(
    ruta: str,
    n_productos: int = 500,
    n_clientes: int = 200,
    n_movimientos: int = 5000,
) -> sqlite3.Connection:
    """Crea una base de datos SQLite poblada con el volumen de datos especificado.

    Exige que ruta no sea db/tienda.db y que el archivo no exista previamente.
    Inicializa esquema y semillas, crea productos, clientes, movimientos y ventas.
    """
    ruta_abs = os.path.abspath(ruta)
    if ruta_abs == TIENDA_DB_PATH or os.path.basename(ruta_abs) == "tienda.db":
        raise ValueError("Prohibido usar o sobreescribir db/tienda.db para pruebas de rendimiento.")

    if os.path.exists(ruta):
        raise ValueError(f"El archivo ya existe: {ruta}")

    conn = get_connection(ruta)

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    with open(SEEDS_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # Optimización de I/O para carga masiva
    conn.execute("PRAGMA synchronous = OFF")

    # 1. Crear productos (repartidos entre las 3 categorías)
    categorias = ["canasta_basica", "cesta_mixta", "consumo_suntuario"]
    for i in range(1, n_productos + 1):
        cat = categorias[(i - 1) % len(categorias)]
        barcode = f"770{i:010d}"
        crear_producto(
            nombre=f"Producto Prueba {i}",
            categoria=cat,
            precio_venta=10000.0,
            costo=7000.0,
            codigo_barras=barcode,
            stock=1000,
            stock_minimo=10,
            conn=conn,
        )

    # 2. Crear clientes (repartidos entre los 3 vínculos, cupo 10M, plazos 8 y 15)
    vinculos = ["registro_completo", "conocido_referido", "solo_apodo"]
    clientes_creados = []
    for i in range(1, n_clientes + 1):
        vinc = vinculos[(i - 1) % len(vinculos)]
        cli = crear_cliente(
            nombre=f"Cliente Rendimiento {i}",
            nivel_vinculo=vinc,
            conn=conn,
        )
        plazo = 8 if i <= (n_clientes // 2) else 15
        asignar_limite_credito(
            cliente_id=cli.id,
            nuevo_limite=10_000_000.0,
            conn=conn,
            plazo_pactado_dias=plazo,
        )
        clientes_creados.append(cli)

    # 3. Crear movimientos de cuentas_por_cobrar
    counts = [n_movimientos // n_clientes] * n_clientes
    rem = n_movimientos % n_clientes
    for r in range(rem):
        counts[r] += 1
    if n_clientes > 1 and n_movimientos >= 10:
        shift = min(10, counts[-1] // 2)
        counts[0] += shift
        counts[-1] -= shift

    now = datetime.now(timezone.utc)
    cxc_rows = []
    cli_saldos = {}

    for c_idx, cli in enumerate(clientes_creados):
        k = counts[c_idx]
        saldo = 0.0
        for j in range(k):
            day_offset = 119 - int(118 * (j / max(1, k - 1))) if k > 1 else 60
            dt = now - timedelta(days=day_offset, minutes=(k - j) * 5)
            fecha_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            if j % 2 == 0:
                tipo = "cargo"
                monto = 50000.0
                saldo += monto
            else:
                tipo = "abono"
                monto = min(30000.0, saldo)
                saldo -= monto
            cxc_rows.append((cli.id, 1, tipo, monto, saldo, fecha_str, f"Movimiento #{j+1}"))
        cli_saldos[cli.id] = saldo

    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT INTO cuentas_por_cobrar (
            cliente_id, usuario_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento, descripcion
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        cxc_rows,
    )
    for cid, saldo in cli_saldos.items():
        cursor.execute("UPDATE clientes SET saldo_actual = ? WHERE id = ?", (saldo, cid))

    # 4. Crear 2.000 ventas en efectivo con detalle en los últimos 30 días
    cursor.execute("SELECT id, precio_venta FROM productos WHERE activo = 1")
    prods = cursor.fetchall()
    cursor.execute("SELECT id FROM clientes WHERE activo = 1")
    clis = cursor.fetchall()

    n_ventas = 2000
    for v in range(1, n_ventas + 1):
        cli_id = clis[(v - 1) % len(clis)]["id"]
        prod = prods[(v - 1) % len(prods)]
        p_id = prod["id"]
        precio = float(prod["precio_venta"])
        day_offset = int(29 * (v / max(1, n_ventas)))
        dt = now - timedelta(days=day_offset, minutes=v * 2)
        fecha_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """
            INSERT INTO ventas (usuario_id, cliente_id, tipo_pago, total, monto_pagado, fecha_venta)
            VALUES (1, ?, 'efectivo', ?, ?, ?)
            """,
            (cli_id, precio, precio, fecha_str),
        )
        vid = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO venta_detalle (venta_id, producto_id, descripcion, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, 'Item venta rendimiento', 1.0, ?, ?)
            """,
            (vid, p_id, precio, precio),
        )

    conn.commit()
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def medir(conn: sqlite3.Connection, repeticiones: int = 7) -> List[Dict[str, Any]]:
    """Mide con time.perf_counter la mediana y máximo en milisegundos de las operaciones requeridas."""
    cursor = conn.cursor()

    # Identificar cliente con más movimientos para scoring
    cursor.execute(
        """
        SELECT cliente_id, COUNT(*) as c
        FROM cuentas_por_cobrar
        GROUP BY cliente_id
        ORDER BY c DESC
        LIMIT 1
        """
    )
    top_cxc = cursor.fetchone()
    top_cliente_id = top_cxc["cliente_id"] if top_cxc else 1

    # Identificar clientes con saldo > 0 para los abonos
    cursor.execute(
        """
        SELECT id, saldo_actual
        FROM clientes
        WHERE saldo_actual > 100
        ORDER BY id ASC
        LIMIT ?
        """,
        (repeticiones,),
    )
    abono_clis = cursor.fetchall()
    if not abono_clis:
        cursor.execute("SELECT id, saldo_actual FROM clientes WHERE saldo_actual > 0 LIMIT 1")
        abono_clis = cursor.fetchall()

    operaciones = [
        ("Inventario: buscar_productos", 500.0),
        ("Inventario: listar_productos", 500.0),
        ("Saldo: registrar_abono", 500.0),
        ("Scoring: evaluar_cliente", 500.0),
        ("Informativo: obtener_consolidado_cartera", None),
    ]

    resultados: List[Dict[str, Any]] = []

    for nombre_op, limite in operaciones:
        tiempos: List[float] = []

        for r in range(repeticiones):
            if nombre_op == "Inventario: buscar_productos":
                t0 = time.perf_counter()
                buscar_productos("Producto", conn=conn)
                t1 = time.perf_counter()
            elif nombre_op == "Inventario: listar_productos":
                t0 = time.perf_counter()
                listar_productos(conn=conn)
                t1 = time.perf_counter()
            elif nombre_op == "Saldo: registrar_abono":
                cid = abono_clis[r % len(abono_clis)]["id"]
                t0 = time.perf_counter()
                registrar_abono(
                    cliente_id=cid,
                    monto=10.0,
                    conn=conn,
                    auto_commit=True,
                    usuario_id=1,
                    descripcion=f"Abono medición #{r+1}",
                )
                t1 = time.perf_counter()
            elif nombre_op == "Scoring: evaluar_cliente":
                t0 = time.perf_counter()
                evaluar_cliente(top_cliente_id, conn=conn)
                t1 = time.perf_counter()
            elif nombre_op == "Informativo: obtener_consolidado_cartera":
                t0 = time.perf_counter()
                obtener_consolidado_cartera(conn=conn)
                t1 = time.perf_counter()
            else:
                raise ValueError(f"Operación desconocida: {nombre_op}")

            tiempos.append((t1 - t0) * 1000.0)

        mediana = round(statistics.median(tiempos), 2)
        maximo = round(max(tiempos), 2)
        cumple = (mediana <= limite) if limite is not None else None

        resultados.append(
            {
                "operacion": nombre_op,
                "mediana_ms": mediana,
                "maximo_ms": maximo,
                "limite_ms": limite,
                "cumple": cumple,
            }
        )

    return resultados


def main() -> None:
    """Ejecuta la suite de pruebas de rendimiento sobre una base de datos temporal."""
    print("=" * 70)
    print("MEDICIÓN DE RENDIMIENTO DEL SISTEMA (RNF-03)")
    print("=" * 70)
    print(f"Versión de Python: {sys.version.split()[0]} ({platform.python_implementation()})")
    print(f"Sistema Operativo: {platform.system()} {platform.release()} ({platform.platform()})")
    print(f"Procesador:        {platform.processor() or 'No identificado'}")
    print("-" * 70)

    with tempfile.TemporaryDirectory() as td:
        ruta_db = os.path.join(td, "tienda_perf.db")
        print("Poblando base de datos temporal con volúmenes de prueba...")
        t_ini = time.perf_counter()
        conn = crear_base_de_prueba(ruta_db, n_productos=500, n_clientes=200, n_movimientos=5000)
        t_creacion = time.perf_counter() - t_ini
        print(f"Base de prueba creada en {t_creacion:.2f} s.")

        cur = conn.cursor()
        total_prod = cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        total_cli = cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        total_cxc = cur.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0]
        total_vta = cur.execute("SELECT COUNT(*) FROM ventas").fetchone()[0]

        print("-" * 70)
        print("VOLÚMENES REALES REGISTRADOS:")
        print(f"  - Productos en catálogo:       {total_prod}")
        print(f"  - Clientes registrados:        {total_cli}")
        print(f"  - Movimientos CxC (historial): {total_cxc}")
        print(f"  - Ventas registradas:          {total_vta}")
        print("-" * 70)

        print("Ejecutando mediciones (7 repeticiones por operación)...")
        resultados = medir(conn, repeticiones=7)
        conn.close()

        # Mostrar tabla formateada
        print("-" * 70)
        print(f"{'Operación':<42} | {'Mediana':>10} | {'Máximo':>9} | {'Límite':>7} | {'Cumple':^6}")
        print("-" * 70)
        for r in resultados:
            lim_str = f"{r['limite_ms']:.0f} ms" if r["limite_ms"] is not None else "N/A"
            cumple_str = "SÍ" if r["cumple"] is True else ("NO" if r["cumple"] is False else "INFO")
            print(
                f"{r['operacion']:<42} | {r['mediana_ms']:>7.2f} ms | {r['maximo_ms']:>6.2f} ms | {lim_str:>7} | {cumple_str:^6}"
            )
        print("-" * 70)

        # Guardar en CSV
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["operacion", "mediana_ms", "maximo_ms", "limite_ms", "cumple"],
            )
            writer.writeheader()
            for r in resultados:
                writer.writerow(r)

        print(f"Resultados exportados exitosamente a: {CSV_PATH}")
        print("=" * 70)


if __name__ == "__main__":
    main()
