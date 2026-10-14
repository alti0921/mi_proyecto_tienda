import os
import pytest
from scripts.medir_rendimiento import crear_base_de_prueba, medir, TIENDA_DB_PATH


def test_script_rendimiento_corre_con_volumen_pequeno(tmp_path):
    """
    Verifica que el script de rendimiento funcione correctamente con un volumen reducido:
    crea la base, ejecuta la medición (1 repetición), retorna 5 operaciones y los COUNT(*)
    coinciden con los volúmenes pedidos más los datos semilla.
    """
    db_path = str(tmp_path / "perf.db")
    conn = crear_base_de_prueba(db_path, n_productos=20, n_clientes=10, n_movimientos=100)

    try:
        resultados = medir(conn, repeticiones=1)
        assert len(resultados) == 5
        for r in resultados:
            assert r["mediana_ms"] >= 0.0
            assert "operacion" in r
            assert "maximo_ms" in r

        cur = conn.cursor()
        total_prod = cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        total_cli = cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        total_cxc = cur.execute("SELECT COUNT(*) FROM cuentas_por_cobrar").fetchone()[0]

        # 20 creados + 3 semillas = 23
        assert total_prod == 23
        # 10 creados + 1 semilla = 11
        assert total_cli == 11
        # 100 movimientos creados (+ 1 abono registrado en la medición)
        assert total_cxc in (100, 101)
    finally:
        conn.close()


def test_script_rendimiento_rechaza_tienda_db():
    """
    Verifica que crear_base_de_prueba rechace tajantemente ejecutarse sobre db/tienda.db
    lanzando ValueError:
    - Si db/tienda.db existe: tamaño y fecha quedan intactos.
    - Si no existe: sigue sin existir después del intento.
    """
    if os.path.exists(TIENDA_DB_PATH):
        stat_antes = os.stat(TIENDA_DB_PATH)
        size_antes = stat_antes.st_size
        mtime_antes = stat_antes.st_mtime

        with pytest.raises(ValueError):
            crear_base_de_prueba(TIENDA_DB_PATH)

        stat_despues = os.stat(TIENDA_DB_PATH)
        assert stat_despues.st_size == size_antes
        assert stat_despues.st_mtime == mtime_antes
    else:
        with pytest.raises(ValueError):
            crear_base_de_prueba(TIENDA_DB_PATH)

        assert not os.path.exists(TIENDA_DB_PATH)
