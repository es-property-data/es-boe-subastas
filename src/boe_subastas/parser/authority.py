"""Pestaña «Autoridad gestora» de la ficha (ver=2)."""

from __future__ import annotations

from boe_subastas.parser.detail import block_table
from boe_subastas.parser.dom import map_table, make_soup


_AUTHORITY_FIELDS = {
    "código": "codigo",
    "descripción": "descripcion",
    "dirección": "direccion",
    "teléfono": "telefono",
    "fax": "fax",
    "correo electrónico": "correo_electronico",
}


def parse_authority(html: str) -> dict:
    """Interpreta la pestaña «Autoridad gestora» (ver=2)."""
    soup = make_soup(html)
    table = block_table(soup, "idBloqueDatos2", "Datos de la autoridad gestora")
    data, unmapped = map_table(table, _AUTHORITY_FIELDS)
    data["otros"] = unmapped or None
    return data
