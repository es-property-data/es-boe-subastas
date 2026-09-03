"""Pestaña «Bienes»/«Lotes» de la ficha (ver=3)."""

from __future__ import annotations

import re

from bs4.element import Tag

from boe_subastas.errors import StructureError
from boe_subastas.parser.detail import (
    ECONOMIC_AMOUNT_KEYS,
    LOT_HEADING_RE,
    ensure_detail_page,
    documents,
)
from boe_subastas.parser.normalize import canonical_url, clean, collapse, query_param
from boe_subastas.parser.dom import map_table, make_soup, element_text


_RE_ASSET = re.compile(r"^Bien\s+(\d+)\s*-\s*([^()]+?)(?:\s*\((.+)\))?$")

_ASSET_AMOUNT_FIELDS = frozenset({"cargas"})

_LOT_FIELDS = {
    "cantidad reclamada": "cantidad_reclamada",
    "valor subasta": "valor_subasta",
    "valor de tasación": "tasacion",
    "tasación": "tasacion",
    "puja mínima": "puja_minima",
    "tramos entre pujas": "tramos_pujas",
    "importe del depósito": "importe_deposito",
}

_ASSET_FIELDS = {
    "descripción": "descripcion",
    "idufir": "idufir",
    "referencia catastral": "referencia_catastral",
    "dirección": "direccion",
    "código postal": "codigo_postal",
    "localidad": "localidad",
    "provincia": "provincia",
    "vivienda habitual": "vivienda_habitual",
    "situación posesoria": "situacion_posesoria",
    "csv certificación registral": "csv_certificacion_registral",
    "información registral electrónica": "informacion_registral_electronica",
    "visitable": "visitable",
    "cargas": "cargas",
    "inscripción registral": "inscripcion_registral",
    "título jurídico": "titulo_juridico",
    "información adicional": "informacion_adicional",
}


def _parse_asset(h4: Tag) -> dict | None:
    heading = collapse(h4.get_text(" ")) or ""
    m = _RE_ASSET.match(heading)
    if not m:
        return None
    table = h4.find_next("table")
    if table is None:
        raise StructureError(f"El bien «{heading}» no tiene tabla de datos.")
    data, unmapped = map_table(table, _ASSET_FIELDS, _ASSET_AMOUNT_FIELDS)

    asset = {
        "numero": int(m.group(1)),
        "tipo": clean(m.group(2)),
        "subtipo": clean(m.group(3)) if m.group(3) else None,
        **data,
        "documentos": [],
        "imagenes": [],
        "otros": unmapped or None,
    }

    container = h4.parent
    if isinstance(container, Tag):
        for box in container.select("div.caja.gris"):
            legend = collapse(element_text(box.find(class_="legend"))) or ""
            links = box.select("ul.enlaces a[href]")
            if legend.casefold().startswith("documentos"):
                asset["documentos"] = documents(box)
            elif "imágenes" in legend.casefold() or "fotografías" in legend.casefold():
                asset["imagenes"] = [canonical_url(a["href"]) for a in links]
    return asset


def parse_assets(html: str) -> dict:
    """Interpreta la pestaña «Bienes»/«Lotes» (ver=3) para el lote mostrado.

    En subastas con lotes cada petición devuelve un único lote (el de
    ``idLote``); en subastas sin lotes devuelve todos los bienes.
    """
    soup = make_soup(html)
    block = soup.find("div", id="idBloqueDatos3")
    if not isinstance(block, Tag):
        ensure_detail_page(soup)
        raise StructureError("No se encontró el bloque de bienes (div#idBloqueDatos3).")

    available_lots = []
    for link in soup.select("div#tabsver ul.navlistver a[href]"):
        lot_id = query_param(link["href"], "idLote")
        if lot_id and lot_id.isdigit():
            available_lots.append(int(lot_id))

    lot_number = None
    for h3 in block.find_all("h3"):
        m = LOT_HEADING_RE.match(collapse(h3.get_text(" ")) or "")
        if m:
            lot_number = int(m.group(1))
            break

    description = None
    for box in block.select("div.caja"):
        if "gris" not in (box.get("class") or []):
            description = element_text(box)
            break

    announcement = element_text(block.select_one("p > em"))

    lot_data = None
    for h3 in block.find_all("h3"):
        h3_text = collapse(h3.get_text(" ")) or ""
        if h3_text.casefold().startswith("datos relacionados con la subasta"):
            table = h3.find_next("table")
            if table is None:
                raise StructureError("El lote no tiene tabla de datos de subasta.")
            lot_data, lot_extra = map_table(
                table, _LOT_FIELDS, ECONOMIC_AMOUNT_KEYS
            )
            lot_data["otros"] = lot_extra or None
            break

    assets = []
    for h4 in block.find_all("h4"):
        asset = _parse_asset(h4)
        if asset is not None:
            assets.append(asset)

    if not assets:
        raise StructureError("La pestaña de bienes no contiene ningún bien reconocible.")

    return {
        "numero_lote": lot_number,
        "lotes_disponibles": sorted(set(available_lots)),
        "descripcion": description,
        "descripcion_anuncio": announcement,
        "datos_lote": lot_data,
        "bienes": assets,
    }
