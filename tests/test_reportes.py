import os
import sqlite3
import pytest
from datetime import date

from services.reportes_service import (
    obtener_arqueo_diario,
    obtener_consolidado_cartera,
    clasificar_banda_mora,
    generar_comprobante_pdf,
)
from services.pos_service import registrar_venta, asignar_limite_credito, LineaVentaInput
from services.cxc_service import crear_cliente, registrar_abono, registrar_cargo
from services.inventario_service import crear_producto
from services.auth_service import obtener_usuario_por_username


def test_clasificar_banda_mora():
    """Verifica que clasificar_banda_mora clasifique fielmente según los umbrales de scoring (P-Q9 / V1.1)."""
    # 0 a 3 días: vigente
    assert clasificar_banda_mora(0)[0] == "vigente_0_3"
    assert clasificar_banda_mora(1)[0] == "vigente_0_3"
    assert clasificar_banda_mora(3)[0] == "vigente_0_3"

    # 4 a 6 días: preventiva
    assert clasificar_banda_mora(4)[0] == "preventiva_4_6"
    assert clasificar_banda_mora(5)[0] == "preventiva_4_6"
    assert clasificar_banda_mora(6)[0] == "preventiva_4_6"

    # 7 a 10 días: congelada (Clase C)
    assert clasificar_banda_mora(7)[0] == "congelada_7_10"
    assert clasificar_banda_mora(8)[0] == "congelada_7_10"
    assert clasificar_banda_mora(10)[0] == "congelada_7_10"

    # > 10 días: crítica (Clase D)
    assert clasificar_banda_mora(11)[0] == "critica_mas_10"
    assert clasificar_banda_mora(20)[0] == "critica_mas_10"


def test_obtener_arqueo_diario_sin_movimientos(db_conn):
    """Verifica el arqueo diario en un día sin transacciones."""
    arqueo = obtener_arqueo_diario(fecha="2026-01-01", conn=db_conn)

    assert arqueo["fecha"] == "2026-01-01"
    assert arqueo["ventas_efectivo"] == 0.0
    assert arqueo["ventas_nequi"] == 0.0
    assert arqueo["ventas_credito"] == 0.0
    assert arqueo["anticipos_credito"] == 0.0
    assert arqueo["abonos_cxc"] == 0.0
    assert arqueo["total_efectivo_en_caja"] == 0.0
    assert arqueo["total_ingresos_dia"] == 0.0
    assert arqueo["total_transacciones"] == 0
    assert arqueo["movimientos"] == []


def test_obtener_arqueo_diario_consolidado_completo(db_conn):
    """
    Verifica la liquidación completa del arqueo de caja con:
    - Venta contado en efectivo ($20.000)
    - Venta contado en nequi ($15.000)
    - Venta a crédito con anticipo en efectivo ($50.000 total, $10.000 anticipo, $40.000 financiado)
    - Abono de cartera en efectivo ($15.000)
    Total efectivo en caja esperado: 20.000 + 10.000 + 15.000 = $45.000.
    Total ingresos día: 45.000 (efectivo) + 15.000 (nequi) = $60.000.
    """
    admin = obtener_usuario_por_username("admin", db_conn)
    cliente = crear_cliente(nombre="Pedro Arqueo", nivel_vinculo="registro_completo", conn=db_conn)
    asignar_limite_credito(cliente.id, 100000.0, db_conn)

    prod = crear_producto(
        nombre="Aceite Girasol 1L",
        categoria="canasta_basica",
        precio_venta=10000.0,
        costo=8000.0,
        conn=db_conn,
        stock=50.0,
    )

    # 1. Venta Efectivo: $20.000 (2 unidades)
    registrar_venta(
        usuario_id=admin.id,
        tipo_pago="efectivo",
        items=[LineaVentaInput(producto_id=prod.id, cantidad=2.0, precio_unitario=10000.0)],
        monto_pagado=20000.0,
        conn=db_conn,
    )

    # 2. Venta Nequi: $15.000 (1 ítem por monto directo)
    registrar_venta(
        usuario_id=admin.id,
        tipo_pago="nequi",
        items=[LineaVentaInput(producto_id=None, descripcion="Carga Virtual", cantidad=1.0, precio_unitario=15000.0)],
        monto_pagado=15000.0,
        conn=db_conn,
    )

    # 3. Venta Crédito: $50.000 con anticipo de $10.000
    registrar_venta(
        usuario_id=admin.id,
        cliente_id=cliente.id,
        tipo_pago="credito",
        items=[LineaVentaInput(producto_id=prod.id, cantidad=5.0, precio_unitario=10000.0)],
        monto_pagado=10000.0,
        conn=db_conn,
    )

    # 4. Abono en CxC: $15.000 abonados a la cuenta
    registrar_abono(cliente_id=cliente.id, monto=15000.0, conn=db_conn, descripcion="Abono parcial en caja")

    # Consultar arqueo del día actual
    hoy_str = date.today().strftime("%Y-%m-%d")
    arqueo = obtener_arqueo_diario(fecha="today", conn=db_conn)

    assert arqueo["fecha"] == hoy_str
    assert arqueo["ventas_efectivo"] == 20000.0
    assert arqueo["ventas_nequi"] == 15000.0
    assert arqueo["ventas_credito"] == 40000.0  # Neto fiado ($50.000 - $10.000)
    assert arqueo["total_ventas_credito"] == 50000.0
    assert arqueo["anticipos_credito"] == 10000.0
    assert arqueo["abonos_cxc"] == 15000.0

    # Efectivo en caja física = 20.000 + 10.000 + 15.000 = 45.000
    assert arqueo["total_efectivo_en_caja"] == 45000.0

    # Total ingresos = efectivo + nequi = 45.000 + 15.000 = 60.000
    assert arqueo["total_ingresos_dia"] == 60000.0

    assert arqueo["total_transacciones"] == 4
    assert len(arqueo["movimientos"]) == 4

    tipos_mov = [m["tipo"] for m in arqueo["movimientos"]]
    assert "Venta Contado (Efectivo)" in tipos_mov
    assert "Venta Contado (Nequi/Transf.)" in tipos_mov
    assert "Venta a Crédito (Fiado)" in tipos_mov
    assert "Abono Cartera CxC" in tipos_mov


