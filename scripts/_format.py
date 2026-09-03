"""Utilidades compartidas por los scripts de prueba de la carpeta scripts/.

Estos scripts son CONSUMIDORES del recolector: lanzan `boe-subastas`, leen
los sobres JSONL de su stdout y los pintan para humanos. Se mantiene la misma
disciplina que en el recolector: stdout lleva solo el producto del script (la
vista legible), y stderr lleva los diagnósticos propios más los logs del
recolector, que se dejan pasar sin tocar.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Callable, TextIO

# Color (solo si stdout es una terminal)

def _enable_ansi() -> bool:
    """Activa las secuencias ANSI en la consola clásica de Windows."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))  # VT
    except (AttributeError, OSError):
        return False


_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR") and _enable_ansi()


def _style(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(text: str) -> str:
    return _style(text, "1")


def dim(text: str) -> str:
    return _style(text, "2")


def green(text: str) -> str:
    return _style(text, "32")


def yellow(text: str) -> str:
    return _style(text, "33")


def cyan(text: str) -> str:
    return _style(text, "36")


# Formato de valores

def format_amount(value: object) -> str:
    """1234567.89 -> «1.234.567,89 €»; literales de la fuente tal cual."""
    if value is None:
        return dim("—")
    if isinstance(value, (int, float)):
        flat = f"{value:,.2f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
        return green(f"{flat} €")
    return str(value)


def format_date(iso: str | None) -> str:
    """«2026-09-14T18:00:00+02:00» -> «14/09/2026 18:00»."""
    if not iso:
        return dim("—")
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def shorten(text: str | None, width: int = 100) -> str:
    if not text:
        return ""
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[: width - 1] + "…"


def row(label: str, value: object, indent: int = 4) -> None:
    """Imprime una fila etiqueta/valor; omite las filas sin dato."""
    if value is None or value == "" or value == []:
        return
    print(" " * indent + dim(f"{label:<20}") + f" {value}")


# Vistas de un sobre

def _entity(person: dict) -> str:
    parts = [person.get("nombre") or "—"]
    if person.get("nif"):
        parts.append(f"({person['nif']})")
    place = " ".join(
        p for p in (person.get("direccion"), person.get("localidad"),
                    person.get("provincia"), person.get("pais")) if p
    )
    if place:
        parts.append("· " + place)
    return " ".join(parts)


def render_detail(envelope: dict) -> None:
    """Vista completa y legible de un sobre (para `view_auction.py`)."""
    meta, data = envelope["meta"], envelope["data"]
    auction = data.get("subasta") or {}
    lot = data.get("lote")
    bids = data.get("pujas") or {}

    header = meta.get("external_id", "?")
    if lot:
        header += f" · Lote {lot.get('numero')} de {auction.get('lotes')}"
    if auction.get("estado"):
        header += f" · {auction['estado']}"
    line = "─" * min(len(header) + 4, 78)
    print(line)
    print(bold(cyan(f"  {header}")))
    print(line)
    if data.get("descripcion"):
        print(f"  {shorten(data['descripcion'], 200)}")

    print(bold("  Subasta"))
    row("Tipo", auction.get("tipo"))
    row("Expediente", auction.get("expediente"))
    row("Inicio", format_date(auction.get("fecha_inicio")))
    row("Conclusión", format_date(auction.get("fecha_conclusion")))
    row("Cantidad reclamada", format_amount(auction.get("cantidad_reclamada")))
    row("Anuncio BOE", auction.get("anuncio_boe"))
    if auction.get("aviso_estado"):
        row("Aviso", yellow(shorten(auction["aviso_estado"], 120)))

    economics = lot if lot else auction
    print(bold(f"  Lote {lot['numero']}" if lot else "  Condiciones"))
    row("Valor subasta", format_amount(economics.get("valor_subasta")))
    row("Tasación", format_amount(economics.get("tasacion")))
    row("Puja mínima", format_amount(economics.get("puja_minima")))
    row("Tramos entre pujas", format_amount(economics.get("tramos_pujas")))
    row("Depósito", format_amount(economics.get("importe_deposito")))

    print(bold("  Pujas"))
    if bids.get("puja_mas_alta") is not None:
        row("Puja más alta", format_amount(bids["puja_mas_alta"]))
    else:
        row("Puja más alta", dim(bids.get("mensaje") or "—"))
    row("Certificado cierre", bids.get("certificado_cierre"))

    for asset in data.get("bienes") or []:
        title = f"  Bien {asset.get('numero')} · {asset.get('tipo') or ''}"
        if asset.get("subtipo"):
            title += f" ({asset['subtipo']})"
        print(bold(title))
        if asset.get("descripcion"):
            print(f"    {shorten(asset['descripcion'], 300)}")
        row("Dirección", asset.get("direccion"))
        locality = " ".join(
            p for p in (asset.get("codigo_postal"), asset.get("localidad")) if p
        )
        if asset.get("provincia"):
            locality = f"{locality} ({asset['provincia']})" if locality else asset["provincia"]
        row("Localidad", locality)
        row("Ref. catastral", asset.get("referencia_catastral"))
        row("IDUFIR", asset.get("idufir"))
        row("Título jurídico", asset.get("titulo_juridico"))
        row("Vivienda habitual", asset.get("vivienda_habitual"))
        row("Situación posesoria", asset.get("situacion_posesoria"))
        row("Cargas", format_amount(asset.get("cargas")) if asset.get("cargas") is not None else None)
        row("Visitable", asset.get("visitable"))
        for label, value in (asset.get("otros") or {}).items():
            row(label, value)
        if asset.get("imagenes"):
            row("Imágenes", f"{len(asset['imagenes'])} foto(s)")

    authority = auction.get("autoridad_gestora") or {}
    if authority.get("descripcion"):
        contact = " · ".join(
            p for p in (authority.get("telefono"), authority.get("correo_electronico")) if p
        )
        print(bold("  Autoridad gestora"))
        row("Órgano", authority["descripcion"])
        row("Contacto", contact)

    if auction.get("acreedores"):
        print(bold("  Acreedores"))
        for person in auction["acreedores"]:
            print(f"    · {_entity(person)}")
    if auction.get("administradores_concursales"):
        print(bold("  Administración concursal"))
        for person in auction["administradores_concursales"]:
            print(f"    · {_entity(person)}")
    if auction.get("aviso_relacionados"):
        row("Aviso", yellow(auction["aviso_relacionados"]), indent=2)
    for heading, entities in (auction.get("relacionados_otros") or {}).items():
        print(bold(f"  {heading}"))
        for person in entities:
            print(f"    · {_entity(person)}")

    documents = auction.get("documentos") or []
    if documents:
        print(bold(f"  Documentos ({len(documents)})"))
        for doc in documents:
            print(f"    · {shorten(doc.get('nombre'), 70)}")
            print(dim(f"      {doc.get('url')}"))

    row("Ficha", meta.get("url"), indent=2)
    print()


def render_summary(envelope: dict) -> None:
    """Vista compacta de dos líneas por sobre (para `search_auctions.py`)."""
    meta, data = envelope["meta"], envelope["data"]
    auction = data.get("subasta") or {}
    lot = data.get("lote")
    bids = data.get("pujas") or {}
    economics = lot if lot else auction

    if bids.get("puja_mas_alta") is not None:
        bid = "puja " + format_amount(bids["puja_mas_alta"])
    else:
        bid = dim(shorten(bids.get("mensaje") or "pujas —", 45))

    identifier = meta.get("external_id") or "?"
    status = auction.get("estado") or "—"
    parts = [
        bold(cyan(f"{identifier:<32}")),
        f"{shorten(status, 40):<40}",
        "concluye " + format_date(auction.get("fecha_conclusion")),
        "valor " + format_amount(economics.get("valor_subasta")),
        bid,
    ]
    print("  ".join(parts))
    description = shorten(data.get("descripcion"), 110)
    if description:
        print(dim(f"    {description}"))


# Ejecución del recolector

def collector_command() -> list[str]:
    executable = shutil.which("boe-subastas")
    if executable:
        return [executable]
    return [sys.executable, "-m", "boe_subastas.cli"]


def paint_envelope(envelope: object, view: Callable[[dict], None], source_label: str) -> None:
    """Pinta un sobre tolerando líneas malformadas (JSON válido no-objeto,
    claves ausentes): avisa por stderr y deja seguir con el resto. Una tubería
    de salida cerrada (BrokenPipeError) sí se propaga: es fin de ejecución."""
    if not isinstance(envelope, dict):
        print(f"aviso: {source_label} no es un sobre (se ignora): {envelope!r}"[:120],
              file=sys.stderr)
        return
    try:
        view(envelope)
    except BrokenPipeError:
        raise
    except (KeyError, TypeError, AttributeError) as exc:
        print(f"aviso: {source_label} con forma inesperada (se ignora): {exc!r}",
              file=sys.stderr)


def consume_collector(
    arguments: list[str],
    view: Callable[[dict], None],
    save_stream: TextIO | None = None,
) -> int:
    """Lanza el recolector, pinta cada sobre según llega y devuelve su código.

    stderr del recolector se hereda (los logs siguen viéndose en la terminal,
    separados de la vista); si `save_stream` está abierto, cada línea JSONL cruda
    se conserva además tal cual. El hijo queda siempre cosechado: en cualquier
    salida anticipada (Ctrl+C, tubería cerrada, error del render) se le
    termina en vez de dejarlo haciendo peticiones en segundo plano.
    """
    command = collector_command() + arguments
    print("$ " + " ".join(command), file=sys.stderr)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, text=True, encoding="utf-8"
    )
    assert process.stdout is not None
    interrupted = False
    completed = False
    try:
        for line in process.stdout:
            if not line.strip():
                continue
            if save_stream is not None:
                save_stream.write(line)
                save_stream.flush()
            try:
                envelope = json.loads(line)
            except json.JSONDecodeError:
                print(f"aviso: línea no JSON ignorada: {line[:80]!r}",
                      file=sys.stderr)
                continue
            paint_envelope(envelope, view, "sobre recibido")
        completed = True
    except KeyboardInterrupt:
        interrupted = True
        print("interrumpido; cerrando el recolector…", file=sys.stderr)
    finally:
        process.stdout.close()
        if not completed and process.poll() is None:
            process.terminate()
        try:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except KeyboardInterrupt:
            process.kill()
            process.wait()
            interrupted = True

    if interrupted:
        return 130
    code = process.returncode
    if code < 0:
        # Muerte por señal N: convención de shell 128+N.
        code = 128 - code
    if code != 0:
        print(f"boe-subastas terminó con código de salida {code}",
              file=sys.stderr)
    return code


def status_footer(status: str, auctions: int, envelopes: int) -> None:
    """Línea de recuento que cierra un bloque de estado en el listado.

    Cuenta subastas, no sobres: una subasta con varios lotes cuenta una vez.
    """
    detail = f"{auctions} subasta(s)"
    if envelopes != auctions:
        detail += f" en {envelopes} sobre(s)"
    print(bold(f"  ── {status}: {detail} ──"))
    print()
