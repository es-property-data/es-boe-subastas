"""Pestaña «Pujas» (ver=5) en sus variantes."""

from boe_subastas.parser.bids import parse_bids
from conftest import read_fixture

ANONYMOUS_ACTIVE_HTML = (
    '<html><body><div id="contenido"><div id="tabs"></div><h3>Pujas</h3>'
    "<h4>Puja máxima actual de la subasta</h4>"
    '<p class="centrador">La subasta ha recibido alguna puja. Para ver su importe debe acceder como usuario registrado.</p>'
    "</div></body></html>"
)
CONCLUDED_HTML = (
    '<html><body><div id="contenido"><div id="tabs"></div><h3>Pujas</h3><h4>Pujas máximas</h4>'
    "<table><tr><th>Lote</th><th>Importe de la puja</th></tr>"
    "<tr><td>1</td><td>17.089,94 €</td></tr><tr><td>2</td><td>15.641,64 €</td></tr></table>"
    '<p class="puntoPDF"><a href="/reg/verCertificadoCierre.php?idSub=SUB-X">Certificado de cierre de la subasta</a></p>'
    "</div></body></html>"
)


def test_logged_in_lot_without_bids():
    b = parse_bids(read_fixture("SUB-JA-2026-265000", "bids", "auction-bid-01.html"))
    assert b["numero_lote"] == 1
    assert b["puja_mas_alta"] is None
    assert b["mensaje"] == "Sin pujas en el lote 1 de esta subasta"
    assert b["pujas_maximas"] is None and b["certificado_cierre"] is None


def test_logged_in_lots_with_amounts():
    assert parse_bids(read_fixture("SUB-JA-2026-265003", "bids", "auction-bid-01.html"))["puja_mas_alta"] == 15641.64
    third = parse_bids(read_fixture("SUB-JA-2026-265003", "bids", "auction-bid-03.html"))
    assert (third["numero_lote"], third["puja_mas_alta"]) == (3, 15351.98)


def test_auctions_without_lots():
    assert parse_bids(read_fixture("SUB-AT-2026-26R0886001200", "auction-bids.html"))["puja_mas_alta"] == 59367.49
    rc = parse_bids(read_fixture("SUB-RC-2026-07003001815", "auction-bids.html"))
    assert (rc["numero_lote"], rc["puja_mas_alta"]) == (None, 6118.8)


def test_anonymous_active_variant_keeps_portal_message():
    b = parse_bids(ANONYMOUS_ACTIVE_HTML)
    assert b["puja_mas_alta"] is None
    assert b["mensaje"].startswith("La subasta ha recibido alguna puja")


def test_concluded_variant_table_per_lot_and_certificate():
    b = parse_bids(CONCLUDED_HTML)
    assert b["pujas_maximas"] == [{"lote": 1, "importe": 17089.94}, {"lote": 2, "importe": 15641.64}]
    assert b["certificado_cierre"] == "https://subastas.boe.es/verCertificadoCierre.php?idSub=SUB-X"
