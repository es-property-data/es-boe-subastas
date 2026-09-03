"""Búsqueda: paginación, localización por identificador y particionado."""

from boe_subastas.client.search import locate, search, search_pages
from boe_subastas.models import STATUSES
from conftest import read_fixture

TOO_MANY_HTML = (
    '<html><body><div id="contenido"><p>ERROR: El número de resultados obtenidos '
    "para la consulta realizada es excesivo.</p></div></body></html>"
)


class PartitionConnection:
    """Rechaza por «excesiva» toda consulta sin estado; con estado, lista."""

    def __init__(self, reject_until_key: str = "dato[2]") -> None:
        self.calls: list[dict] = []
        self.reject_until_key = reject_until_key

    def get(self, path: str, params: dict | None = None) -> str:
        params = dict(params or {})
        self.calls.append(params)
        assert path == "subastas_ava.php"
        if self.reject_until_key not in params:
            return TOO_MANY_HTML
        return read_fixture("province-auction-list.html")


def test_search_pages_single_page(fake_connection):
    pages = list(search_pages(fake_connection, {"province": "07", "status": "EJ"}))
    assert len(pages) == 1 and pages[0]["total"] == 9
    (path, params), = fake_connection.calls
    assert path == "subastas_ava.php"
    assert params["campo[8]"] == "BIEN.COD_PROVINCIA" and params["dato[8]"] == "07"
    assert params["campo[2]"] == "SUBASTA.ESTADO.CODIGO" and params["dato[2]"] == "EJ"
    assert params["accion"] == "Buscar"


def test_search_yields_listing_items(fake_connection):
    items = list(search(fake_connection, {"province": "07"}))
    assert len(items) == 9
    assert items[0]["identificador"] == "SUB-JA-2026-265000"


def test_locate_returns_listing_item_or_none(fake_connection):
    item = locate(fake_connection, "SUB-JA-2026-265003")
    assert item["estado"] == "Celebrándose" and item["expediente"] == "0262/17"
    assert fake_connection.calls[-1][1]["dato[15]"] == "SUB-JA-2026-265003"
    assert locate(fake_connection, "SUB-XX-0000-000000") is None


def test_partition_by_status_when_source_rejects_broad_query():
    connection = PartitionConnection()
    items = list(search(connection, {"province": "07"}))
    assert len(items) == 9  # deduplicados entre subconsultas
    statuses = [p["dato[2]"] for p in connection.calls if "dato[2]" in p]
    assert statuses == list(STATUSES)
    assert len(connection.calls) == 1 + len(STATUSES)


def test_partition_by_start_date_when_status_is_already_set():
    connection = PartitionConnection(reject_until_key="dato[18][1]")
    items = list(search(connection, {"province": "07", "status": "FS"}))
    assert len(items) == 9
    windows = [(p["dato[18][0]"], p["dato[18][1]"]) for p in connection.calls if "dato[18][1]" in p]
    assert len(windows) == 2 and windows[0][1] < windows[1][0]
