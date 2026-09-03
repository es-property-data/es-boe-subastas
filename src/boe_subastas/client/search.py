"""Búsqueda en el portal: consulta, paginación y particionado automático."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, timedelta

from boe_subastas.client.connection import Connection
from boe_subastas.errors import QueryError, StructureError
from boe_subastas.models import PROVINCES, STATUSES
from boe_subastas.parser.listing import parse_listing

log = logging.getLogger(__name__)

# Índices fijos de los filtros del buscador avanzado (pares campo[i]/dato[i]).
_SEARCH_FIELDS = {
    "origin": (0, "SUBASTA.ORIGEN"),
    "authority": (1, "SUBASTA.AUTORIDAD"),
    "status": (2, "SUBASTA.ESTADO.CODIGO"),
    "asset_type": (3, "BIEN.TIPO"),
    "address": (5, "BIEN.DIRECCION"),
    "postal_code": (6, "BIEN.CODPOSTAL"),
    "locality": (7, "BIEN.LOCALIDAD"),
    "province": (8, "BIEN.COD_PROVINCIA"),
    "auction_id": (15, "SUBASTA.ID_SUBASTA_BUSCAR"),
    "start_date_from": (18, "SUBASTA.FECHA_INICIO"),
    "start_date_to": (18, "SUBASTA.FECHA_INICIO"),
}
# Filtros de rango: clave -> posición en dato[i][N].
_RANGE_FIELDS = {"start_date_from": 0, "start_date_to": 1}
# Clave interna de filtro -> cómo nombrarla en los mensajes para personas.
_FILTER_LABELS = {
    "province": "--province", "status": "--status", "origin": "--origin",
    "asset_type": "--asset-type", "locality": "--locality",
    "postal_code": "--postal-code", "address": "--address",
    "authority": "--authority", "auction_id": "identificador",
    "start_date_from": "inicio desde", "start_date_to": "inicio hasta",
}

# Límites del particionado automático por fecha de inicio, usados cuando la
# fuente rechaza una consulta por «excesiva». Fijos (no derivados del reloj)
# para que dos ejecuciones sobre una fuente sin cambios produzcan la misma
# partición y, por tanto, la misma salida en el mismo orden. El portal opera
# desde 2016; las ventanas futuras vacías se descartan con una sola petición.
_PARTITION_DATE_MIN = date(2015, 1, 1)
_PARTITION_DATE_MAX = date(2099, 12, 31)


def _describe_filters(filters: dict[str, str]) -> str:
    """Filtros en formato legible para los mensajes de stderr."""
    return ", ".join(f"{_FILTER_LABELS.get(k, k)} {v}" for k, v in filters.items())


def search_pages(
    connection: Connection, filters: dict[str, str], page_hits: int = 50
) -> Iterator[dict]:
    """Ejecuta una búsqueda y produce cada página de resultados parseada."""
    params: dict[str, str | int] = {"accion": "Buscar", "page_hits": page_hits,
                                    "sort_field[0]": "SUBASTA.FECHA_FIN",
                                    "sort_order[0]": "desc"}
    for key, value in filters.items():
        if key not in _SEARCH_FIELDS:
            raise ValueError(f"Filtro de búsqueda desconocido: {key!r}")
        index, field = _SEARCH_FIELDS[key]
        params[f"campo[{index}]"] = field
        if key in _RANGE_FIELDS:
            params[f"dato[{index}][{_RANGE_FIELDS[key]}]"] = value
            params.setdefault(f"dato[{index}][{1 - _RANGE_FIELDS[key]}]", "")
        else:
            params[f"dato[{index}]"] = value

    page = parse_listing(connection.get("subastas_ava.php", params))
    yield page
    while page["hasta"] < page["total"]:
        if not page["token"]:
            raise StructureError(
                "Faltan resultados pero la página no expone el token de "
                "paginación id_busqueda."
            )
        previous = page["hasta"]
        page = parse_listing(
            connection.get(
                "subastas_ava.php",
                {
                    "accion": "Mas",
                    "id_busqueda": f"{page['token']}-{page['hasta']}-{page_hits}",
                },
            )
        )
        if page["hasta"] <= previous:
            raise StructureError(
                "La paginación de la fuente no avanza: estructura cambiada."
            )
        yield page


def search(connection: Connection, filters: dict[str, str], page_hits: int = 50) -> Iterator[dict]:
    """Produce cada resultado del listado (dicts de `parse_listing`).

    Si la fuente rechaza la consulta por devolver demasiados resultados,
    la divide automáticamente en subconsultas (primero por estado, después
    por rangos de fecha de inicio) y une los resultados, deduplicados por
    identificador. El orden entonces es el de las subconsultas, no el
    orden global del portal.
    """
    seen: set[str] = set()
    for page in _partitioned_pages(connection, dict(filters), page_hits):
        for item in page["resultados"]:
            if item["identificador"] in seen:
                continue
            seen.add(item["identificador"])
            yield item


def _partitioned_pages(
    connection: Connection, filters: dict[str, str], page_hits: int
) -> Iterator[dict]:
    pages = search_pages(connection, filters, page_hits)
    try:
        # El rechazo por consulta excesiva solo puede llegar con la
        # primera página; a partir de ahí se reemite tal cual.
        first = next(pages)
    except StopIteration:
        return
    except QueryError:
        yield from _partition(connection, filters, page_hits)
        return
    yield first
    yield from pages


def _partition(
    connection: Connection, filters: dict[str, str], page_hits: int
) -> Iterator[dict]:
    # Cascada de dimensiones, de la más segura a la menos: estado y
    # provincia son particiones exhaustivas de la fuente (provincia
    # incluye el código 00 «No consta»); el rango de fecha de inicio es
    # el último recurso porque el filtro del portal excluye las subastas
    # sin fecha de inicio asignada.
    if "status" not in filters:
        log.info(
            "La fuente rechazó la consulta por amplia; se divide por "
            "estado (%s).",
            ", ".join(STATUSES),
        )
        for status in STATUSES:
            yield from _partitioned_pages(connection, 
                {**filters, "status": status}, page_hits
            )
        return

    if "province" not in filters:
        log.info(
            "La fuente rechazó la consulta por amplia (estado %s); se "
            "divide por provincia.",
            filters["status"],
        )
        for code in PROVINCES:
            yield from _partitioned_pages(connection, 
                {**filters, "province": code}, page_hits
            )
        return

    try:
        start = date.fromisoformat(
            filters.get("start_date_from")
            or _PARTITION_DATE_MIN.isoformat()
        )
        end = date.fromisoformat(
            filters.get("start_date_to")
            or _PARTITION_DATE_MAX.isoformat()
        )
    except ValueError as exc:
        raise QueryError(
            f"Filtro de fecha de inicio inválido: {exc}"
        ) from exc
    if start >= end:
        # Ni un solo día cabe: caso teórico (miles de subastas iniciadas
        # el mismo día en la misma provincia y estado). Se registra la
        # ventana omitida y se continúa con el resto de particiones en
        # lugar de abortar un crawl ya parcialmente emitido.
        log.error(
            "La fuente rechaza incluso la ventana de un solo día "
            "%s (filtros %s); se omiten sus resultados.",
            start.isoformat(), _describe_filters(filters),
        )
        return
    if "start_date_to" not in filters:
        # Primera bisección de esta rama (el límite superior solo lo pone
        # el propio particionado).
        log.warning(
            "Se recurre a la bisección por fecha de inicio: las subastas "
            "sin fecha de inicio asignada en la fuente pueden quedar "
            "fuera de estos resultados (filtros %s).",
            _describe_filters(filters),
        )
    middle = start + (end - start) // 2
    log.info(
        "La fuente rechazó la consulta por amplia; se divide por fecha de "
        "inicio: %s..%s y %s..%s.",
        start.isoformat(), middle.isoformat(),
        (middle + timedelta(days=1)).isoformat(), end.isoformat(),
    )
    yield from _partitioned_pages(connection, 
        {
            **filters,
            "start_date_from": start.isoformat(),
            "start_date_to": middle.isoformat(),
        },
        page_hits,
    )
    yield from _partitioned_pages(connection, 
        {
            **filters,
            "start_date_from": (middle + timedelta(days=1)).isoformat(),
            "start_date_to": end.isoformat(),
        },
        page_hits,
    )


def locate(connection: Connection, auction_id: str) -> dict | None:
    """Busca una subasta por identificador; None si la fuente no la lista."""
    for item in search(connection, {"auction_id": auction_id}):
        if item["identificador"] == auction_id:
            return item
    return None
