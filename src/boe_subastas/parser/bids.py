"""Pestaña «Pujas» de la ficha (ver=5)."""

from __future__ import annotations

import re

from boe_subastas.parser.detail import LOT_HEADING_RE, ensure_detail_page
from boe_subastas.parser.normalize import canonical_url, collapse, parse_amount, query_param
from boe_subastas.parser.dom import make_soup, element_text


_RE_AMOUNT_IN_TEXT = re.compile(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*€")


def parse_bids(html: str) -> dict:
    """Interpreta la pestaña «Pujas» (ver=5) en sus tres variantes.

    - Sesión iniciada, subasta activa: «Puja más alta» con importe o mensaje.
    - Sin sesión, subasta activa: mensaje («La subasta no ha recibido pujas.»,
      «La subasta ha recibido alguna puja. Para ver su importe debe acceder
      como usuario registrado.»).
    - Subasta concluida: tabla «Pujas máximas» por lote, con importes.
    """
    soup = make_soup(html)
    ensure_detail_page(soup)

    lot_number = None
    current = soup.select_one("div#tabsver ul.navlistver a.current")
    if current is not None:
        lot_id = query_param(current.get("href", ""), "idLote")
        if lot_id and lot_id.isdigit():
            lot_number = int(lot_id)
    if lot_number is None:
        for h3 in soup.select("div.bloque h3"):
            m = LOT_HEADING_RE.match(collapse(h3.get_text(" ")) or "")
            if m:
                lot_number = int(m.group(1))
                break

    certificate = None
    for link in soup.find_all("a", href=True):
        if "certificado de cierre" in (collapse(link.get_text(" ")) or "").casefold():
            certificate = canonical_url(link["href"])
            break

    max_bids = None
    for h4 in soup.find_all("h4"):
        if (collapse(h4.get_text(" ")) or "").casefold().startswith("pujas máximas"):
            table = h4.find_next("table")
            if table is None:
                break
            max_bids = []
            for tr in table.find_all("tr"):
                cells = [element_text(c) for c in tr.find_all(["th", "td"])]
                if len(cells) >= 2 and cells[0] and cells[0].isdigit():
                    max_bids.append(
                        {"lote": int(cells[0]), "importe": parse_amount(cells[1])}
                    )
            break

    highest_bid = None
    message = None
    found = False
    for h4 in soup.find_all("h4"):
        title = (collapse(h4.get_text(" ")) or "").casefold()
        if title.startswith("puja más alta") or title.startswith("puja máxima"):
            paragraph = h4.find_next("p")
            if paragraph is None:
                continue
            found = True
            highlighted = paragraph.find("strong", class_="destaca")
            highest_bid = parse_amount(element_text(highlighted))
            if highest_bid is None:
                paragraph_text = collapse(element_text(paragraph)) or ""
                m = _RE_AMOUNT_IN_TEXT.search(paragraph_text)
                if m:
                    highest_bid = parse_amount(f"{m.group(1)},{m.group(2)} €")
                else:
                    message = paragraph_text or None
            break
    if not found and max_bids is None:
        # Variante sin encabezado reconocible: mensaje suelto centrado
        # («La subasta ha recibido alguna puja. Para ver su importe debe
        # acceder como usuario registrado.», «La subasta no ha recibido
        # pujas.», etc.).
        message = collapse(element_text(soup.select_one("div#contenido p.centrador")))

    return {
        "numero_lote": lot_number,
        "puja_mas_alta": highest_bid,
        "mensaje": message,
        "pujas_maximas": max_bids,
        "certificado_cierre": certificate,
    }
