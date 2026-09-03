"""Piezas comunes de la batería de tests.

Ningún test toca la red: el recolector se ejercita contra las capturas reales
de `tests/fixtures/` mediante una conexión falsa (`FakeConnection`) que
devuelve el HTML guardado en lugar de descargarlo.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
SCHEMA_PATH = REPO / "schemas" / "item.schema.json"
SCRIPTS = REPO / "scripts"

# Los scripts de exploración se importan como módulos sueltos (p. ej. `_format`).
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Subastas con captura completa (todas las pestañas) y lo que se sabe de ellas
# por el listado del buscador.
FIXTURE_AUCTIONS = {
    "SUB-JA-2026-265000": {"status": "Celebrándose", "case_number": "0429/24", "lots": 2},
    "SUB-JA-2026-265003": {"status": "Celebrándose", "case_number": "0262/17", "lots": 3},
    "SUB-AT-2026-26R0886001200": {"status": "Celebrándose", "case_number": None, "lots": 0},
    "SUB-RC-2026-07003001815": {"status": "Celebrándose", "case_number": None, "lots": 0},
    "SUB-JA-2026-262402": {"status": None, "case_number": None, "lots": 0},
    "SUB-JC-2026-264427": {"status": None, "case_number": None, "lots": 0},
}

NOT_FOUND_HTML = (
    '<html><body><div id="contenido"><p>ERROR: La subasta no existe. '
    '<a href="/">Volver a la página de inicio</a></p></div></body></html>'
)

# Ficha con pestañas pero sin bloque de bienes: estructura irreconocible.
BROKEN_ASSETS_HTML = (
    '<html><body><div id="contenido"><div id="tabs"><ul class="navlist">'
    '<li><a href="./detalleSubasta.php?idSub=X&ver=3">Bienes</a></li></ul></div>'
    "<p>Contenido inesperado</p></div></body></html>"
)


def read_fixture(*parts: str) -> str:
    return (FIXTURES.joinpath(*parts)).read_text(encoding="utf-8")


class FakeConnection:
    """Conexión falsa: sirve las capturas de `tests/fixtures/` en lugar de la red.

    `broken` permite sustituir una página concreta ((id_subasta, ver) -> HTML)
    para simular un cambio de estructura del portal.
    """

    def __init__(self, broken: dict[tuple[str, int], str] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.broken = broken or {}

    def get(self, path: str, params: dict | None = None) -> str:
        params = dict(params or {})
        self.calls.append((path, params))
        if path == "subastas_ava.php":
            return read_fixture("province-auction-list.html")
        assert path == "detalleSubasta.php", path
        auction_id, view, lot = params["idSub"], params["ver"], params.get("idLote")
        if (auction_id, view) in self.broken:
            return self.broken[(auction_id, view)]
        folder = FIXTURES / auction_id
        if not folder.is_dir():
            return NOT_FOUND_HTML
        if view == 3:
            name = f"lots/auction-lot-{lot:02d}.html" if lot else "auction-assets.html"
        elif view == 5:
            name = f"bids/auction-bid-{lot:02d}.html" if lot else "auction-bids.html"
        else:
            name = {
                1: "auction-general-info.html",
                2: "auction-managing-authority.html",
                4: "auction-related-items.html",
            }[view]
        return (folder / name).read_text(encoding="utf-8")


@pytest.fixture
def fake_connection() -> FakeConnection:
    return FakeConnection()


@pytest.fixture(scope="session")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def validator(schema: dict) -> jsonschema.Draft202012Validator:
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


@pytest.fixture(autouse=True)
def _reset_logging():
    """Evita que `logging.basicConfig` del CLI se quede enganchado al stderr
    capturado de un test anterior."""
    root = logging.getLogger()
    root.handlers.clear()
    yield
    root.handlers.clear()


