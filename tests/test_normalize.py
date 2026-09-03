"""Reglas de formato del contrato: importes, fechas, texto y URLs."""

from boe_subastas.parser import normalize as n


def test_parse_amount_converts_spanish_format_to_number():
    assert n.parse_amount("145.660,86 €") == 145660.86
    assert n.parse_amount("0,00 €") == 0.0
    assert n.parse_amount("1.234.567,89 €") == 1234567.89
    assert n.parse_amount("Sin puja mínima") is None
    assert n.parse_amount(None) is None


def test_normalize_amount_keeps_literals_and_maps_absence_to_none():
    assert n.normalize_amount("262.046,95 €") == 262046.95
    assert n.normalize_amount("Sin puja mínima") == "Sin puja mínima"
    assert n.normalize_amount("No consta") is None
    assert n.normalize_amount("No disponible") is None
    assert n.normalize_amount("-") is None
    assert n.normalize_amount("   ") is None


def test_normalize_text_never_converts_to_number():
    assert n.normalize_text("500,00 €") == "500,00 €"
    assert n.normalize_text("No consta") is None
    assert n.normalize_text("No consta (escritura de 2005)") == "No consta (escritura de 2005)"


def test_clean_removes_markup_breaks_but_keeps_inner_spacing():
    assert n.clean("Superficie: 112 m2.\n          Útil: 82 m2.") == "Superficie: 112 m2. Útil: 82 m2."
    assert n.clean("CL MAGALLANES                46      00 03   ") == "CL MAGALLANES                46      00 03"
    assert n.clean("\xa0 texto \xa0") == "texto"
    assert n.clean("") is None
    assert n.clean(None) is None


def test_collapse_flattens_all_whitespace():
    assert n.collapse("  Sin pujas  en el lote 1 \n de esta subasta ") == "Sin pujas en el lote 1 de esta subasta"
    assert n.collapse("") is None


def test_parse_date_prefers_iso_suffix_with_offset():
    assert n.parse_date("25-08-2026 18:00:00 CET  (ISO: 2026-08-25T18:00:00+02:00)") == "2026-08-25T18:00:00+02:00"
    assert n.parse_date("31-08-2026 18:38:01 CET") == "2026-08-31T18:38:01"
    assert n.parse_date("sin fecha") is None
    assert n.parse_date(None) is None


def test_canonical_url_resolves_and_strips_reg_zone():
    assert (
        n.canonical_url("./verDocumento.php?idSub=SUB-X&idDoc=1-abc")
        == "https://subastas.boe.es/verDocumento.php?idSub=SUB-X&idDoc=1-abc"
    )
    assert n.canonical_url("/reg/detalleSubasta.php?idSub=SUB-X#cont-tabs") == (
        "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-X"
    )
    assert n.canonical_url("") is None


def test_query_param_reads_portal_hrefs():
    href = "./detalleSubasta.php?idSub=SUB-JA-2026-265000&ver=3&idLote=2&idBus=abc,,--50"
    assert n.query_param(href, "idSub") == "SUB-JA-2026-265000"
    assert n.query_param(href, "idLote") == "2"
    assert n.query_param(href, "noexiste") is None
    assert n.query_param(None, "idSub") is None
