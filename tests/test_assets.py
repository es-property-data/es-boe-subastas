"""Pestaña «Bienes» / «Lotes» (ver=3)."""

import pytest

from boe_subastas.errors import StructureError
from boe_subastas.parser.assets import parse_assets
from conftest import BROKEN_ASSETS_HTML, read_fixture


def test_lot_page_of_judicial_auction():
    page = parse_assets(read_fixture("SUB-JA-2026-265000", "lots", "auction-lot-01.html"))
    assert page["numero_lote"] == 1
    assert page["lotes_disponibles"] == [1, 2]
    assert page["descripcion"] == "SUBASTA VIVIENDA EN SANT JORDI (SAN JOSÉ)."
    lot = page["datos_lote"]
    assert lot["valor_subasta"] == 262046.95
    assert lot["tasacion"] == 0.0
    assert lot["importe_deposito"] == 13102.35
    assert lot["puja_minima"] == "Sin puja mínima"
    assert lot["tramos_pujas"] == 5240.94
    assert lot["cantidad_reclamada"] is None
    assert lot["otros"] is None
    (asset,) = page["bienes"]
    assert (asset["numero"], asset["tipo"], asset["subtipo"]) == (1, "Inmueble", "Vivienda")
    assert asset["idufir"] == "07010000670403"
    assert asset["referencia_catastral"] == "1767906CD6016N0052UE"
    assert asset["codigo_postal"] == "07817"
    assert asset["localidad"] == "SANT JORDI"
    assert asset["vivienda_habitual"] == "Sí"
    assert asset["situacion_posesoria"] is None  # «No consta»
    assert asset["cargas"] == "SE ADJUNTA CERTIFICACION DE CARGAS."
    assert asset["documentos"] == [] and asset["imagenes"] == []


def test_lot_page_without_optional_rows():
    (asset,) = parse_assets(read_fixture("SUB-JA-2026-265000", "lots", "auction-lot-02.html"))["bienes"]
    assert asset["vivienda_habitual"] is None  # la fila no existe en este lote
    assert asset["referencia_catastral"] == "1767906CD6016N007ML"


def test_trailing_spaces_and_lot_number_from_third_lot():
    page = parse_assets(read_fixture("SUB-JA-2026-265003", "lots", "auction-lot-03.html"))
    assert page["numero_lote"] == 3
    assert page["bienes"][0]["referencia_catastral"] == "3631739DD7833S0013KY"
    first = parse_assets(read_fixture("SUB-JA-2026-265003", "lots", "auction-lot-01.html"))
    assert first["bienes"][0]["referencia_catastral"] == "3631739DD7833S0011HR"


def test_assets_page_without_lots_keeps_fixed_width_spacing_and_documents():
    page = parse_assets(read_fixture("SUB-AT-2026-26R0886001200", "auction-assets.html"))
    assert page["numero_lote"] is None and page["datos_lote"] is None
    assert page["descripcion_anuncio"] is not None
    (asset,) = page["bienes"]
    assert asset["cargas"] == 4308.19
    assert asset["titulo_juridico"] == "PLENO DOMINIO"
    assert asset["direccion"] == "CL MAGALLANES                46      00 03"
    assert [d["nombre"] for d in asset["documentos"]] == ["catastro", "Nota simple"]
    assert len(asset["imagenes"]) == 2
    assert all(url.startswith("https://subastas.boe.es/verDocumento.php") for url in asset["imagenes"])


def test_vehicle_like_unknown_rows_go_to_otros():
    html = read_fixture("SUB-RC-2026-07003001815", "auction-assets.html").replace(
        "<th>IDUFIR</th>", "<th>Matrícula</th>", 1
    )
    (asset,) = parse_assets(html)["bienes"]
    assert asset["idufir"] is None
    assert asset["otros"] == {"Matrícula": "07027000173216"}


def test_unrecognizable_assets_page_is_structure_error():
    with pytest.raises(StructureError):
        parse_assets(BROKEN_ASSETS_HTML)
