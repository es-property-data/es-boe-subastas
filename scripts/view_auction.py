#!/usr/bin/env python
"""Muestra la ficha completa de una o varias subastas de forma legible.

Es un consumidor del recolector: por debajo ejecuta `boe-subastas fetch` y
pinta cada sobre según llega.

Ejemplos:
    python scripts/view_auction.py SUB-JA-2026-265000
    python scripts/view_auction.py SUB-JA-2026-265003/L2 --auth
    python scripts/view_auction.py SUB-JC-2026-264427 --save sobres.jsonl
    python scripts/view_auction.py --file sobres.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from _format import consume_collector, paint_envelope, render_detail


def _show_file(path: str) -> int:
    try:
        input_file = open(path, encoding="utf-8")
    except OSError as exc:
        print(f"no se pudo leer {path}: {exc}", file=sys.stderr)
        return 2
    with input_file:
        for number, line in enumerate(input_file, 1):
            if not line.strip():
                continue
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"aviso: línea {number} no es JSON (se ignora): {exc}",
                      file=sys.stderr)
                continue
            paint_envelope(envelope, render_detail, f"línea {number}")
    return 0


def main() -> int:
    arguments = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    arguments.add_argument(
        "ids",
        metavar="ID",
        nargs="*",
        help="identificadores de subasta o de lote (SUB-…, SUB-…/L2)",
    )
    arguments.add_argument(
        "--auth",
        action="store_true",
        help="usa la sesión autenticada del portal (importes de pujas en curso)",
    )
    arguments.add_argument(
        "--save",
        metavar="FICHERO",
        help="además de mostrar la vista, guarda los sobres JSONL crudos ahí",
    )
    arguments.add_argument(
        "--file",
        metavar="JSONL",
        help="no accede a la red: muestra los sobres de un JSONL ya guardado",
    )
    args = arguments.parse_args()

    if args.file:
        if args.ids or args.auth or args.save:
            arguments.error(
                "--file muestra un JSONL ya guardado y no admite "
                "identificadores, --auth ni --save"
            )
        return _show_file(args.file)
    if not args.ids:
        arguments.error("indique identificadores de subasta o bien --file")

    command_args = ["fetch", *args.ids]
    if args.auth:
        command_args.append("--auth")

    save_stream = None
    if args.save:
        try:
            save_stream = open(args.save, "w", encoding="utf-8")
        except OSError as exc:
            print(f"no se pudo escribir {args.save}: {exc}", file=sys.stderr)
            return 2
    try:
        return consume_collector(command_args, render_detail, save_stream)
    finally:
        if save_stream is not None:
            save_stream.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # «script | head»: terminación normal del consumidor.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
