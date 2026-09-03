"""Reglas de formato del contrato sobre cadenas y hrefs del portal.

Importes a número, fechas a ISO 8601, limpieza de artefactos de
marcado, marcadores de ausencia a None y URLs canónicas. No
conoce el árbol HTML ni las páginas del portal.
"""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from boe_subastas.models import BASE_URL


_ABSENCE_MARKERS = {"no consta", "no disponible", "-", ""}

_RE_LINE_BREAKS = re.compile(r"(?:[ \t]*\n[ \t]*)+")

_RE_AMOUNT = re.compile(r"^(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})\s*€$")

_RE_ISO = re.compile(r"\(ISO:\s*([0-9T:+.\-]+)\s*\)")

_RE_SPANISH_DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})\s+(\d{2}:\d{2}:\d{2})")


def clean(text: str | None) -> str | None:
    """Limpia artefactos de marcado sin colapsar los espacios internos."""
    if text is None:
        return None
    text = text.replace("\xa0", " ").replace("\r", "\n")
    text = _RE_LINE_BREAKS.sub(" ", text)
    text = text.strip()
    return text or None


def collapse(text: str | None) -> str | None:
    """Colapsa todo el espacio en blanco; para mensajes y etiquetas."""
    if text is None:
        return None
    flat = " ".join(text.split())
    return flat or None


def parse_amount(text: str | None) -> float | None:
    """Convierte «145.660,86 €» en 145660.86; None si no es un importe."""
    if not text:
        return None
    m = _RE_AMOUNT.match(text.strip())
    if not m:
        return None
    return float(Decimal(f"{m.group(1).replace('.', '')}.{m.group(2)}"))


def normalize_amount(text: str | None) -> float | str | None:
    """Normaliza una celda de importe: None si ausente, número si es un
    importe en euros, literal limpio en cualquier otro caso («Sin puja
    mínima», «Ver valor de subasta en cada lote…»)."""
    flat = collapse(text)
    if flat is None or flat.casefold() in _ABSENCE_MARKERS:
        return None
    amount = parse_amount(flat)
    if amount is not None:
        return amount
    return clean(text)


def normalize_text(text: str | None) -> str | None:
    """Normaliza una celda de texto: None si ausente, literal limpio si no.

    A diferencia de `normalize_amount`, nunca convierte a número: un campo de
    texto conserva su literal aunque su contenido parezca un importe.
    """
    flat = collapse(text)
    if flat is None or flat.casefold() in _ABSENCE_MARKERS:
        return None
    return clean(text)


def parse_date(text: str | None) -> str | None:
    """Extrae la fecha en ISO 8601 de una celda de fecha del portal.

    Prefiere el sufijo «(ISO: ...)» que emite la propia fuente (con huso);
    si no existe, reconstruye desde «DD-MM-AAAA HH:MM:SS» sin huso.
    """
    if not text:
        return None
    m = _RE_ISO.search(text)
    if m:
        return m.group(1)
    m = _RE_SPANISH_DATE.search(text)
    if m:
        day, month, year, time_of_day = m.groups()
        return f"{year}-{month}-{day}T{time_of_day}"
    return None


def canonical_url(href: str | None, base: str = BASE_URL) -> str | None:
    """Resuelve un href contra la fuente y lo canonicaliza sin zona `/reg/`."""
    if not href:
        return None
    absolute_url = urljoin(base, href.strip())
    parts = urlparse(absolute_url)
    path = parts.path
    if path.startswith("/reg/"):
        path = path[len("/reg"):]
    return urlunparse(parts._replace(path=path, fragment=""))



def query_param(href: str | None, name: str) -> str | None:
    """Valor del parámetro `name` en la query de un href del portal, o None."""
    if not href:
        return None
    query = parse_qs(urlparse(urljoin(BASE_URL, href)).query)
    return (query.get(name) or [None])[0]
