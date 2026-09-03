"""Punto de entrada: subcomandos, canales y códigos de salida (sin red)."""

import json
import logging

import pytest

from boe_subastas import cli
from conftest import BROKEN_ASSETS_HTML, FakeConnection


def run(monkeypatch, capsys, caplog, argv, connection=None):
    """Ejecuta el CLI sin red y devuelve (código, sobres de stdout, diagnósticos).

    Los registros de `logging` los captura pytest (`caplog`), no la captura de
    stderr; ambos canales se devuelven juntos como «diagnósticos».
    """
    caplog.set_level(logging.INFO)  # el CLI informa del progreso en INFO
    monkeypatch.setattr(cli, "_connection", lambda args: connection or FakeConnection())
    code = cli.main(argv)
    out, err = capsys.readouterr()
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    return code, lines, err + caplog.text


def test_info_is_one_json_line_without_network(monkeypatch, capsys, caplog):
    code, lines, _ = run(monkeypatch, capsys, caplog, ["info"])
    assert code == 0 and len(lines) == 1
    info = lines[0]
    assert {"source", "scraper_version", "schema_version", "filtros_search"} <= info.keys()
    assert [f["opcion"] for f in info["filtros_search"]][:3] == ["--province", "--origin", "--status"]


def test_fetch_emits_valid_envelopes_and_lot_ids(monkeypatch, capsys, caplog, validator):
    code, lines, err = run(monkeypatch, capsys, caplog, ["fetch", "SUB-JA-2026-265000", "SUB-JA-2026-265003/L2"])
    assert code == 0
    assert [e["meta"]["external_id"] for e in lines] == ["SUB-JA-2026-265000/L1", "SUB-JA-2026-265000/L2", "SUB-JA-2026-265003/L2"]
    assert lines[0]["data"]["subasta"]["estado"] == "Celebrándose"  # del listado
    for envelope in lines:
        assert not list(validator.iter_errors(envelope))
    assert "Emitidos 3 sobres" in err


def test_stdout_carries_only_data(monkeypatch, capsys, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(cli, "_connection", lambda args: FakeConnection())
    cli.main(["fetch", "SUB-RC-2026-07003001815"])
    out, _ = capsys.readouterr()
    assert all(line.startswith("{") for line in out.splitlines() if line)
    assert any(record.levelname == "INFO" for record in caplog.records)
    assert "INFO" not in out and "Recolectando" not in out


def test_search_continues_past_missing_auctions_and_respects_limit(monkeypatch, capsys, caplog):
    code, lines, err = run(monkeypatch, capsys, caplog, ["search", "--province", "Illes Balears"])
    # El listado tiene 9 subastas; solo 4 tienen captura completa: 2 + 1 + 3 + 1
    # sobres. Las otras 5 no existen para la conexión falsa y se saltan.
    assert code == 0 and len(lines) == 7
    assert "ya no está disponible" in err  # subastas del listado sin ficha
    code, lines, _ = run(monkeypatch, capsys, caplog, ["search", "--province", "07", "--limit", "3"])
    assert code == 0 and len(lines) == 3


def test_since_filters_locally_by_start_date(monkeypatch, capsys, caplog):
    code, lines, _ = run(monkeypatch, capsys, caplog, ["fetch", "SUB-JA-2026-265000", "--since", "2026-09-01"])
    assert code == 0 and lines == []  # empezó el 25-08-2026


def test_output_file_receives_the_data(monkeypatch, capsys, caplog, tmp_path):
    target = tmp_path / "salida.jsonl"
    code, lines, _ = run(monkeypatch, capsys, caplog, ["fetch", "SUB-JC-2026-264427", "-o", str(target)])
    assert code == 0 and lines == []
    assert json.loads(target.read_text(encoding="utf-8"))["meta"]["external_id"] == "SUB-JC-2026-264427"


def test_unknown_id_in_fetch_exits_with_1(monkeypatch, capsys, caplog):
    code, lines, err = run(monkeypatch, capsys, caplog, ["fetch", "SUB-XX-9999-000000", "SUB-RC-2026-07003001815"])
    assert code == 1 and len(lines) == 1
    assert "no existe en la fuente" in err


def test_structure_change_exits_with_4_but_keeps_good_items(monkeypatch, capsys, caplog):
    broken = FakeConnection(broken={("SUB-AT-2026-26R0886001200", 3): BROKEN_ASSETS_HTML})
    code, lines, err = run(monkeypatch, capsys, caplog, ["fetch", "SUB-AT-2026-26R0886001200", "SUB-RC-2026-07003001815"], broken)
    assert code == 4
    assert [e["meta"]["external_id"] for e in lines] == ["SUB-RC-2026-07003001815"]
    assert "No se pudo interpretar" in err


@pytest.mark.parametrize("argv", [["search", "--since", "2026-02-31"], ["search", "--status", "XX"], ["search", "--provincia", "07"], ["fetch"]])
def test_usage_errors_exit_with_2(argv):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 2


def test_unwritable_output_exits_with_2(monkeypatch, capsys, caplog):
    code, _, err = run(monkeypatch, capsys, caplog, ["info", "-o", "/ruta/inexistente/salida.jsonl"])
    assert code == 2 and "fichero de salida" in err


def test_split_lot_and_since_filter_helpers():
    assert cli._split_lot("SUB-JA-2026-265000/L2") == ("SUB-JA-2026-265000", 2)
    assert cli._split_lot("SUB-JA-2026-265000") == ("SUB-JA-2026-265000", None)
    assert cli._passes_since({"subasta": {"fecha_inicio": "2026-08-25T18:00:00+02:00"}}, "2026-08-25")
    assert not cli._passes_since({"subasta": {"fecha_inicio": "2026-08-25T18:00:00+02:00"}}, "2026-08-26")
    assert cli._passes_since({"subasta": {"fecha_inicio": None}}, "2026-08-26")