def test_obtener_consolidado_cartera_clasificacion_bandas(db_conn):
    """
    Verifica que obtener_consolidado_cartera:
    1. Agregue todos los saldos deudores.
    2. Excluya a clientes con saldo 0.
    3. Clasifique a los clientes en las 4 bandas exactas de scoring según mora efectiva:
       - Vigente (0 a 3 días de mora efectiva)
       - Preventiva (4 a 6 días de mora efectiva)
       - Congelada (7 a 10 días de mora efectiva)
       - Crítica (> 10 días de mora efectiva)
    """
    # Crear 4 clientes con cupo y registrar cargos
    c1 = crear_cliente(nombre="Cliente Vigente", nivel_vinculo="registro_completo", limite_credito=100000.0, conn=db_conn)
    c2 = crear_cliente(nombre="Cliente Preventivo", nivel_vinculo="conocido_referido", limite_credito=100000.0, conn=db_conn)
    c3 = crear_cliente(nombre="Cliente Congelado", nivel_vinculo="conocido_referido", limite_credito=100000.0, conn=db_conn)
    c4 = crear_cliente(nombre="Cliente Critico", nivel_vinculo="solo_apodo", limite_credito=100000.0, conn=db_conn)
    c_paz_salvo = crear_cliente(nombre="Cliente Al Dia", limite_credito=100000.0, conn=db_conn)

    # 1. C1: Hoy (0 días transcurridos -> mora_efectiva = 0) -> vigente_0_3
    cursor = db_conn.cursor()
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 25000.0, 25000.0, datetime('now'))
    """, (c1.id,))
    cursor.execute("UPDATE clientes SET saldo_actual = 25000.0 WHERE id = ?", (c1.id,))

    # 2. C2: Hace 13 días (13 - 8 = 5 días de mora efectiva) -> preventiva_4_6
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 30000.0, 30000.0, datetime('now', '-13 days'))
    """, (c2.id,))
    cursor.execute("UPDATE clientes SET saldo_actual = 30000.0 WHERE id = ?", (c2.id,))

    # 3. C3: Hace 16 días (16 - 8 = 8 días de mora efectiva) -> congelada_7_10
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 40000.0, 40000.0, datetime('now', '-16 days'))
    """, (c3.id,))
    cursor.execute("UPDATE clientes SET saldo_actual = 40000.0 WHERE id = ?", (c3.id,))

    # 4. C4: Hace 22 días (22 - 8 = 14 días de mora efectiva) -> critica_mas_10
    cursor.execute("""
        INSERT INTO cuentas_por_cobrar (cliente_id, tipo_movimiento, monto, saldo_resultante, fecha_movimiento)
        VALUES (?, 'cargo', 50000.0, 50000.0, datetime('now', '-22 days'))
    """, (c4.id,))
    cursor.execute("UPDATE clientes SET saldo_actual = 50000.0 WHERE id = ?", (c4.id,))

    db_conn.commit()

    # Ejecutar consolidado de cartera
    cartera = obtener_consolidado_cartera(db_conn)

    # Verificaciones globales
    assert cartera["total_deudores"] == 4
    assert cartera["total_cartera_por_cobrar"] == 25000.0 + 30000.0 + 40000.0 + 50000.0  # 145.000

    # Conteo por banda
    conteos = cartera["conteo_por_banda"]
    assert conteos["vigente_0_3"] == 1
    assert conteos["preventiva_4_6"] == 1
    assert conteos["congelada_7_10"] == 1
    assert conteos["critica_mas_10"] == 1

    # Montos por banda
    resumen = cartera["resumen_por_banda"]
    assert resumen["vigente_0_3"] == 25000.0
    assert resumen["preventiva_4_6"] == 30000.0
    assert resumen["congelada_7_10"] == 40000.0
    assert resumen["critica_mas_10"] == 50000.0

    # Verificar que el cliente en paz y salvo no aparezca en deudores
    ids_deudores = [d["cliente_id"] for d in cartera["deudores"]]
    assert c_paz_salvo.id not in ids_deudores
    assert c1.id in ids_deudores
    assert c2.id in ids_deudores
    assert c3.id in ids_deudores
    assert c4.id in ids_deudores


def test_generar_comprobante_pdf_con_usuario_identificado(db_conn, tmp_path):
    """
    RF-CXC-04: Verifica la generación exitosa de un comprobante en PDF de 80mm
    para un abono con cajero identificado (usuario_id presente).
    """
    cliente = crear_cliente(nombre="María Del Comprobante", limite_credito=60000.0, conn=db_conn)
    registrar_cargo(cliente_id=cliente.id, monto=40000.0, conn=db_conn, usuario_id=1)

    abono = registrar_abono(
        cliente_id=cliente.id,
        monto=15000.0,
        conn=db_conn,
        descripcion="Abono parcial en mostrador",
        usuario_id=2,  # Vendedor
    )

    salida_pdf = str(tmp_path / f"comprobante_abono_{abono.id}.pdf")
    ruta_generada = generar_comprobante_pdf(
        movimiento_id=abono.id,
        conn=db_conn,
        ruta_salida=salida_pdf,
    )

    assert ruta_generada == salida_pdf
    assert os.path.exists(salida_pdf)
    assert os.path.getsize(salida_pdf) > 500  # Archivo binario PDF con contenido

    # Verificar cabecera mágica de archivo PDF
    with open(salida_pdf, "rb") as f:
        cabecera = f.read(5)
        assert cabecera == b"%PDF-"


def test_generar_comprobante_pdf_usuario_none_caso_legado(db_conn, tmp_path):
    """
    RF-CXC-04: Verifica la compatibilidad histórica cuando usuario_id es NULL,
    desplegando 'No registrado' como cajero en el PDF.
    """
    cliente = crear_cliente(nombre="Juan Histórico", limite_credito=50000.0, conn=db_conn)
    registrar_cargo(cliente_id=cliente.id, monto=20000.0, conn=db_conn)

    abono_legado = registrar_abono(
        cliente_id=cliente.id,
        monto=5000.0,
        conn=db_conn,
        descripcion="Abono de migración histórica",
        usuario_id=None,
    )

    salida_pdf = str(tmp_path / "comprobante_legado.pdf")
    ruta_generada = generar_comprobante_pdf(
        movimiento_id=abono_legado.id,
        conn=db_conn,
        ruta_salida=salida_pdf,
    )

    assert os.path.exists(ruta_generada)
    assert os.path.getsize(ruta_generada) > 500


def test_generar_comprobante_pdf_cargo_venta_credito_y_ruta_temporal(db_conn):
    """
    RF-CXC-04: Verifica la generación de comprobante de un cargo generado desde una venta
    a crédito, y la generación en directorio temporal si ruta_salida es None.
    """
    admin = obtener_usuario_por_username("admin", db_conn)
    cliente = crear_cliente(nombre="Carlos Crédito", limite_credito=100000.0, conn=db_conn)
    prod = crear_producto(
        nombre="Harina de Trigo",
        categoria="canasta_basica",
        precio_venta=5000.0,
        costo=3500.0,
        conn=db_conn,
        stock=20.0,
    )

    venta = registrar_venta(
        usuario_id=admin.id,
        cliente_id=cliente.id,
        tipo_pago="credito",
        items=[LineaVentaInput(producto_id=prod.id, cantidad=3.0, precio_unitario=5000.0)],
        conn=db_conn,
    )

    # Buscar el cargo asociado a la venta
    cur = db_conn.cursor()
    cur.execute("SELECT id FROM cuentas_por_cobrar WHERE venta_id = ?", (venta.id,))
    cargo_row = cur.fetchone()
    assert cargo_row is not None
    cargo_id = cargo_row["id"]

    ruta_temp = generar_comprobante_pdf(
        movimiento_id=cargo_id,
        conn=db_conn,
        ruta_salida=None,
    )

    assert os.path.exists(ruta_temp)
    assert ruta_temp.endswith(".pdf")
    assert os.path.getsize(ruta_temp) > 500


def test_generar_comprobante_pdf_validaciones_error(db_conn):
    """Verifica manejo de errores ante movimiento inexistente o conexión nula."""
    with pytest.raises(ValueError, match="no encontrado"):
        generar_comprobante_pdf(movimiento_id=99999, conn=db_conn)

    with pytest.raises(ValueError, match="Se requiere una conexión"):
        generar_comprobante_pdf(movimiento_id=1, conn=None)
