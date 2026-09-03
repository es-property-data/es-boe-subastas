"""Armazón común de la ficha de subasta (`detalleSubasta.php`).

Lo que comparten sus pestañas: detección de ficha inexistente, bloques
`div#idBloqueDatosN`, pestañas de navegación, avisos de cabecera, listas de
documentos y vocabulario transversal (campos económicos, encabezado de lote).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from bs4.element import Tag

from boe_subastas.errors import ItemNotFoundError, StructureError
from boe_subastas.parser.normalize import canonical_url, collapse, query_param
from boe_subastas.parser.dom import make_soup, element_text


LOT_HEADING_RE = re.compile(r"^Lote\s+(\d+)$")

# Campos económicos: normalización a número.
ECONOMIC_AMOUNT_KEYS = frozenset({
    "cantidad_reclamada",
    "valor_subasta",
    "tasacion",
    "puja_minima",
    "tramos_pujas",
    "importe_deposito",
})


def block_table(soup: BeautifulSoup, block_id: str, context: str) -> Tag:
    block = soup.find("div", id=block_id)
    table = block.find("table") if isinstance(block, Tag) else None
    if table is None:
        ensure_detail_page(soup)
        raise StructureError(
            f"No se encontró la tabla de «{context}» (div#{block_id})."
        )
    return table


def ensure_detail_page(soup: BeautifulSoup) -> None:
    """Distingue una ficha inexistente de un cambio de estructura."""
    if soup.find("div", id="tabs") is None and soup.find(
        "div", id=re.compile(r"^idBloqueDatos")
    ) is None:
        content = collapse(element_text(soup.find("div", id="contenido"))) or ""
        raise ItemNotFoundError(
            "La fuente no devolvió una ficha de subasta. "
            f"Contenido recibido: {content[:200]!r}"
        )


def documents(container: Tag) -> list[dict]:
    docs = []
    for link in container.select("ul.enlaces li.puntoPDF a[href]"):
        docs.append(
            {"nombre": collapse(link.get_text(" ")), "url": canonical_url(link["href"])}
        )
    return docs


def parse_tabs(html: str) -> list[dict]:
    """Pestañas de la ficha: [{"texto": "Pujas", "ver": 5}, ...]."""
    soup = make_soup(html)
    ensure_detail_page(soup)
    tabs = []
    for link in soup.select("div#tabs ul.navlist a[href]"):
        view = query_param(link["href"], "ver")
        tabs.append(
            {
                "texto": collapse(link.get_text(" ")),
                "ver": int(view) if view and view.isdigit() else None,
            }
        )
    return tabs
