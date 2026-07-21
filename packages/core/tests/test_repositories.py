"""Tests directos de métodos de repositorios no cubiertos por los servicios."""

from datetime import date
from typing import Any

from coop_core.services.amortization import build_amortization_schedule


def _insert_socio(
    repos: dict[str, Any], nombres: str = "Ana", apellidos: str = "Perez", saldo: int = 0
) -> int:
    return repos["socios"].save(nombres, apellidos, None, None, saldo)


def _insert_credito_completo(
    repos: dict[str, Any], sid: int, capital: int = 600_000, n_cuotas: int = 6
) -> int:
    letra_id = repos["creditos"].create([sid], capital, 0.02, n_cuotas, "2024-01-01")
    cuotas = build_amortization_schedule(letra_id, capital, 0.02, n_cuotas, date(2024, 1, 1))
    repos["liquidaciones"].save_all(cuotas)
    repos["conn"].commit()
    return letra_id


# ─── SociosRepository ─────────────────────────────────────────────────────────


def test_socios_find_all_empty(repos: dict[str, Any]) -> None:
    assert repos["socios"].find_all() == []


def test_socios_find_all(repos: dict[str, Any]) -> None:
    _insert_socio(repos, "Carlos", "Lopez")
    _insert_socio(repos, "Maria", "Garcia")
    rows = repos["socios"].find_all()
    assert len(rows) == 2


def test_socios_find_all_full(repos: dict[str, Any]) -> None:
    _insert_socio(repos, "Juan", "Ruiz", saldo=50000)
    rows = repos["socios"].find_all_full()
    assert rows[0]["nombres"] == "Juan"
    assert rows[0]["saldo"] == 50000


def test_socios_find_by_id_not_found(repos: dict[str, Any]) -> None:
    assert repos["socios"].find_by_id(999) is None


