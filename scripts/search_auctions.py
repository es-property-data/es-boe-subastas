#!/usr/bin/env python
"""Busca subastas y las muestra como un listado legible.

Es un consumidor del recolector: por debajo ejecuta `boe-subastas search` con
los mismos filtros y pinta un resumen de dos líneas por sobre según llega
(con --detail, la ficha completa). Al terminar cada bloque de estado imprime
cuántas subastas había en él (una subasta con varios lotes cuenta una sola
vez), y al final el total si hubo varios estados.

Sin --status se buscan todos los estados: si la fuente rechaza la consulta
por amplia, el recolector la divide automáticamente en subconsultas.

Ejemplos:
    python scripts/search_auctions.py --province "Illes Balears" --limit 10
    python scripts/search_auctions.py --province 07 --status PU --detail
    python scripts/search_auctions.py --province 07 --auth --save baleares.jsonl
"""

from __future__ import annotations

import argparse
import os
import sys

from _format import (
    status_footer,
    consume_collector,
    render_detail,
    render_summary,
    dim,
)

try:
    from boe_subastas import models
except ImportError:  # el paquete no está instalado en este entorno
    models = None


def _codes(table: dict | None) -> str:
    if not table:
        return ""
    return "; ".join(f"{code}={name}" for code, name in table.items())


# Opción del script -> opción equivalente del CLI boe-subastas.
_CLI_FILTERS = {
    "province": "--province",
    "status": "--status",
    "origin": "--origin",
    "asset_type": "--asset-type",
    "locality": "--locality",
    "postal_code": "--postal-code",
    "address": "--address",
    "authority": "--authority",
    "since": "--since",
    "limit": "--limit",
}


def main() -> int:
    arguments = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    arguments.add_argument(
        "--province",
        help="provincia del bien: código INE o nombre oficial "
        "(p. ej. 07 o 'Illes Balears')",
    )
    arguments.add_argument(
        "--status",
        help="estado de la subasta: "
        + (_codes(models.STATUSES if models else None)
           or "PU, EJ, SU, CA, PC o FS"),
    )
    arguments.add_argument(
        "--origin",
        help="origen de la subasta: "
        + (_codes(models.ORIGINS if models else None) or "J, N, A, R o G"),
    )
    arguments.add_argument(
        "--asset-type",
        help="tipo de bien: "
        + (_codes(models.ASSET_TYPES if models else None) or "I, V o M"),
    )
    arguments.add_argument(
        "--locality", help="localidad del bien (texto libre, p. ej. PALMA)"
    )
    arguments.add_argument(
        "--postal-code", help="código postal del bien (p. ej. 07001)"
    )
    arguments.add_argument(
        "--address", help="texto a buscar en la dirección del bien"
    )
    arguments.add_argument(
        "--authority",
        help="texto a buscar en la autoridad gestora (juzgado, AEAT…)",
    )
    arguments.add_argument(
        "--since",
        metavar="FECHA",
        help="solo subastas con fecha de inicio desde FECHA (AAAA-MM-DD)",
    )
    arguments.add_argument(
        "--limit", metavar="N", help="corta al alcanzar N sobres"
    )
    arguments.add_argument(
        "--auth",
        action="store_true",
        help="usa la sesión autenticada del portal (importes de pujas en curso)",
    )
    arguments.add_argument(
        "--detail",
        action="store_true",
        help="ficha completa de cada sobre en vez del resumen de dos líneas",
    )
    arguments.add_argument(
        "--save",
        metavar="FICHERO",
        help="guarda además los sobres JSONL crudos ahí",
    )
    args = arguments.parse_args()

    command_args = ["search"]
    for option, cli_option in _CLI_FILTERS.items():
        value = getattr(args, option)
        if value:
            command_args += [cli_option, str(value)]
    if args.auth:
        command_args.append("--auth")

    paint = render_detail if args.detail else render_summary

    # Recuento por bloque de estado: los resultados llegan agrupados por
    # estado (la búsqueda de todos los estados se ejecuta estado a estado) y
    # al cerrarse cada bloque se imprime cuántas subastas contenía. Una
    # subasta con varios lotes emite varios sobres pero cuenta una sola vez.
    block = {"status": None, "ids": set(), "envelopes": 0}
    statuses_seen: set[str] = set()
    total_ids: set[str] = set()
    total_envelopes = 0

    def close_block() -> None:
        if block["status"] is not None and block["envelopes"]:
            status_footer(block["status"], len(block["ids"]), block["envelopes"])

    def view(envelope: dict) -> None:
        nonlocal total_envelopes
        data = envelope.get("data") or {}
        auction = data.get("subasta") or {}
        status = auction.get("estado") or "(sin estado)"
        identifier = (
            data.get("identificador_subasta")
            or (envelope.get("meta") or {}).get("external_id")
            or "?"
        )
        if status != block["status"]:
            close_block()
            block["status"] = status
            block["ids"] = set()
            block["envelopes"] = 0
        paint(envelope)
        block["ids"].add(identifier)
        block["envelopes"] += 1
        statuses_seen.add(status)
        total_ids.add(identifier)
        total_envelopes += 1

    save_stream = None
    if args.save:
        try:
            save_stream = open(args.save, "w", encoding="utf-8")
        except OSError as exc:
            print(f"no se pudo escribir {args.save}: {exc}", file=sys.stderr)
            return 2
    try:
        code = consume_collector(command_args, view, save_stream)
    finally:
        if save_stream is not None:
            save_stream.close()

    close_block()
    if len(statuses_seen) > 1:
        print(dim(
            f"  Total: {len(total_ids)} subasta(s) en {total_envelopes} sobre(s)"
        ))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # «script | head»: terminación normal del consumidor.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
