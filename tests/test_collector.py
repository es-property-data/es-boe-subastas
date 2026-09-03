"""Ensamblado de sobres a partir de la ficha completa (sin red)."""

import pytest

from boe_subastas import models
from boe_subastas.client.collector import collect, detail_url
from boe_subastas.errors import ItemNotFoundError, StructureError
from conftest import BROKEN_ASSETS_HTML, FIXTURE_AUCTIONS, FakeConnection


def collect_all(connection):
    envelopes = []
    for auction_id, known in FIXTURE_AUCTIONS.items():
        for external_id, url, data in collect(connection, auction_id, known["status"], known["case_number"]):
            envelopes.append(models.envelope(external_id, url, data))
    return envelopes


def test_one_envelope_per_lot_or_per_auction(fake_connection):
    envelopes = collect_all(fake_connection)
    ids = [e["meta"]["external_id"] for e in envelopes]
    assert ids == [
        "SUB-JA-2026-265000/L1", "SUB-JA-2026-265000/L2",
        "SUB-JA-2026-265003/L1", "SUB-JA-2026-265003/L2", "SUB-JA-2026-265003/L3",
        "SUB-AT-2026-26R0886001200", "SUB-RC-2026-07003001815",
        "SUB-JA-2026-262402", "SUB-JC-2026-264427",
    ]


def test_every_envelope_validates_against_the_schema(fake_connection, validator):
    for envelope in collect_all(fake_connection):
        errors = [e.message for e in validator.iter_errors(envelope)]
        assert errors == [], (envelope["meta"]["external_id"], errors)


def test_collection_is_deterministic():
    first = [data for _, _, data in collect(FakeConnection(), "SUB-JA-2026-265003", "Celebrándose", "0262/17")]
    second = [data for _, _, data in collect(FakeConnection(), "SUB-JA-2026-265003", "Celebrándose", "0262/17")]
    assert first == second


def test_lot_envelope_carries_lot_economics_and_parent_link(fake_connection):
    (external_id, url, data), *_ = collect(fake_connection, "SUB-JA-2026-265000", "Celebrándose", "0429/24")
    assert external_id == "SUB-JA-2026-265000/L1"
    assert url == "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-JA-2026-265000&ver=3&idLote=1"
    assert data["identificador_subasta"] == "SUB-JA-2026-265000"
    assert data["lote"]["numero"] == 1 and data["lote"]["valor_subasta"] == 262046.95
    assert data["subasta"]["estado"] == "Celebrándose"
    assert data["subasta"]["expediente"] == "0429/24"
    assert data["subasta"]["lotes"] == 2
    assert data["pujas"] == {"puja_mas_alta": None, "mensaje": "Sin pujas en el lote 1 de esta subasta", "certificado_cierre": None}


def test_auction_without_lots(fake_connection):
    ((external_id, url, data),) = list(collect(fake_connection, "SUB-AT-2026-26R0886001200", "Celebrándose", None))
    assert external_id == "SUB-AT-2026-26R0886001200"
    assert url == detail_url("SUB-AT-2026-26R0886001200")
    assert data["lote"] is None
    assert data["subasta"]["valor_subasta"] == 113674.93
    assert data["pujas"]["puja_mas_alta"] == 59367.49
    assert data["subasta"]["acreedores"] is None


def test_related_entities_reach_the_envelope(fake_connection):
    ((_, _, jc),) = list(collect(fake_connection, "SUB-JC-2026-264427"))
    assert jc["subasta"]["administradores_concursales"][0]["nombre"] == "FRANCISCO DE BORJA"
    assert "privilegiados" in jc["subasta"]["aviso_relacionados"]
    ((_, _, rc),) = list(collect(fake_connection, "SUB-RC-2026-07003001815"))
    assert rc["subasta"]["acreedores"][0]["nif"] == "Q0700546E"


def test_only_lot_limits_to_that_lot(fake_connection):
    envelopes = list(collect(fake_connection, "SUB-JA-2026-265003", only_lot=2))
    assert [e[0] for e in envelopes] == ["SUB-JA-2026-265003/L2"]
    with pytest.raises(ItemNotFoundError):
        list(collect(fake_connection, "SUB-JA-2026-265003", only_lot=7))
    with pytest.raises(ItemNotFoundError):
        list(collect(fake_connection, "SUB-AT-2026-26R0886001200", only_lot=1))


def test_unknown_auction_is_item_not_found(fake_connection):
    with pytest.raises(ItemNotFoundError):
        list(collect(fake_connection, "SUB-XX-9999-000000"))


def test_broken_lot_does_not_hide_the_other_lots():
    connection = FakeConnection(broken={("SUB-JA-2026-265003", 3): BROKEN_ASSETS_HTML})
    # todas las peticiones ver=3 de esa subasta devuelven la página rota -> los
    # tres lotes fallan; la excepción llega al final, no al primer lote
    with pytest.raises(StructureError):
        list(collect(connection, "SUB-JA-2026-265003"))
    lot_requests = [p for path, p in connection.calls if path == "detalleSubasta.php" and p["ver"] == 3]
    assert [p["idLote"] for p in lot_requests] == [1, 2, 3]


def test_detail_url():
    assert detail_url("SUB-X") == "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-X"
    assert detail_url("SUB-X", 2) == "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-X&ver=3&idLote=2"
