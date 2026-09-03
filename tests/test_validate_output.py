"""Validador de ficheros JSONL (scripts/validate_output.py)."""

import json
import subprocess
import sys

from boe_subastas import models
from boe_subastas.client.collector import collect
from conftest import REPO, SCRIPTS, FakeConnection


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
