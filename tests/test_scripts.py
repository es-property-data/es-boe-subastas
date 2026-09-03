"""Scripts de exploración manual: formato y lectura de JSONL guardados."""

import json
import subprocess
import sys

import _format
from boe_subastas import models
from boe_subastas.client.collector import collect
from conftest import REPO, SCRIPTS, FakeConnection


def test_format_helpers_without_color():
    assert _format.format_amount(1234567.89) == "1.234.567,89 €"
    assert _format.format_amount("Sin puja mínima") == "Sin puja mínima"
    assert _format.format_amount(None) == "—"
    assert _format.format_date("2026-09-14T18:00:00+02:00") == "14/09/2026 18:00"
    assert _format.format_date(None) == "—"
    assert _format.shorten("x" * 200, 10) == "x" * 9 + "…"


def test_view_auction_renders_a_saved_jsonl(tmp_path):
    envelopes = [models.envelope(eid, url, data) for eid, url, data in collect(FakeConnection(), "SUB-JA-2026-265000")]
    target = tmp_path / "sobres.jsonl"
    target.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in envelopes) + "null\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "view_auction.py"), "--file", str(target)],
        capture_output=True, text=True, cwd=REPO, encoding="utf-8",
    )
    assert result.returncode == 0
    assert "SUB-JA-2026-265000/L1 · Lote 1 de 2" in result.stdout
    assert "no es un sobre" in result.stderr  # la línea «null» se ignora con aviso


def test_validate_output_script(tmp_path):
    good = tmp_path / "good.jsonl"
    envelopes = [models.envelope(eid, url, data) for eid, url, data in collect(FakeConnection(), "SUB-RC-2026-07003001815")]
    good.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in envelopes), encoding="utf-8")
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"meta": {}, "data": {}}\n', encoding="utf-8")
    ok = subprocess.run([sys.executable, str(SCRIPTS / "validate_output.py"), str(good)], capture_output=True, text=True, cwd=REPO)
    assert ok.returncode == 0, ok.stderr
    ko = subprocess.run([sys.executable, str(SCRIPTS / "validate_output.py"), str(good), str(bad)], capture_output=True, text=True, cwd=REPO)
    assert ko.returncode == 1 and "bad.jsonl" in ko.stderr
