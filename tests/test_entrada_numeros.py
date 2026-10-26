import pytest
from ui.entrada_numeros import leer_monto, MENSAJE_ERROR_MONTO


def test_leer_monto_punto_miles_con_y_sin_decimales():
    # ^\d{1,3}(\.\d{3})+(,\d{1,2})?$
    assert leer_monto("50.000") == 50000.0
    assert leer_monto("1.250.000") == 1250000.0
    assert leer_monto("2.500,50") == 2500.5
    assert leer_monto("2.500,5") == 2500.5
    assert leer_monto("$ 50.000") == 50000.0
    assert leer_monto("$1.250.000") == 1250000.0
    assert leer_monto("$ 2.500,50") == 2500.5


def test_leer_monto_coma_miles():
    # ^\d{1,3}(,\d{3})+$
    assert leer_monto("50,000") == 50000.0
    assert leer_monto("1,250,000") == 1250000.0
    assert leer_monto("$ 50,000") == 50000.0


def test_leer_monto_sin_miles_coma_decimal_opcional():
    # ^\d+(,\d{1,2})?$
    assert leer_monto("2500") == 2500.0
    assert leer_monto("2500,5") == 2500.5
    assert leer_monto("2500,50") == 2500.5
    assert leer_monto("50,00") == 50.0
    assert leer_monto("0") == 0.0
    assert leer_monto("0,5") == 0.5


def test_leer_monto_punto_decimal():
    # ^\d+(\.\d{1,2})?$
    assert leer_monto("2.5") == 2.5
    assert leer_monto("0.50") == 0.5
    assert leer_monto("2500.5") == 2500.5
    assert leer_monto("0.5") == 0.5


@pytest.mark.parametrize(
    "invalido",
    [
        "",
        "   ",
        "$",
        " $ ",
        "abc",
        "5.00.0",
        "-3000",
        "2.5000",
        "1,2,3",
        "1.2.3",
        "2.500,500",
        "50..000",
    ],
)
def test_leer_monto_invalidos_lanzan_value_error(invalido):
    with pytest.raises(ValueError) as excinfo:
        leer_monto(invalido)
    assert str(excinfo.value) == MENSAJE_ERROR_MONTO
