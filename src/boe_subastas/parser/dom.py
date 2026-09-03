"""Ayudas genéricas sobre el árbol HTML (BeautifulSoup).
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from bs4.element import Tag

from boe_subastas.parser.normalize import clean, collapse, normalize_amount, normalize_text


_HTML_PARSER = "lxml"


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, _HTML_PARSER)


def element_text(element: Tag | None) -> str | None:
    if element is None:
        return None
    # Sin separador: un separador artificial insertaría espacios fantasma en
    # las fronteras de los elementos inline (<strong>, <span>) y alteraría el
    # literal de la fuente. Los <br> sí son saltos reales.
    for br in element.find_all("br"):
        br.replace_with("\n")
    return clean(element.get_text())


def table_rows(table: Tag) -> list[tuple[str, Tag]]:
    pairs = []
    for tr in table.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if th is None or td is None:
            continue
        label = collapse(th.get_text(" "))
        if label:
            pairs.append((label, td))
    return pairs


def map_table(
    table: Tag, field_map: dict[str, str], amount_keys: frozenset[str] = frozenset()
) -> tuple[dict, dict]:
    """Convierte una tabla th/td en un dict de claves estables.

    Devuelve (data, unmapped): `data` con todas las claves del mapa (None si
    la fila no existe) y `unmapped` con las filas cuya etiqueta no está en el mapa,
    conservando la etiqueta literal de la fuente. Solo las claves listadas en
    `amount_keys` se convierten a número; el resto conserva su literal.
    """
    data = {key: None for key in field_map.values()}
    unmapped: dict[str, str | None] = {}
    for label, td in table_rows(table):
        key = field_map.get(label.casefold())
        if key is not None:
            text = element_text(td)
            data[key] = (
                normalize_amount(text) if key in amount_keys
                else normalize_text(text)
            )
        else:
            unmapped[label] = normalize_text(element_text(td))
    return data, unmapped
