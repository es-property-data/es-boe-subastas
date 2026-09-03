"""Conexión HTTP con el Portal de Subastas: ritmo, reintentos y sesión.

Único punto del paquete que habla con el portal (Gateway). El ritmo de
peticiones y la identificación no son configurables: son comportamiento fijo
del recolector.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

from boe_subastas.errors import AuthenticationError, SourceUnavailableError
from boe_subastas.models import BASE_URL, USER_AGENT

log = logging.getLogger(__name__)

# Comportamiento fijo del recolector.
REQUEST_INTERVAL_SECONDS = 1.5
TIMEOUT_SECONDS = 30
ATTEMPTS = 3
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}

_LOGIN_PAGE_MARKER = "Acceso de usuarios registrados"


class Connection:
    """Conexión con el portal: ritmo fijo, reintentos y control de sesión.

    Con `authenticated=True` opera en la zona `/reg/` (sesión de usuario
    registrado) y falla en alto si el portal redirige a la zona pública.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        authenticated: bool = False,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.authenticated = authenticated
        self._last_request = 0.0

    @property
    def _base(self) -> str:
        return BASE_URL + "reg/" if self.authenticated else BASE_URL

    def _wait_interval(self) -> None:
        remaining = self._last_request + REQUEST_INTERVAL_SECONDS - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    def get(self, path: str, params: dict | None = None) -> str:
        url = self._base + path
        last_error: Exception | None = None
        for attempt in range(1, ATTEMPTS + 1):
            self._wait_interval()
            try:
                response = self.session.get(
                    url, params=params, timeout=TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                last_error = exc
                log.warning("Fallo de red en %s (intento %d/%d): %s",
                            path, attempt, ATTEMPTS, exc)
            else:
                self._last_request = time.monotonic()
                if response.status_code == 200:
                    return self._check_session(response)
                last_error = SourceUnavailableError(
                    f"La fuente respondió HTTP {response.status_code} en {path}."
                )
                if response.status_code not in RETRYABLE_HTTP_STATUSES:
                    raise last_error
                log.warning("HTTP %d en %s (intento %d/%d)",
                            response.status_code, path, attempt, ATTEMPTS)
            finally:
                self._last_request = time.monotonic()
            if attempt < ATTEMPTS:
                time.sleep(2 * attempt)
        raise SourceUnavailableError(
            f"La fuente no respondió tras {ATTEMPTS} intentos en {path}: "
            f"{last_error}"
        )

    def _check_session(self, response: requests.Response) -> str:
        if not self.authenticated:
            return response.text
        # Con la sesión caducada el portal no da error: redirige en silencio
        # desde /reg/ a la zona pública y serviría datos anónimos (sin pujas).
        final_path = urlparse(response.url).path
        if (
            not final_path.startswith("/reg/")
            or "acceso.php" in response.url
            or _LOGIN_PAGE_MARKER in response.text
        ):
            raise AuthenticationError(
                "La sesión autenticada ha caducado o no es válida (el portal "
                "redirigió a la zona pública); vuelva a iniciar sesión (--auth) "
                "o elimine el fichero de sesión."
            )
        return response.text
