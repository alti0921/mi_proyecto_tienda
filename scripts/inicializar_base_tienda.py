import os
import sqlite3
import argparse
from db.migraciones import aplicar_migraciones
from services.auth_service import crear_usuario, CONTRASENA_INICIAL_TIENDA


def inicializar_base_tienda(ruta_db: str) -> None:
    """
    Inicializa una base de datos limpia para una tienda real sin datos de prueba.
    Ejecuta el esquema estructural, aplica migraciones y registra un único usuario administrador
    con la contraseña inicial por defecto.
    """
    if os.path.exists(ruta_db):
        raise ValueError("La base ya existe; no se reinicializa.")

    directorio = os.path.dirname(os.path.abspath(ruta_db))
    if directorio:
        os.makedirs(directorio, exist_ok=True)

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    schema_path = os.path.join(base_dir, "db", "schema.sql")

    conn = None
    archivo_creado = False
    try:
        conn = sqlite3.connect(ruta_db)
        archivo_creado = True
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        aplicar_migraciones(conn, ruta_db)

        crear_usuario(
            username="admin",
            password=CONTRASENA_INICIAL_TIENDA,
            nombre="Administrador",
            conn=conn,
            rol="admin",
        )
        conn.close()
        conn = None
    except Exception:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        if archivo_creado and os.path.exists(ruta_db):
            try:
                os.remove(ruta_db)
            except Exception:
                pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inicializa una base de datos limpia para una tienda real sin datos semilla."
    )
    parser.add_argument(
        "--ruta",
        default="db/tienda.db",
        help="Ruta al archivo de base de datos a crear (por defecto: db/tienda.db)",
    )
    args = parser.parse_args()
    try:
        inicializar_base_tienda(args.ruta)
        print("Base creada. Entre con usuario admin y contraseña tienda123; el sistema le pedirá cambiarla al ingresar.")
    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
