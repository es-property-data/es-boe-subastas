#!/usr/bin/env python
"""Valida ficheros JSONL de sobres contra schemas/item.schema.json.

Cada línea se valida como un documento independiente. Devuelve 0 si todo
valida, 1 si alguna línea falla y 2 si no se pudo leer algún fichero.

Ejemplo:
    python scripts/validate_output.py baleares.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "item.schema.json"


def validate_file(path: Path, validator: jsonschema.Draft202012Validator) -> tuple[int, int]:
    """Devuelve (sobres, fallos) del fichero."""
    envelopes = failures = 0
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            envelopes += 1
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError as exc:
                failures += 1
                print(f"{path}:{number}: no es JSON: {exc}", file=sys.stderr)
                continue
            errors = list(validator.iter_errors(envelope))
            if errors:
                failures += 1
                first = errors[0]
                where = "/".join(str(p) for p in first.absolute_path) or "(raíz)"
                print(f"{path}:{number}: no valida ({where}): {first.message[:200]}", file=sys.stderr)
    return envelopes, failures


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arguments.add_argument("files", metavar="JSONL", nargs="+", help="ficheros JSONL a validar")
    args = arguments.parse_args()

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    total_failures = 0
    for name in args.files:
        path = Path(name)
        try:
            envelopes, failures = validate_file(path, validator)
        except OSError as exc:
            print(f"{path}: no se pudo leer: {exc}", file=sys.stderr)
            return 2
        total_failures += failures
        print(f"{path}: {envelopes} sobre(s), {failures} fallo(s)", file=sys.stderr)
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())
