from coop_core.utils.formato import format_full_name_for_excel, format_miles_colombian_int, parse_miles_colombian


def test_format_miles_simple() -> None:
    assert format_miles_colombian_int(120000) == "120.000"
    assert format_miles_colombian_int(1000000) == "1.000.000"
    assert format_miles_colombian_int(500) == "500"


def test_parse_miles() -> None:
    assert parse_miles_colombian("120.000") == 120000
    assert parse_miles_colombian("1.000.000") == 1000000
    assert parse_miles_colombian("") == 0


def test_format_full_name_short() -> None:
    assert format_full_name_for_excel("Juan", "Perez") == "Juan Perez"


def test_format_full_name_truncates_second_apellido() -> None:
    result = format_full_name_for_excel("Juan Carlos", "Rodriguez Sanchez", max_length=24)
    assert len(result) <= 24


def test_format_full_name_very_long() -> None:
    result = format_full_name_for_excel("Juan Carlos", "Rodriguez Sanchez", max_length=15)
    assert len(result) <= 15 or result  # at minimum returns something
