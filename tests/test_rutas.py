import os
import sys
import tempfile
import pytest

from db.rutas import (
    es_ejecutable,
    ruta_recursos,
    carpeta_datos,
    ruta_base_datos,
    carpeta_comprobantes,
)
from services.reportes_service import generar_comprobante_pdf
from services.cxc_service import crear_cliente, registrar_cargo


def test_rutas_en_desarrollo():
    """
    Verifica que en modo desarrollo (sin sys.frozen):
    - es_ejecutable() sea False.
    - ruta_base_datos() termine en 'db/tienda.db' dentro del proyecto.
    - ruta_recursos('db', 'schema.sql') apunte a un archivo existente.
    """
    assert es_ejecutable() is False
    db_path = ruta_base_datos()
    assert db_path.endswith(os.path.join("db", "tienda.db"))
    schema_file = ruta_recursos("db", "schema.sql")
    assert os.path.exists(schema_file)
    assert os.path.isfile(schema_file)


def test_rutas_en_ejecutable(tmp_path, monkeypatch):
    """
    Verifica que en modo ejecutable (con sys.frozen=True, sys._MEIPASS y LOCALAPPDATA):
    - es_ejecutable() sea True.
    - carpeta_datos() sea <tmp_path/local>/MiTienda y exista físicamente.
    - ruta_base_datos() esté dentro de carpeta_datos() y se llame tienda.db.
    - carpeta_comprobantes() sea carpeta_datos()/comprobantes y exista físicamente.
    - ruta_recursos apunte a sys._MEIPASS.
    """
    recursos_dir = tmp_path / "recursos"
    recursos_dir.mkdir()
    schema_dummy = recursos_dir / "db" / "schema.sql"
    schema_dummy.parent.mkdir(parents=True, exist_ok=True)
    schema_dummy.write_text("DUMMY SCHEMA", encoding="utf-8")

    local_app_data = str(tmp_path / "local")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(recursos_dir), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", local_app_data)

    assert es_ejecutable() is True

    c_datos = carpeta_datos()
    esperado_datos = os.path.join(local_app_data, "MiTienda")
    assert os.path.abspath(c_datos) == os.path.abspath(esperado_datos)
    assert os.path.exists(c_datos)

    r_bd = ruta_base_datos()
    assert r_bd == os.path.join(c_datos, "tienda.db")

    c_comp = carpeta_comprobantes()
    esperado_comp = os.path.join(c_datos, "comprobantes")
    assert os.path.abspath(c_comp) == os.path.abspath(esperado_comp)
    assert os.path.exists(c_comp)

    r_recurso = ruta_recursos("db", "schema.sql")
    assert os.path.abspath(r_recurso) == os.path.abspath(str(schema_dummy))
    assert os.path.exists(r_recurso)


def test_generar_comprobante_pdf_usa_carpeta_comprobantes(tmp_path, monkeypatch, db_conn):
    """
    Verifica que al invocar generar_comprobante_pdf con ruta_salida=None,
    el comprobante se guarde dentro del directorio retornado por carpeta_comprobantes().
    """
    comprobantes_custom = str(tmp_path / "mis_comprobantes")
    os.makedirs(comprobantes_custom, exist_ok=True)

    monkeypatch.setattr("services.reportes_service.carpeta_comprobantes", lambda: comprobantes_custom)

    cli = crear_cliente(nombre="Cliente Comprobante Test", limite_credito=500.0, conn=db_conn)
    cargo = registrar_cargo(cliente_id=cli.id, monto=150.0, conn=db_conn, descripcion="Cargo comprobante ruta")

    pdf_generado = generar_comprobante_pdf(movimiento_id=cargo.id, conn=db_conn, ruta_salida=None)

    assert os.path.exists(pdf_generado)
    assert os.path.dirname(os.path.abspath(pdf_generado)) == os.path.abspath(comprobantes_custom)
