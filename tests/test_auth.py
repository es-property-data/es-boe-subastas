"""Inicio de sesión: lectura del código por consola y ruta de la sesión."""

from pathlib import Path

import pytest

from boe_subastas import auth
from boe_subastas.errors import AuthenticationError


def test_reads_code_from_console_device(monkeypatch, tmp_path):
    device = tmp_path / "console"
    device.write_text("123456\n", encoding="utf-8")
    monkeypatch.setattr(auth, "_CONSOLE_DEVICE", str(device))
    assert auth._read_line_from_console() == "123456"


def test_without_console_nor_tty_fails_loudly(monkeypatch):
    monkeypatch.setattr(auth, "_CONSOLE_DEVICE", str(Path("/ruta/inexistente/CON")))
    with pytest.raises(AuthenticationError):
        auth._read_line_from_console()  # stdin bajo pytest no es una terminal


def test_session_file_honours_explicit_variable(monkeypatch, tmp_path):
    monkeypatch.setenv("BOE_SUBASTAS_SESSION_FILE", str(tmp_path / "s.json"))
    assert auth.default_session_file() == tmp_path / "s.json"


def test_session_file_per_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("BOE_SUBASTAS_SESSION_FILE", raising=False)
    monkeypatch.setattr(auth.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert auth.default_session_file() == tmp_path / "boe-subastas" / "session.json"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert auth.default_session_file() == Path.home() / ".config" / "boe-subastas" / "session.json"
    monkeypatch.setattr(auth.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert auth.default_session_file() == tmp_path / "Roaming" / "boe-subastas" / "session.json"


def test_saved_cookies_are_private_and_round_trip(tmp_path):
    path = tmp_path / "session.json"
    cookies = [{"name": "SESSID", "value": "abc", "domain": ".subastas.boe.es", "path": "/"}]
    auth.save_cookies(path, cookies)
    assert auth.load_cookies(path) == cookies
    assert auth.load_cookies(tmp_path / "missing.json") is None
    if auth.sys.platform != "win32":
        assert oct(path.stat().st_mode & 0o777) == "0o600"
