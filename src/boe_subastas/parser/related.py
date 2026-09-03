"""Pestaña «Relacionados» de la ficha (ver=4): acreedores y administración concursal."""

from __future__ import annotations

from bs4.element import Tag

from boe_subastas.errors import StructureError
from boe_subastas.parser.detail import ensure_detail_page
from boe_subastas.parser.dom import map_table, make_soup, element_text
from boe_subastas.parser.normalize import collapse


_RELATED_ENTITY_FIELDS = {
    "nombre": "nombre",
    "nif": "nif",
    "dirección": "direccion",
    "localidad": "localidad",
    "provincia": "provincia",
    "país": "pais",
}

# Encabezado (h3) de la pestaña Relacionados.
_RELATED_ENTITIES = {
    "acreedor": "acreedores",
    "acreedores": "acreedores",
    "administrador concursal": "administradores_concursales",
    "administradores concursales": "administradores_concursales",
}


def parse_related(html: str) -> dict:
    """Interpreta la pestaña «Relacionados» (ver=4) en sus variantes.

    Según la subasta contiene acreedores (h3 «Acreedor», div#idBloqueDatos4),
    administradores concursales en subastas concursales (h3 «Administrador
    concursal», div#idBloqueDatos7), avisos («Los datos de los acreedores
    privilegiados especiales no se muestran para esta subasta.»), o cualquier
    combinación. Cada encabezado puede repetirse y su bloque puede contener
    varias tablas (una entidad por tabla); no se descarta ninguna. Devuelve::

        {
          "acreedores": [dict, ...] | None,
          "administradores_concursales": [dict, ...] | None,
          "aviso": str | None,                      # avisos de la pestaña
          "otros": {encabezado: [dict, ...]} | None,  # no tipificadas
        }
    """
    soup = make_soup(html)
    ensure_detail_page(soup)
    content = soup.find("div", id="contenido")
    if not isinstance(content, Tag):
        raise StructureError("La pestaña «Relacionados» no contiene div#contenido.")

    def after_tabs(element: Tag) -> bool:
        # El contenido propio de la pestaña va después de #tabs; lo anterior
        # (aviso de cabecera, h2 del título…) es común a toda la ficha.
        return element.find_previous("div", id="tabs") is not None

    notices = []
    for box in content.select("div.caja.gris.info"):
        if not after_tabs(box):
            continue
        text = collapse(element_text(box))
        if text:
            notices.append(text)

    groups: dict[str, list[dict]] = {}
    unmapped: dict[str, list[dict]] = {}
    has_tables = False
    for h3 in content.find_all("h3"):
        if not after_tabs(h3):
            continue
        # El bloque de la entidad es el elemento inmediatamente siguiente al
        # h3; si lo que sigue es otro encabezado u otra cosa, este h3 no tiene
        # bloque propio y no debe anexionarse la tabla de la entidad vecina.
        block = next(
            (sib for sib in h3.next_siblings if isinstance(sib, Tag)), None
        )
        if block is None or block.name != "div":
            continue
        tables = block.find_all("table")
        if not tables:
            continue
        has_tables = True
        entities = []
        for table in tables:
            data, extra = map_table(table, _RELATED_ENTITY_FIELDS)
            data["otros"] = extra or None
            entities.append(data)
        heading = collapse(h3.get_text(" ")) or ""
        key = _RELATED_ENTITIES.get(heading.casefold())
        if key is not None:
            groups.setdefault(key, []).extend(entities)
        else:
            unmapped.setdefault(heading, []).extend(entities)

    if not has_tables and not notices:
        raise StructureError(
            "La pestaña «Relacionados» no contiene ni tablas de entidades ni "
            "avisos reconocibles: la estructura de la fuente ha cambiado."
        )

    return {
        "acreedores": groups.get("acreedores") or None,
        "administradores_concursales": groups.get("administradores_concursales")
        or None,
        "aviso": " ".join(notices) if notices else None,
        "otros": unmapped or None,
    }
