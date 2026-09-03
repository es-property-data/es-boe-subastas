"""Página de resultados del buscador."""

from __future__ import annotations

import re

from boe_subastas.errors import QueryError, StructureError
from boe_subastas.parser.normalize import clean, collapse, query_param
from boe_subastas.parser.dom import make_soup, element_text


_RE_SEARCH_ID = re.compile(r"^(?P<token>.+)-(?P<start>\d*)-(?P<hits>\d+)$")

_RE_LOT_COUNT = re.compile(r"\((\d+)\s+lotes?\)")

_RE_RESULT_COUNTER = re.compile(r"Resultados\s+([\d.]+)\s+a\s+([\d.]+)\s+de\s+([\d.]+)")

_RE_STATUS = re.compile(r"^Estado:\s*(.+?)(?:\s*-\s*\[.*)?$", re.S)

_NO_RESULTS_MESSAGE = "no se han encontrado documentos"

_TOO_MANY_RESULTS_MESSAGE = "resultados obtenidos para la consulta realizada es excesivo"


def parse_listing(html: str) -> dict:
    """Interpreta una página de resultados de `subastas_ava.php`.

    Devuelve::

        {
          "total": int, "desde": int, "hasta": int,
          "token": str | None,          # id_busqueda sin sufijo -inicio-hits
          "resultados": [
            {"identificador", "lotes", "autoridad", "expediente", "estado"}
          ],
        }
    """
    soup = make_soup(html)
    page_text = collapse(soup.get_text(" ")) or ""

    if _TOO_MANY_RESULTS_MESSAGE in page_text:
        raise QueryError(
            "La fuente rechazó la consulta por devolver demasiados resultados. "
            "Añada más filtros (por ejemplo --status o --asset-type) para acotarla."
        )

    results = []
    for li in soup.select("div.listadoResult li.resultado-busqueda"):
        link = li.find("a", href=re.compile(r"detalleSubasta\.php"))
        if link is None:
            raise StructureError("Resultado de búsqueda sin enlace a la ficha.")
        identifier = query_param(link["href"], "idSub")
        if not identifier:
            raise StructureError("Resultado de búsqueda sin parámetro idSub.")

        h3 = collapse(element_text(li.find("h3"))) or ""
        lot_count_match = _RE_LOT_COUNT.search(h3)

        case_number = status = None
        for p in li.find_all("p"):
            p_text = collapse(element_text(p)) or ""
            if p_text.startswith("Expediente:"):
                case_number = clean(p_text.removeprefix("Expediente:")) or None
            elif p_text.startswith("Estado:"):
                m = _RE_STATUS.match(p_text)
                status = m.group(1) if m else None

        results.append(
            {
                "identificador": identifier,
                "lotes": int(lot_count_match.group(1)) if lot_count_match else None,
                "autoridad": collapse(element_text(li.find("h4"))),
                "expediente": case_number,
                "estado": status,
            }
        )

    counter_match = _RE_RESULT_COUNTER.search(page_text)
    if counter_match:
        # Los números pueden llevar punto de millar («Resultados 1 a 50 de 1.006»).
        start, end, total = (int(g.replace(".", "")) for g in counter_match.groups())
    elif _NO_RESULTS_MESSAGE in page_text.casefold():
        start = end = total = 0
    else:
        # Sin contador no se puede paginar con fiabilidad: mejor fallar en alto
        # que truncar la recolección en silencio.
        raise StructureError(
            "La página de resultados no contiene el contador «Resultados N a M "
            "de T» ni el mensaje de búsqueda vacía: la estructura de la fuente "
            "ha cambiado."
        )

    token = None
    for link in soup.select("ul.navlist li a[href]"):
        search_id = query_param(link["href"], "id_busqueda")
        if search_id:
            m = _RE_SEARCH_ID.match(search_id)
            token = m.group("token") if m else search_id
            break

    return {
        "total": total,
        "desde": start,
        "hasta": end,
        "token": token,
        "resultados": results,
    }
