"""Página de resultados del buscador (`subastas_ava.php`)."""

import pytest

from boe_subastas.errors import QueryError, StructureError
from boe_subastas.parser.listing import parse_listing
from conftest import read_fixture

TOO_MANY_HTML = (
    '<html><body><div id="contenido"><ul class="navlist"><li><a href="#">Búsqueda</a></li></ul>'
    "<p>ERROR: El número de resultados obtenidos para la consulta realizada es "
    "excesivo. Por favor, proporcione algún criterio más.</p></div></body></html>"
)
EMPTY_HTML = (
    '<html><body><div id="contenido"><div class="caja gris info"><p>No se han '
    "encontrado documentos que satisfagan sus criterios de búsqueda</p></div></div></body></html>"
)


def test_listing_counter_results_and_token():
    page = parse_listing(read_fixture("province-auction-list.html"))
    assert (page["desde"], page["hasta"], page["total"]) == (1, 9, 9)
    assert page["token"] and "-" not in page["token"][-3:]  # sin sufijo -inicio-hits
    ids = [r["identificador"] for r in page["resultados"]]
    assert ids == [
        "SUB-JA-2026-265000", "SUB-JA-2026-262582", "SUB-JA-2026-264731",
        "SUB-JA-2026-263775", "SUB-JA-2026-264170", "SUB-RC-2026-07003001801",
        "SUB-AT-2026-26R0886001200", "SUB-JA-2026-265003", "SUB-RC-2026-07003001815",
    ]


def test_listing_item_fields():
    results = {r["identificador"]: r for r in parse_listing(read_fixture("province-auction-list.html"))["resultados"]}
    first = results["SUB-JA-2026-265000"]
    assert first["lotes"] == 2
    assert first["estado"] == "Celebrándose"
    assert first["expediente"] == "0429/24"
    assert first["autoridad"].startswith("Sección Civil TI Eivissa")
    assert results["SUB-JA-2026-265003"]["lotes"] == 3
    assert results["SUB-AT-2026-26R0886001200"]["lotes"] is None
    assert results["SUB-AT-2026-26R0886001200"]["expediente"] is None


def test_too_many_results_raises_query_error():
    with pytest.raises(QueryError):
        parse_listing(TOO_MANY_HTML)


def test_empty_search_is_zero_results_not_an_error():
    page = parse_listing(EMPTY_HTML)
    assert page["total"] == 0 and page["resultados"] == []


def test_missing_counter_is_a_structure_change():
    with pytest.raises(StructureError):
        parse_listing("<html><body><div id='contenido'><p>Hola</p></div></body></html>")
