"""Punto de entrada del recolector.

stdout es solo datos (una línea JSON por sobre); todo lo demás —logs,
progreso, avisos, errores— en stderr. Las excepciones del paquete se
traducen aquí a códigos de salida:

    0  ejecución correcta
    1  error inesperado
    2  uso incorrecto (opción/argumento inválido, salida no escribible,
       consulta rechazada por demasiado amplia)
    3  fuente inaccesible (red, servidor, bloqueo, autenticación)
    4  estructura cambiada: al menos un ítem no se pudo interpretar
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date
from typing import TextIO

import requests

from boe_subastas import auth, models
from boe_subastas.client.collector import collect
from boe_subastas.client.connection import REQUEST_INTERVAL_SECONDS, Connection
from boe_subastas.client.search import locate, search
from boe_subastas.errors import (
    AuthenticationError,
    BoeSubastasError,
    ItemNotFoundError,
    QueryError,
    SourceUnavailableError,
    StructureError,
)
from boe_subastas.version import SCHEMA_VERSION, SCRAPER_VERSION, SOURCE

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_SOURCE = 3
EXIT_STRUCTURE = 4

_RE_SINCE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_RE_LOT_ID = re.compile(r"^(?P<auction>.+)/L(?P<lot>\d+)$")

# Fallos de descarga consecutivos que se toleran antes de dar la fuente por
# inaccesible y abortar (un ítem purgado del portal no debe tirar el crawl).
_MAX_CONSECUTIVE_SOURCE_FAILURES = 3


def _split_lot(requested_id: str) -> tuple[str, int | None]:
    """Desdobla un external_id de lote («SUB-…/L2») en (id_subasta, lote)."""
    m = _RE_LOT_ID.match(requested_id)
    if m:
        return m.group("auction"), int(m.group("lot"))
    return requested_id, None


# Argumentos

def _province_type(value: str) -> str:
    try:
        return models.province_code(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _since_type(value: str) -> str:
    m = _RE_SINCE.match(value.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida: {value!r}. Use ISO 8601 (AAAA-MM-DD)."
        )
    try:
        date.fromisoformat(m.group(1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Fecha de calendario inválida: {m.group(1)} ({exc})."
        ) from exc
    return m.group(1)


def _limit_type(value: str) -> int:
    try:
        limit_value = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Límite inválido: {value!r}") from exc
    if limit_value < 1:
        raise argparse.ArgumentTypeError("El límite debe ser mayor que cero.")
    return limit_value


def build_argument_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-o",
        "--output",
        metavar="FICHERO",
        help="escribe la salida de datos en FICHERO (truncándolo) en lugar de "
        "stdout; no afecta a stderr",
    )

    capture = argparse.ArgumentParser(add_help=False)
    capture.add_argument(
        "--since",
        metavar="FECHA",
        type=_since_type,
        help="limita a subastas con fecha de inicio (publicación en el portal) "
        "desde FECHA (ISO 8601, se usa solo la parte de fecha). La fuente no "
        "expone fecha de modificación, así que los cambios posteriores en "
        "subastas iniciadas antes de FECHA quedan fuera",
    )
    capture.add_argument(
        "--limit",
        metavar="N",
        type=_limit_type,
        help="corta la emisión al alcanzar N sobres",
    )
    capture.add_argument(
        "--auth",
        action="store_true",
        help="usa una sesión autenticada del portal (necesaria para ver el "
        "importe de las pujas de subastas en curso); requiere "
        "BOE_SUBASTAS_EMAIL y BOE_SUBASTAS_PASSWORD o una sesión guardada",
    )

    root = argparse.ArgumentParser(
        prog="boe-subastas",
        description="Recolector del Portal de Subastas del BOE "
        "(https://subastas.boe.es). Emite una línea JSON por unidad "
        "subastada (subasta o lote), conforme a schemas/item.schema.json.",
    )
    root.add_argument("--version", action="version", version=SCRAPER_VERSION)

    subcommands = root.add_subparsers(dest="subcommand", required=True)

    search_command = subcommands.add_parser(
        "search",
        parents=[common, capture],
        help="descubre subastas según los filtros y emite un sobre por unidad",
        description="Busca en el portal y emite un sobre por cada unidad "
        "subastada encontrada (la subasta entera, o cada lote si los hay).",
        epilog='Ejemplo: boe-subastas search --province "Illes Balears" '
        "(todos los estados; si la fuente rechaza la consulta por amplia, se "
        "divide automáticamente en subconsultas). Añada --status EJ para solo "
        "las que se están celebrando.",
    )
    search_command.add_argument(
        "--province",
        metavar="PROVINCIA",
        type=_province_type,
        help="provincia del bien: código INE o nombre oficial "
        "(p. ej. 07 o 'Illes Balears')",
    )
    search_command.add_argument(
        "--origin",
        type=str.upper,
        choices=sorted(models.ORIGINS),
        help="origen de la subasta: "
        + ", ".join(f"{c}={n}" for c, n in models.ORIGINS.items()),
    )
    search_command.add_argument(
        "--status",
        type=str.upper,
        choices=sorted(models.STATUSES),
        help="estado de la subasta: "
        + ", ".join(f"{c}={n}" for c, n in models.STATUSES.items()),
    )
    search_command.add_argument(
        "--asset-type",
        type=str.upper,
        choices=sorted(models.ASSET_TYPES),
        help="tipo de bien: "
        + ", ".join(f"{c}={n}" for c, n in models.ASSET_TYPES.items()),
    )
    search_command.add_argument("--locality", metavar="LOCALIDAD", help="localidad del bien (texto libre)")
    search_command.add_argument(
        "--postal-code", metavar="CODIGO_POSTAL", help="código postal del bien (texto libre)"
    )
    search_command.add_argument("--address", metavar="DIRECCION", help="dirección del bien (texto libre)")
    search_command.add_argument(
        "--authority", metavar="AUTORIDAD", help="autoridad gestora (texto libre)"
    )
    search_command.set_defaults(func=cmd_search)

    fetch_command = subcommands.add_parser(
        "fetch",
        parents=[common, capture],
        help="recupera subastas concretas por su identificador",
        description="Descarga la ficha completa de cada identificador dado y "
        "emite sus sobres (uno por lote si la subasta tiene lotes).",
        epilog="Ejemplo: boe-subastas fetch SUB-JA-2026-265000",
    )
    fetch_command.add_argument(
        "ids",
        metavar="ID",
        nargs="+",
        help="identificadores de subasta o de lote, tal y como los emite el "
        "recolector (p. ej. SUB-JA-2026-265000 o SUB-JA-2026-265000/L2)",
    )
    fetch_command.set_defaults(func=cmd_fetch)

    info_command = subcommands.add_parser(
        "info",
        parents=[common],
        help="describe el recolector (sin acceder a la red)",
        description="Emite una línea JSON con las capacidades del recolector.",
    )
    info_command.set_defaults(func=cmd_info)

    return root


# Emisión

def _emit(output: TextIO, obj: dict) -> None:
    output.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    output.write("\n")
    output.flush()


def _passes_since(data: dict, since: str | None) -> bool:
    if not since:
        return True
    start_date = data["subasta"]["fecha_inicio"]
    if not start_date:
        return True
    return start_date[:10] >= since


def _connection(args: argparse.Namespace) -> Connection:
    session = requests.Session()
    if getattr(args, "auth", False):
        auth.prepare_authenticated_session(session)
    return Connection(session=session, authenticated=getattr(args, "auth", False))


# Subcomandos

def cmd_search(args: argparse.Namespace, output: TextIO) -> int:
    filters: dict[str, str] = {}
    if args.province:
        filters["province"] = args.province
    if args.origin:
        filters["origin"] = args.origin
    if args.status:
        filters["status"] = args.status
    if args.asset_type:
        filters["asset_type"] = args.asset_type
    if args.locality:
        filters["locality"] = args.locality
    if args.postal_code:
        filters["postal_code"] = args.postal_code
    if args.address:
        filters["address"] = args.address
    if args.authority:
        filters["authority"] = args.authority
    if args.since:
        filters["start_date_from"] = args.since

    connection = _connection(args)
    emitted = 0
    structure_failures = 0
    consecutive_source_failures = 0

    for item in search(connection, filters):
        log.info("Recolectando %s…", item["identificador"])
        try:
            for external_id, url, data in collect(
                connection,
                item["identificador"],
                status=item["estado"],
                case_number=item["expediente"],
            ):
                if not _passes_since(data, args.since):
                    continue
                _emit(output, models.envelope(external_id, url, data))
                emitted += 1
                if args.limit and emitted >= args.limit:
                    break
            consecutive_source_failures = 0
        except StructureError as exc:
            structure_failures += 1
            consecutive_source_failures = 0
            log.error(
                "No se pudo interpretar la subasta %s: %s",
                item["identificador"],
                exc,
                exc_info=True,
            )
        except ItemNotFoundError as exc:
            # Carrera normal en una fuente viva (subasta retirada entre el
            # listado y la ficha): no es un cambio de estructura.
            consecutive_source_failures = 0
            log.warning(
                "La subasta %s ya no está disponible en la fuente: %s",
                item["identificador"],
                exc,
            )
        except SourceUnavailableError as exc:
            consecutive_source_failures += 1
            if consecutive_source_failures >= _MAX_CONSECUTIVE_SOURCE_FAILURES:
                raise
            log.error(
                "No se pudo descargar la subasta %s; se continúa con la "
                "siguiente: %s",
                item["identificador"],
                exc,
            )
        # La comprobación va al final del cuerpo para no avanzar el listado
        # (y disparar la petición de la página siguiente) tras el último sobre.
        if args.limit and emitted >= args.limit:
            break

    log.info("Emitidos %d sobres (%d subastas fallidas).", emitted, structure_failures)
    return EXIT_STRUCTURE if structure_failures else EXIT_OK


def cmd_fetch(args: argparse.Namespace, output: TextIO) -> int:
    connection = _connection(args)
    emitted = 0
    structure_failures = 0
    not_found = 0

    for requested_id in args.ids:
        auction_id, lot = _split_lot(requested_id)
        try:
            item = locate(connection, auction_id)
            if item is None:
                log.warning(
                    "El buscador no lista %s; se descarga la ficha directamente.",
                    auction_id,
                )
            for external_id, url, data in collect(
                connection,
                auction_id,
                status=item["estado"] if item else None,
                case_number=item["expediente"] if item else None,
                only_lot=lot,
            ):
                if not _passes_since(data, args.since):
                    continue
                _emit(output, models.envelope(external_id, url, data))
                emitted += 1
                if args.limit and emitted >= args.limit:
                    break
        except ItemNotFoundError as exc:
            not_found += 1
            log.error("El ítem %s no existe en la fuente: %s", requested_id, exc)
        except StructureError as exc:
            structure_failures += 1
            log.error(
                "No se pudo interpretar la subasta %s: %s",
                auction_id,
                exc,
                exc_info=True,
            )
        if args.limit and emitted >= args.limit:
            break

    log.info("Emitidos %d sobres.", emitted)
    if structure_failures:
        return EXIT_STRUCTURE
    if not_found:
        return EXIT_ERROR
    return EXIT_OK


def cmd_info(args: argparse.Namespace, output: TextIO) -> int:
    def filter_spec(option: str, field: str | None, description: str, values=None):
        return {
            "opcion": option,
            "campo_fuente": field,
            "descripcion": description,
            "valores": values,
        }

    _emit(
        output,
        {
            "source": SOURCE,
            "scraper_version": SCRAPER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "descripcion": "Recolector del Portal de Subastas de la Agencia "
            "Estatal Boletín Oficial del Estado (https://subastas.boe.es). "
            "Emite un sobre por unidad subastada: la subasta entera o cada "
            "lote (external_id con sufijo /L<n>).",
            "subcomandos": ["search", "fetch", "info"],
            "filtros_search": [
                filter_spec("--province", "BIEN.COD_PROVINCIA",
                       "código INE o nombre oficial de la provincia",
                       models.PROVINCES),
                filter_spec("--origin", "SUBASTA.ORIGEN",
                       "origen de la subasta", models.ORIGINS),
                filter_spec("--status", "SUBASTA.ESTADO.CODIGO",
                       "estado de la subasta", models.STATUSES),
                filter_spec("--asset-type", "BIEN.TIPO",
                       "tipo de bien", models.ASSET_TYPES),
                filter_spec("--locality", "BIEN.LOCALIDAD",
                       "localidad del bien (texto libre)"),
                filter_spec("--postal-code", "BIEN.CODPOSTAL",
                       "código postal del bien (texto libre)"),
                filter_spec("--address", "BIEN.DIRECCION",
                       "dirección del bien (texto libre)"),
                filter_spec("--authority", "SUBASTA.AUTORIDAD",
                       "autoridad gestora (texto libre)"),
                filter_spec("--since", "SUBASTA.FECHA_INICIO",
                       "subastas con fecha de inicio (publicación en el "
                       "portal) desde la fecha dada (ISO 8601); la fuente no "
                       "expone fecha de modificación"),
            ],
            "autenticacion": {
                "opcion": "--auth",
                "descripcion": "sesión de usuario registrado del portal; "
                "necesaria para ver el importe de las pujas de subastas en "
                "curso. Usa BOE_SUBASTAS_EMAIL/BOE_SUBASTAS_PASSWORD y pide "
                "por terminal el código de verificación enviado por correo.",
            },
            "ritmo_peticiones_segundos": REQUEST_INTERVAL_SECONDS,
            "user_agent": models.USER_AGENT,
        },
    )
    return EXIT_OK


# Entrada

def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    _load_environment()
    args = build_argument_parser().parse_args(argv)

    output: TextIO = sys.stdout
    if args.output:
        try:
            output = open(args.output, "w", encoding="utf-8")
        except OSError as exc:
            log.error("No se puede escribir el fichero de salida: %s", exc)
            return EXIT_USAGE

    try:
        return args.func(args, output)
    except QueryError as exc:
        log.error("%s", exc)
        return EXIT_USAGE
    except (SourceUnavailableError, AuthenticationError) as exc:
        log.error("%s", exc, exc_info=True)
        return EXIT_SOURCE
    except StructureError as exc:
        log.error("%s", exc, exc_info=True)
        return EXIT_STRUCTURE
    except BoeSubastasError as exc:
        log.error("%s", exc, exc_info=True)
        return EXIT_ERROR
    except KeyboardInterrupt:
        log.error("Interrumpido por el usuario.")
        return EXIT_ERROR
    except BrokenPipeError:
        # Terminación normal en tuberías («… | head»): salir en silencio,
        # evitando el segundo BrokenPipeError del flush de cierre.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK
    except OSError as exc:
        log.error("No se pudo escribir la salida de datos: %s", exc)
        return EXIT_USAGE
    except Exception:  # noqa: BLE001 — el CLI nunca deja escapar un traceback
        log.exception("Error inesperado.")
        return EXIT_ERROR
    finally:
        if output is not sys.stdout:
            try:
                output.close()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
