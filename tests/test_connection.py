"""Conexión: reintentos, clasificación de errores HTTP y control de sesión."""

import pytest
import requests

from boe_subastas.client import connection as conn_module
from boe_subastas.client.connection import Connection
from boe_subastas.errors import AuthenticationError, SourceUnavailableError


class FakeResponse:
    def __init__(self, status_code=200, text="ok", url="https://subastas.boe.es/x.php"):
        self.status_code, self.text, self.url = status_code, text, url


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.headers = {}
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(conn_module.time, "sleep", lambda seconds: None)


def test_identifies_itself_and_returns_body():
    session = FakeSession([FakeResponse(text="<html>")])
    connection = Connection(session=session)
    assert connection.get("x.php") == "<html>"
    assert session.headers["User-Agent"].startswith("boe-subastas/")


def test_retries_temporary_server_errors():
    session = FakeSession([FakeResponse(503), requests.ConnectionError("caída"), FakeResponse(text="ok")])
    assert Connection(session=session).get("x.php") == "ok"
    assert session.calls == 3


def test_does_not_retry_definitive_errors():
    session = FakeSession([FakeResponse(404)])
    with pytest.raises(SourceUnavailableError):
        Connection(session=session).get("x.php")
    assert session.calls == 1


def test_gives_up_after_all_attempts():
    session = FakeSession([requests.ConnectionError("x")] * conn_module.ATTEMPTS)
    with pytest.raises(SourceUnavailableError):
        Connection(session=session).get("x.php")
    assert session.calls == conn_module.ATTEMPTS


def test_authenticated_session_detects_silent_redirect_to_public_zone():
    public = FakeResponse(url="https://subastas.boe.es/detalleSubasta.php?idSub=X")
    with pytest.raises(AuthenticationError):
        Connection(session=FakeSession([public]), authenticated=True).get("detalleSubasta.php")
    private = FakeResponse(url="https://subastas.boe.es/reg/detalleSubasta.php?idSub=X", text="<html>")
    assert Connection(session=FakeSession([private]), authenticated=True).get("detalleSubasta.php") == "<html>"
