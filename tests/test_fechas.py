from datetime import datetime, timezone
from services.fechas import a_hora_local


def test_a_hora_local_ida_y_vuelta():
    """Toma la hora local ingenua 2026-10-13 20:00:00, conviértela a UTC con astimezone()
    y formatea como texto de SQLite; a_hora_local(ese texto) == '2026-10-13 20:00:00'.
    """
    dt_local = datetime(2026, 10, 13, 20, 0, 0)
    dt_utc = dt_local.astimezone(timezone.utc)
    sqlite_txt = dt_utc.strftime("%Y-%m-%d %H:%M:%S")
    assert a_hora_local(sqlite_txt) == "2026-10-13 20:00:00"


def test_a_hora_local_vacio_e_invalido():
    """None → '--', '' → '--', 'no es fecha' → 'no es fecha'."""
    assert a_hora_local(None) == "--"
    assert a_hora_local("") == "--"
    assert a_hora_local("no es fecha") == "no es fecha"
