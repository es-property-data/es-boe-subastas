"""Pestañas de la ficha: información general, autoridad gestora y relacionados."""

import pytest

from boe_subastas.errors import ItemNotFoundError
from boe_subastas.parser.authority import parse_authority
from boe_subastas.parser.detail import parse_tabs
from boe_subastas.parser.general import parse_general
from boe_subastas.parser.related import parse_related
from conftest import NOT_FOUND_HTML, read_fixture


def test_tabs_of_auction_with_lots_and_without_related():
    tabs = parse_tabs(read_fixture("SUB-JA-2026-265000", "auction-general-info.html"))
    assert [(t["texto"], t["ver"]) for t in tabs] == [
        ("Información general", 1), ("Autoridad gestora", 2), ("Lotes", 3), ("Pujas", 5),
    ]


def test_tabs_of_auction_with_related_tab():
    views = {t["ver"] for t in parse_tabs(read_fixture("SUB-RC-2026-07003001815", "auction-general-info.html"))}
    assert views == {1, 2, 3, 4, 5}


def test_general_info_of_judicial_auction_with_lots():
    g = parse_general(read_fixture("SUB-JA-2026-265000", "auction-general-info.html"))
    assert g["identificador"] == "SUB-JA-2026-265000"
    assert g["tipo"] == "JUDICIAL EN VÍA DE APREMIO"
    assert g["cuenta_expediente"] == "0422 0000 06 0429 24"
    assert g["fecha_inicio"] == "2026-08-25T18:00:00+02:00"
    assert g["fecha_conclusion"] == "2026-09-14T18:00:00+02:00"
    assert g["cantidad_reclamada"] == 145660.86
    assert g["lotes"] == 2
    assert g["forma_adjudicacion"] == "Separada para cada lote"
    assert g["anuncio_boe"] == "BOE-B-2026-27571"
    # con lotes, los importes de la ficha son literales que remiten a cada lote
    assert g["valor_subasta"].startswith("Ver valor de subasta en cada lote")
    assert len(g["documentos"]) == 7
    assert g["documentos"][0]["url"].startswith("https://subastas.boe.es/verDocumento.php?idSub=SUB-JA-2026-265000")
    assert g["advertencia"].startswith("ADVERTENCIA:") and g["advertencia"].endswith("24 horas.")
    assert g["aviso_estado"] is None
    assert g["otros"] is None


def test_general_info_of_tax_agency_auction_without_lots():
    g = parse_general(read_fixture("SUB-AT-2026-26R0886001200", "auction-general-info.html"))
    assert g["tipo"] == "AGENCIA TRIBUTARIA"
    assert g["lotes"] == 0
    assert g["cuenta_expediente"] is None
    assert (g["valor_subasta"], g["tasacion"], g["puja_minima"]) == (113674.93, 117983.12, 11367.49)
    assert (g["tramos_pujas"], g["importe_deposito"]) == (2000.0, 5683.74)
    assert g["fecha_conclusion"] == "2026-08-31T18:38:01+02:00"


def test_general_info_literal_minimum_bid():
    g = parse_general(read_fixture("SUB-RC-2026-07003001815", "auction-general-info.html"))
    assert g["puja_minima"] == "Sin puja mínima"
    assert g["tramos_pujas"] == 203.96


def test_missing_detail_page_is_item_not_found():
    with pytest.raises(ItemNotFoundError):
        parse_general(NOT_FOUND_HTML)


def test_managing_authority():
    a = parse_authority(read_fixture("SUB-JA-2026-265000", "auction-managing-authority.html"))
    assert a["codigo"] == "0702642003"
    assert a["descripcion"] == "Sección Civil TI Eivissa. Plz.n 3"
    assert a["telefono"] == "971314161"
    assert a["correo_electronico"] == "scej.eivissa@justicia.es"
    assert a["otros"] is None


def test_managing_authority_absent_fax_is_none():
    a = parse_authority(read_fixture("SUB-RC-2026-07003001815", "auction-managing-authority.html"))
    assert a["fax"] is None
    assert a["descripcion"] == "Agencia Tributaria de las Islas Baleares (Agencia Tributaria Islas Baleares)"


def test_related_creditor():
    r = parse_related(read_fixture("SUB-RC-2026-07003001815", "auction-related-items.html"))
    assert r["acreedores"][0]["nombre"] == "Agencia Tributaria de las Islas Baleares"
    assert r["acreedores"][0]["nif"] == "Q0700546E"
    assert r["acreedores"][0]["localidad"] == "07003 PALMA"
    assert r["administradores_concursales"] is None
    assert r["aviso"] is None and r["otros"] is None


def test_related_insolvency_administrator_with_notice():
    r = parse_related(read_fixture("SUB-JC-2026-264427", "auction-related-items.html"))
    assert r["acreedores"] is None
    assert r["administradores_concursales"][0]["nif"] == "43041239M"
    assert "privilegiados" in r["aviso"]


def test_related_creditor_with_country():
    r = parse_related(read_fixture("SUB-JA-2026-262402", "auction-related-items.html"))
    assert r["acreedores"][0]["pais"] == "España"


def test_related_keeps_every_table_and_ignores_orphan_headings():
    base = read_fixture("SUB-JC-2026-264427", "auction-related-items.html")
    extra_table = "<table><tr><th>Nombre</th><td>SEGUNDO ADMIN</td></tr></table>"
    html = base.replace("</table>", "</table>" + extra_table, 1)
    html = html.replace("<h3>Administrador concursal</h3>", "<h3>Acreedor</h3><h3>Administrador concursal</h3>", 1)
    r = parse_related(html)
    assert r["acreedores"] is None  # el h3 huérfano no se anexiona la tabla vecina
    assert [a["nombre"] for a in r["administradores_concursales"]] == ["FRANCISCO DE BORJA", "SEGUNDO ADMIN"]
