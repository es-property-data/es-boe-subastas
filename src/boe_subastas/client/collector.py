"""Recolección de una subasta: descarga su ficha completa y ensambla los sobres.

Cada unidad subastada es un ítem propio: la subasta entera si no hay lotes,
o cada lote (`external_id` con sufijo ``/L<n>``) si los hay.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from boe_subastas.client.connection import Connection
from boe_subastas.errors import ItemNotFoundError, StructureError
from boe_subastas.models import BASE_URL
from boe_subastas.parser.assets import parse_assets
from boe_subastas.parser.authority import parse_authority
from boe_subastas.parser.bids import parse_bids
from boe_subastas.parser.detail import parse_tabs
from boe_subastas.parser.general import parse_general
from boe_subastas.parser.related import parse_related

log = logging.getLogger(__name__)


def detail_url(auction_id: str, lot: int | None = None) -> str:
    """URL pública canónica de la ficha de una subasta (o de uno de sus lotes)."""
    url = f"{BASE_URL}detalleSubasta.php?idSub={auction_id}"
    if lot is not None:
        url += f"&ver=3&idLote={lot}"
    return url


def _detail_page(connection: Connection, auction_id: str, view: int, lot: int | None = None) -> str:
    params = {"idSub": auction_id, "ver": view}
    if lot is not None:
        params["idLote"] = lot
    return connection.get("detalleSubasta.php", params)


def collect(
    connection: Connection,
    auction_id: str,
    status: str | None = None,
    case_number: str | None = None,
    only_lot: int | None = None,
) -> Iterator[tuple[str, str, dict]]:
    """Descarga la ficha completa de una subasta y produce sus sobres.

    Cada unidad subastada es un ítem propio: la subasta entera si no hay
    lotes, o cada lote (`external_id` con sufijo ``/L<n>``) si los hay.
    Con `only_lot` se limita a ese lote concreto. Produce tuplas
    ``(external_id, url, data)``.
    """
    general_html = _detail_page(connection, auction_id, view=1)
    general = parse_general(general_html)
    tabs = {p["ver"] for p in parse_tabs(general_html)}

    authority = parse_authority(_detail_page(connection, auction_id, view=2))
    related = (
        parse_related(_detail_page(connection, auction_id, view=4))
        if 4 in tabs
        else None
    )
    if related and related["otros"]:
        log.warning(
            "Subasta %s: entidades no tipificadas en «Relacionados» "
            "(emitidas en relacionados_otros): %s",
            auction_id, sorted(related["otros"]),
        )

    auction = {
        "identificador": general["identificador"],
        "tipo": general["tipo"],
        "estado": status,
        "expediente": case_number or general["expediente"],
        "cuenta_expediente": general["cuenta_expediente"],
        "fecha_inicio": general["fecha_inicio"],
        "fecha_conclusion": general["fecha_conclusion"],
        "cantidad_reclamada": general["cantidad_reclamada"],
        "lotes": general["lotes"],
        "forma_adjudicacion": general["forma_adjudicacion"],
        "anuncio_boe": general["anuncio_boe"],
        "valor_subasta": general["valor_subasta"],
        "tasacion": general["tasacion"],
        "puja_minima": general["puja_minima"],
        "tramos_pujas": general["tramos_pujas"],
        "importe_deposito": general["importe_deposito"],
        "advertencia": general["advertencia"],
        "aviso_estado": general["aviso_estado"],
        "documentos": general["documentos"],
        "autoridad_gestora": authority,
        "acreedores": related["acreedores"] if related else None,
        "administradores_concursales": (
            related["administradores_concursales"] if related else None
        ),
        "aviso_relacionados": related["aviso"] if related else None,
        "relacionados_otros": related["otros"] if related else None,
        "otros": general["otros"],
    }
    if general["otros"]:
        log.warning(
            "Subasta %s: campos no reconocidos en la ficha general: %s",
            auction_id, sorted(general["otros"]),
        )

    lot_count = general["lotes"]
    if lot_count == 0:
        if only_lot is not None:
            raise ItemNotFoundError(
                f"La subasta {auction_id} no tiene lotes: el ítem "
                f"{auction_id}/L{only_lot} no existe."
            )
        yield _envelope_without_lots(connection, auction_id, auction)
    else:
        if only_lot is not None and not 1 <= only_lot <= lot_count:
            raise ItemNotFoundError(
                f"La subasta {auction_id} tiene {lot_count} lotes: el ítem "
                f"{auction_id}/L{only_lot} no existe."
            )
        yield from _envelopes_per_lot(connection, auction_id, auction, lot_count, only_lot)


def _bids_envelope(bids: dict, lot: int | None) -> dict:
    rows = bids["pujas_maximas"]
    if rows is not None:
        # La tabla «Pujas máximas» (subasta concluida) es la autoridad:
        # un lote ausente de ella no hereda datos de otra página/lote.
        amount = None
        if lot is not None:
            for row in rows:
                if row["lote"] == lot:
                    amount = row["importe"]
                    break
        elif len(rows) == 1:
            amount = rows[0]["importe"]
        return {
            "puja_mas_alta": amount,
            "mensaje": None,
            "certificado_cierre": bids["certificado_cierre"],
        }
    return {
        "puja_mas_alta": bids["puja_mas_alta"],
        "mensaje": bids["mensaje"],
        "certificado_cierre": bids["certificado_cierre"],
    }


def _envelope_without_lots(
    connection: Connection, auction_id: str, auction: dict
) -> tuple[str, str, dict]:
    assets = parse_assets(_detail_page(connection, auction_id, view=3))
    bids = parse_bids(_detail_page(connection, auction_id, view=5))
    data = {
        "identificador_subasta": auction_id,
        "lote": None,
        "descripcion": assets["descripcion"],
        "descripcion_anuncio": assets["descripcion_anuncio"],
        "bienes": assets["bienes"],
        "pujas": _bids_envelope(bids, None),
        "subasta": auction,
    }
    return auction_id, detail_url(auction_id), data


def _lot_bids(
    connection: Connection, auction_id: str, lot: int, bids_by_lot: dict[int, dict]
) -> dict:
    if lot not in bids_by_lot:
        bids = parse_bids(_detail_page(connection, auction_id, view=5, lot=lot))
        if bids["numero_lote"] not in (None, lot):
            raise StructureError(
                f"Se pidieron las pujas del lote {lot} de {auction_id} pero "
                f"la fuente devolvió las del lote {bids['numero_lote']}."
            )
        bids_by_lot[lot] = bids
    return bids_by_lot[lot]


def _envelopes_per_lot(
    connection: Connection,
    auction_id: str,
    auction: dict,
    lot_count: int,
    only_lot: int | None = None,
) -> Iterator[tuple[str, str, dict]]:
    lots = [only_lot] if only_lot is not None else range(1, lot_count + 1)

    # Primera página de pujas: si la subasta ha concluido, trae la tabla
    # «Pujas máximas» con todos los lotes y evita una petición por lote.
    bids_by_lot: dict[int, dict] = {}
    first = None
    try:
        first = _lot_bids(connection, auction_id, lots[0], bids_by_lot)
    except (StructureError, ItemNotFoundError) as exc:
        log.error("Pujas del lote %d de %s no interpretables: %s",
                  lots[0], auction_id, exc)
    all_in_one = first is not None and first["pujas_maximas"] is not None

    # Un lote roto no invalida los demás: se registra, se continúa con el
    # siguiente y al final se eleva StructureError para que el CLI
    # devuelva el código 4.
    failed_lots: list[int] = []
    for lot in lots:
        try:
            assets = parse_assets(
                _detail_page(connection, auction_id, view=3, lot=lot)
            )
            if assets["numero_lote"] not in (None, lot):
                raise StructureError(
                    f"Se pidió el lote {lot} de {auction_id} pero la "
                    f"fuente devolvió el lote {assets['numero_lote']}."
                )
            bids = (
                first
                if all_in_one
                else _lot_bids(connection, auction_id, lot, bids_by_lot)
            )
        except (StructureError, ItemNotFoundError) as exc:
            failed_lots.append(lot)
            log.error(
                "Lote %d de %s no interpretable; se continúa con el "
                "siguiente: %s",
                lot,
                auction_id,
                exc,
                exc_info=True,
            )
            continue

        lot_data = assets["datos_lote"] or {}
        data = {
            "identificador_subasta": auction_id,
            "lote": {
                "numero": lot,
                "cantidad_reclamada": lot_data.get("cantidad_reclamada"),
                "valor_subasta": lot_data.get("valor_subasta"),
                "tasacion": lot_data.get("tasacion"),
                "puja_minima": lot_data.get("puja_minima"),
                "tramos_pujas": lot_data.get("tramos_pujas"),
                "importe_deposito": lot_data.get("importe_deposito"),
                "otros": lot_data.get("otros"),
            },
            "descripcion": assets["descripcion"],
            "descripcion_anuncio": assets["descripcion_anuncio"],
            "bienes": assets["bienes"],
            "pujas": _bids_envelope(bids, lot),
            "subasta": auction,
        }
        yield (
            f"{auction_id}/L{lot}",
            detail_url(auction_id, lot),
            data,
        )

    if failed_lots:
        raise StructureError(
            f"No se pudieron interpretar {len(failed_lots)} lote(s) de "
            f"{auction_id}: {failed_lots}."
        )
