import os
import shutil
import sqlite3
from datetime import datetime
from typing import Optional, List


def aplicar_migraciones(
    conn: sqlite3.Connection, db_path: Optional[str] = None
) -> List[str]:
    """
    Ejecuta de manera segura e idempotente las migraciones de esquema pendientes sobre la base de datos.

    Características de integridad:
    - No destructivo: Nunca borra, recrea ni trunca tablas existentes, preservando los datos históricos intactos.
    - Respaldo automático: Antes de realizar cualquier mutación física DDL en un archivo de base de datos
      en disco (distinto de ':memory:'), genera una copia de respaldo completa con timestamp
      formateado como '{db_path}.bak-AAAAMMDD-HHMMSS'.
    - Idempotencia: Inspecciona la estructura actual mediante PRAGMAs de SQLite y aplica únicamente
      las migraciones no aplicadas previamente.

    Retorna la lista de identificadores de migraciones aplicadas exitosamente durante la llamada.
    """
    migraciones_aplicadas: List[str] = []

    # 1. Migración "001_plazo_pactado_dias"
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(clientes)")
    columnas_clientes = cursor.fetchall()

    # Si la tabla clientes no existe (PRAGMA vacío), no hace nada
    if not columnas_clientes:
        return migraciones_aplicadas

    respaldo_realizado = False

    def asegurar_respaldo() -> None:
        nonlocal respaldo_realizado
        if not respaldo_realizado and db_path and db_path != ":memory:" and os.path.isfile(db_path):
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = f"{db_path}.bak-{timestamp}"
            shutil.copy2(db_path, backup_path)
            respaldo_realizado = True

    # 1. Migración "001_plazo_pactado_dias"
    nombres_columnas_clientes = [
        col[1] if isinstance(col, tuple) else col["name"] for col in columnas_clientes
    ]
    if "plazo_pactado_dias" not in nombres_columnas_clientes:
        asegurar_respaldo()
        cursor.execute(
            "ALTER TABLE clientes ADD COLUMN plazo_pactado_dias INTEGER NOT NULL DEFAULT 8 CHECK (plazo_pactado_dias IN (8, 15))"
        )
        conn.commit()
        migraciones_aplicadas.append("001_plazo_pactado_dias")

    # 2. Migración "002_costo_unitario_venta_detalle"
    cursor.execute("PRAGMA table_info(venta_detalle)")
    columnas_vd = cursor.fetchall()
    if columnas_vd:
        nombres_columnas_vd = [
            col[1] if isinstance(col, tuple) else col["name"] for col in columnas_vd
        ]
        if "costo_unitario" not in nombres_columnas_vd:
            asegurar_respaldo()
            cursor.execute(
                "ALTER TABLE venta_detalle ADD COLUMN costo_unitario REAL CHECK (costo_unitario IS NULL OR costo_unitario >= 0)"
            )
            conn.commit()
            migraciones_aplicadas.append("002_costo_unitario_venta_detalle")

    return migraciones_aplicadas