def test_socios_find_by_id(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Rosa", "Torres")
    row = repos["socios"].find_by_id(sid)
    assert row is not None
    assert row["nombres"] == "Rosa"


def test_socios_search_by_name(repos: dict[str, Any]) -> None:
    _insert_socio(repos, "Pedro", "Sanchez")
    _insert_socio(repos, "Carla", "Sanchez")
    results = repos["socios"].search_by_name("Sanchez")
    assert len(results) == 2


def test_socios_search_by_name_no_match(repos: dict[str, Any]) -> None:
    _insert_socio(repos, "Luis", "Mora")
    assert repos["socios"].search_by_name("zzzz") == []


def test_socios_get_balance(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Nora", "Vega", saldo=120000)
    assert repos["socios"].get_balance(sid) == 120000


def test_socios_update(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Viejo", "Nombre", saldo=0)
    repos["socios"].update(sid, "Nuevo", "Apellido", "123", None, 5000)
    repos["conn"].commit()
    row = repos["socios"].find_by_id(sid)
    assert row is not None
    assert row["nombres"] == "Nuevo"
    assert row["saldo"] == 5000


# ─── CreditosRepository ───────────────────────────────────────────────────────


def test_creditos_find_by_letra(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Hugo", "Perez")
    letra = _insert_credito_completo(repos, sid, 500_000, 5)
    row = repos["creditos"].find_by_letra(letra)
    assert row is not None
    assert int(row["capital"]) == 500_000


def test_creditos_find_by_letra_not_found(repos: dict[str, Any]) -> None:
    assert repos["creditos"].find_by_letra(9999) is None


def test_creditos_find_active_by_socio_id(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Elena", "Cruz")
    _insert_credito_completo(repos, sid)
    creditos = repos["creditos"].find_active_by_socio_id(sid)
    assert len(creditos) == 1
    assert int(creditos[0]["capital"]) == 600_000


def test_creditos_find_active_no_creditos(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Sin", "Credito")
    assert repos["creditos"].find_active_by_socio_id(sid) == []


def test_creditos_get_socio_ids(repos: dict[str, Any]) -> None:
    s1 = _insert_socio(repos, "A", "B")
    s2 = _insert_socio(repos, "C", "D")
    letra = repos["creditos"].create([s1, s2], 300_000, 0.02, 3, "2024-01-01")
    repos["conn"].commit()
    ids = repos["creditos"].get_socio_ids(letra)
    assert sorted(ids) == sorted([s1, s2])


def test_creditos_update_no_cuotas(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "T", "U")
    letra = repos["creditos"].create([sid], 300_000, 0.02, 6, "2024-01-01")
    repos["conn"].commit()
    repos["creditos"].update_no_cuotas(letra, 4)
    repos["conn"].commit()
    row = repos["creditos"].find_by_letra(letra)
    assert row is not None
    assert int(row["no_cuotas"]) == 4


# ─── LiquidacionesRepository ──────────────────────────────────────────────────


def test_liquidaciones_get_total_cuotas(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "F", "G")
    letra = _insert_credito_completo(repos, sid, 600_000, 6)
    assert repos["liquidaciones"].get_total_cuotas(letra) == 6


def test_liquidaciones_get_total_cuotas_not_found(repos: dict[str, Any]) -> None:
    assert repos["liquidaciones"].get_total_cuotas(9999) == 0


def test_liquidaciones_find_pending(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "H", "I")
    letra = _insert_credito_completo(repos, sid, 600_000, 6)
    pending = repos["liquidaciones"].find_pending(letra)
    assert len(pending) == 6
    assert pending[0]["nro_cuota"] == 1


def test_liquidaciones_get_current_debt(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "J", "K")
    letra = _insert_credito_completo(repos, sid, 600_000, 6)
    debt = repos["liquidaciones"].get_current_debt(letra)
    assert debt > 0


def test_liquidaciones_get_current_debt_fully_paid(repos: dict[str, Any]) -> None:
    """Cuando no hay cuotas pendientes, retorna el saldo_capital de la última cuota."""
    sid = _insert_socio(repos, "L", "M")
    letra = repos["creditos"].create([sid], 100_000, 0.0, 1, "2024-01-01")
    repos["liquidaciones"].save_all([(letra, 1, "2024-02-01", 100_000, 0, 100_000, 0)])
    # Mark as paid
    repos["conn"].cursor().execute(
        "UPDATE liquidaciones SET fecha_pago = '2024-02-01' WHERE credito_letra = ?", (letra,)
    )
    repos["conn"].commit()
    debt = repos["liquidaciones"].get_current_debt(letra)
    assert debt == 0


def test_liquidaciones_get_current_debt_no_rows(repos: dict[str, Any]) -> None:
    assert repos["liquidaciones"].get_current_debt(9999) == 0


# ─── LiquidacionesRepository.recalculate_amortization ────────────────────────


def _pay_cuota(
    repos: dict[str, Any], letra_id: int, nro_cuota: int, monto: int, recibo_id: int, socio_id: int
) -> None:
    cur = repos["conn"].cursor()
    cur.execute(
        "UPDATE liquidaciones SET fecha_pago = '2024-04-01' WHERE credito_letra = ? AND nro_cuota = ?",
        (letra_id, nro_cuota),
    )
    cur.execute(
        "INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto) "
        "VALUES (?, 'pago_credito', ?, ?, ?, ?)",
        (recibo_id, socio_id, letra_id, nro_cuota, monto),
    )
    repos["conn"].commit()


def test_recalculate_amortization_basic(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "Rec", "Test")
    letra = _insert_credito_completo(repos, sid, 600_000, 6)

    # Create recibo for the payments
    cur = repos["conn"].cursor()
    cur.execute("INSERT INTO recibos (socio_id) VALUES (?)", (sid,))
    repos["conn"].commit()
    recibo_id = 1

    # Pay cuota 1 and 2
    cuota1_val = int(repos["liquidaciones"].find_pending(letra)[0]["valor_cuota"])
    _pay_cuota(repos, letra, 1, cuota1_val, recibo_id, sid)
    cuota2_val = int(repos["liquidaciones"].find_pending(letra)[0]["valor_cuota"])
    _pay_cuota(repos, letra, 2, cuota2_val, recibo_id, sid)

    # Register abono capital in detalle_recibo
    abono = 100_000
    cur.execute(
        "INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto) "
        "VALUES (?, 'pago_credito', ?, ?, 0, ?)",
        (recibo_id, sid, letra, abono),
    )
    repos["conn"].commit()

    # Should not raise
    repos["liquidaciones"].recalculate_amortization(letra, abono)
    repos["conn"].commit()

    pending_after = repos["liquidaciones"].find_pending(letra)
    assert len(pending_after) < 6  # fewer cuotas remaining


def test_recalculate_amortization_paid_off(repos: dict[str, Any]) -> None:
    """Si el saldo real es 0 después del abono, se eliminan cuotas pendientes."""
    sid = _insert_socio(repos, "Zero", "Debt")
    letra = repos["creditos"].create([sid], 100_000, 0.0, 1, "2024-01-01")
    repos["liquidaciones"].save_all([(letra, 1, "2024-02-01", 100_000, 0, 100_000, 0)])
    repos["conn"].commit()

    cur = repos["conn"].cursor()
    cur.execute("INSERT INTO recibos (socio_id) VALUES (?)", (sid,))
    repos["conn"].commit()

    # Mark cuota as paid and register full abono
    cur.execute(
        "UPDATE liquidaciones SET fecha_pago = '2024-02-01' WHERE credito_letra = ? AND nro_cuota = 1",
        (letra,),
    )
    cur.execute(
        "INSERT INTO detalle_recibo (recibo_id, tipo_operacion, socio_id, credito_letra, nro_cuota, monto) "
        "VALUES (1, 'pago_credito', ?, ?, 0, 100000)",
        (sid, letra),
    )
    repos["conn"].commit()

    repos["liquidaciones"].recalculate_amortization(letra, 100_000)
    repos["conn"].commit()
    assert repos["liquidaciones"].find_pending(letra) == []


def test_recalculate_amortization_no_credito(repos: dict[str, Any]) -> None:
    repos["liquidaciones"].recalculate_amortization(9999, 1000)  # should not raise


def test_recalculate_amortization_with_future_cuotas(repos: dict[str, Any]) -> None:
    """Cuando las cuotas restantes son futuras, genera nuevas cuotas con el saldo restante."""
    sid = _insert_socio(repos, "Future", "Credito")
    # Use a far-future fecha_inicio so all cuotas have future vencimiento
    letra = repos["creditos"].create([sid], 600_000, 0.02, 6, "2030-01-01")
    cuotas = build_amortization_schedule(letra, 600_000, 0.02, 6, date(2030, 1, 1))
    repos["liquidaciones"].save_all(cuotas)
    repos["conn"].commit()

    # Mark cuota 1 as paid
    repos["conn"].cursor().execute(
        "UPDATE liquidaciones SET fecha_pago = '2030-02-01' WHERE credito_letra = ? AND nro_cuota = 1",
        (letra,),
    )
    repos["conn"].commit()

    # No abono capital, but cuota 1 was paid — recalculate rebuilds cuotas 2-6
    repos["liquidaciones"].recalculate_amortization(letra, 0)
    repos["conn"].commit()

    pending = repos["liquidaciones"].find_pending(letra)
    # Should still have 5 pending future cuotas
    assert len(pending) == 5


# ─── RecibosRepository ────────────────────────────────────────────────────────


def test_recibos_create(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "R", "S")
    recibo_id = repos["recibos"].create(sid)
    repos["conn"].commit()
    assert recibo_id == 1


def test_recibos_find_by_id(repos: dict[str, Any]) -> None:
    sid = _insert_socio(repos, "X", "Z")
    recibo_id = repos["recibos"].create(sid)
    repos["conn"].commit()
    row = repos["recibos"].find_by_id(recibo_id)
    assert row is not None
    assert int(row["socio_id"]) == sid


def test_recibos_find_by_id_not_found(repos: dict[str, Any]) -> None:
    assert repos["recibos"].find_by_id(9999) is None


# ─── AuxiliarRepository ───────────────────────────────────────────────────────


def test_auxiliar_find_all_empty(repos: dict[str, Any]) -> None:
    assert repos["auxiliar"].find_all() == []


def test_auxiliar_find_all_with_filters(repos: dict[str, Any]) -> None:
    repos["auxiliar"].add("2024-01-15", "Aporte", "Pedro Lopez", 50000, 50000, recibo=1)
    repos["auxiliar"].add("2024-02-10", "Retiro", "Maria Ruiz", -30000, 20000, recibo=2)
    repos["conn"].commit()

    all_rows = repos["auxiliar"].find_all(limit=10)
    assert len(all_rows) == 2

    filtered = repos["auxiliar"].find_all(operation_type="Aporte")
    assert len(filtered) == 1
    assert filtered[0]["tipo"] == "Aporte"

    by_date = repos["auxiliar"].find_all(start_date="2024-02-01", end_date="2024-12-31")
    assert len(by_date) == 1

    by_name = repos["auxiliar"].find_all(socio_name="pedro")
    assert len(by_name) == 1

    by_recibo = repos["auxiliar"].find_all(numero=1)
    assert len(by_recibo) == 1


def test_auxiliar_find_all_pagination(repos: dict[str, Any]) -> None:
    for i in range(5):
        repos["auxiliar"].add(f"2024-01-{i + 1:02d}", "Aporte", f"Socio {i}", 1000, 1000)
    repos["conn"].commit()
    page1 = repos["auxiliar"].find_all(limit=3, offset=0)
    page2 = repos["auxiliar"].find_all(limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) == 2
