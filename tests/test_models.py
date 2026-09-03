"""Vocabulario del dominio, sobre y versiones."""

import re

import pytest

from boe_subastas import cli, models
from boe_subastas.version import SCHEMA_VERSION, SCRAPER_VERSION, SOURCE


@pytest.mark.parametrize("value", ["07", "7", "Illes Balears", "illes balears", "ILLES BALEARS"])
def test_province_code_accepts_codes_and_names(value):
    assert models.province_code(value) == "07"


def test_province_code_accepts_either_official_form():
    assert models.province_code("Alacant") == "03"
    assert models.province_code("Alicante") == "03"
    assert models.province_code("valencia") == "46"


@pytest.mark.parametrize("value", ["99", "Atlántida", ""])
def test_province_code_rejects_unknown(value):
    with pytest.raises(ValueError):
        models.province_code(value)


def test_envelope_meta_shape():
    envelope = models.envelope("SUB-X/L1", "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-X", {"k": 1})
    meta = envelope["meta"]
    assert meta["source"] == SOURCE == "boe_subastas"
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["scraper_version"] == SCRAPER_VERSION
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", meta["scraped_at"])
    assert envelope["data"] == {"k": 1}


def test_version_is_semver_and_matches_cli(capsys):
    assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", SCRAPER_VERSION)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == SCRAPER_VERSION
