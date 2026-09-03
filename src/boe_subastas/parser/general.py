"""Pestaña «Información general» de la ficha (ver=1)."""

from __future__ import annotations

from bs4 import BeautifulSoup

from boe_subastas.errors import StructureError
from boe_subastas.parser.detail import (
    ECONOMIC_AMOUNT_KEYS,
    block_table,
    documents,
)
from boe_subastas.parser.dom import element_text, make_soup, map_table
from boe_subastas.parser.normalize import collapse, parse_date



def _header_notices(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """(advertencia, aviso_estado) de la cabecera de la ficha, antes de #tabs."""
    header_warning = status_notice = None
    notice = soup.select_one("div#contenido div.caja.gris.aviso p")
    if notice is not None and notice.find_parent("div", id="tabs") is None:
        header_warning = collapse(element_text(notice))
    for p in soup.select("div#contenido p.destaca"):
        if p.find_previous("div", id="tabs") is None:
            status_notice = collapse(element_text(p))
            break
    return header_warning, status_notice


_GENERAL_FIELDS = {
    "identificador": "identificador",
    "tipo de subasta": "tipo",
    "expediente": "expediente",
    "cuenta expediente": "cuenta_expediente",
    "fecha de inicio": "fecha_inicio",
    "fecha de conclusión": "fecha_conclusion",
    "cantidad reclamada": "cantidad_reclamada",
    "lotes": "lotes",
    "forma adjudicación": "forma_adjudicacion",
    "anuncio boe": "anuncio_boe",
    "valor subasta": "valor_subasta",
    "tasación": "tasacion",
    "valor de tasación": "tasacion",
    "puja mínima": "puja_minima",
    "tramos entre pujas": "tramos_pujas",
    "importe del depósito": "importe_deposito",
}

_DATE_FIELDS = ("fecha_inicio", "fecha_conclusion")


def parse_general(html: str) -> dict:
    """Interpreta la pestaña «Información general» (ver=1)."""
    soup = make_soup(html)
    table = block_table(soup, "idBloqueDatos1", "Datos de la subasta")
    data, unmapped = map_table(table, _GENERAL_FIELDS, ECONOMIC_AMOUNT_KEYS)

    if not data["identificador"]:
        raise StructureError(
            "La tabla «Datos de la subasta» no contiene el campo Identificador."
        )

    for field in _DATE_FIELDS:
        raw = data[field]
        data[field] = parse_date(raw if isinstance(raw, str) else None)

    lots = data["lotes"]
    if isinstance(lots, str) and collapse(lots).casefold() == "sin lotes":
        data["lotes"] = 0
    elif isinstance(lots, (int, float)) or (isinstance(lots, str) and lots.isdigit()):
        data["lotes"] = int(lots)
    else:
        raise StructureError(f"Valor de «Lotes» no reconocido: {lots!r}")

    block = soup.find("div", id="idBloqueDatos1")
    data["documentos"] = documents(block)
    data["advertencia"], data["aviso_estado"] = _header_notices(soup)
    data["otros"] = unmapped or None
    return data
