from coop_core.utils.telefono import derivar_whatsapp_e164


def test_usa_whatsapp_e164_si_ya_esta_presente() -> None:
    assert derivar_whatsapp_e164("+573001234567", "3009999999") == "+573001234567"


def test_deriva_desde_celular_valido() -> None:
    assert derivar_whatsapp_e164(None, "3116426370") == "+573116426370"


def test_deriva_desde_celular_con_guiones() -> None:
    assert derivar_whatsapp_e164(None, "311-642-6370") == "+573116426370"


def test_sin_whatsapp_ni_celular_es_none() -> None:
    assert derivar_whatsapp_e164(None, None) is None


def test_celular_con_longitud_incorrecta_es_none() -> None:
    assert derivar_whatsapp_e164(None, "12345") is None


def test_celular_que_no_empieza_en_3_es_none() -> None:
    assert derivar_whatsapp_e164(None, "6011234567") is None
