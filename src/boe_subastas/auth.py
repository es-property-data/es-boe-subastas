"""Inicio de sesión en el Portal de Subastas del BOE.

El portal exige usuario registrado para ver el importe de las pujas de las
subastas en curso. El acceso con usuario y contraseña añade un segundo paso:
un código de verificación que el portal envía por correo electrónico. Ese
paso se resuelve con Selenium (navegador real) pidiendo el código por la
terminal de control (Linux, macOS y Windows), y las cookies resultantes se
trasladan a la sesión de `requests`, que es la que scrapea. Las cookies se persisten en disco para
reutilizar la sesión entre ejecuciones sin repetir el login.

Variables de entorno (véase .env.example):
- ``BOE_SUBASTAS_EMAIL`` / ``BOE_SUBASTAS_PASSWORD`` — credenciales.
- ``BOE_SUBASTAS_SESSION_FILE`` — ruta del fichero de cookies.
- ``BOE_SUBASTAS_HEADLESS`` — ``0`` para ver el navegador durante el login.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

from boe_subastas.errors import AuthenticationError
from boe_subastas.models import BASE_URL, USER_AGENT

log = logging.getLogger(__name__)

LOGIN_URL = BASE_URL + "id/login.php"
_SESSION_MARKERS = ("Conectado como", "desconectar.php")
# Solo se buscan dentro de elementos marcados como error: el propio formulario
# de login contiene texto estático con «quedará bloqueado», que daría falsos
# positivos si se escanease la página completa.
_ERROR_MARKERS = ("incorrect", "bloquead", "no es válido", "erróne")
_LOGIN_TIMEOUT_SECONDS = 300


def _config_dir() -> Path:
    """Carpeta de configuración del usuario según la plataforma.

    Windows: %APPDATA%\\boe-subastas. Linux/macOS: $XDG_CONFIG_HOME/boe-subastas
    o, en su defecto, ~/.config/boe-subastas.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / "boe-subastas"


def default_session_file() -> Path:
    configured = os.environ.get("BOE_SUBASTAS_SESSION_FILE")
    if configured:
        return Path(configured).expanduser()
    return _config_dir() / "session.json"


def save_cookies(path: Path, cookies: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Permisos restrictivos desde la creación: las cookies equivalen a la
    # sesión de la cuenta del portal. En Windows la protección la da la carpeta
    # del perfil de usuario (%APPDATA%).
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(cookies, handle, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def load_cookies(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def apply_cookies(session: requests.Session, cookies: list[dict]) -> None:
    for cookie in cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain") or "subastas.boe.es",
            path=cookie.get("path") or "/",
        )


def session_is_connected(session: requests.Session) -> bool:
    """Comprueba contra la fuente si la sesión de requests está autenticada."""
    try:
        response = session.get(
            BASE_URL + "reg/index.php",
            timeout=30,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        return False
    return any(marker in response.text for marker in _SESSION_MARKERS[:1])


# Dispositivo de la terminal de control.
_CONSOLE_DEVICE = "CON" if sys.platform == "win32" else "/dev/tty"


def _read_line_from_console() -> str:
    """Lee una línea de la terminal de control, nunca de una tubería.

    Si no hay dispositivo de consola disponible, acepta stdin solo cuando es
    una terminal interactiva; en una tubería falla en alto.
    """
    try:
        with open(_CONSOLE_DEVICE) as console:
            return console.readline().strip()
    except OSError as exc:
        if sys.stdin.isatty():
            return sys.stdin.readline().strip()
        raise AuthenticationError(
            "No hay terminal interactiva para introducir el código de "
            "verificación. Ejecute una vez el login de forma interactiva para "
            "guardar la sesión y reutilizarla después."
        ) from exc


def _ask_code_on_terminal() -> str:
    # Se lee de la terminal de control, nunca de stdin: en una tubería
    # («cat ids | xargs boe-subastas fetch --auth») stdin lleva datos ajenos
    # y enviarlos como código acabaría bloqueando la cuenta en el portal.
    print(
        "Introduce el código de verificación que el portal ha enviado a tu "
        "correo y pulsa Intro: ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    code = _read_line_from_console()
    if not code:
        raise AuthenticationError("No se introdujo ningún código de verificación.")
    return code


_CODE_FIELD_TYPES = {"", "text", "password", "number", "tel"}


def _code_field(driver):
    from selenium.webdriver.common.by import By

    for entry in driver.find_elements(By.TAG_NAME, "input"):
        # Un <input> sin atributo type también es de texto.
        input_type = (entry.get_attribute("type") or "").lower()
        if input_type not in _CODE_FIELD_TYPES:
            continue
        if entry.get_attribute("name") in ("usuario", "password"):
            continue
        if entry.is_displayed() and entry.is_enabled():
            return entry
    return None


def _error_text(driver) -> str | None:
    from selenium.webdriver.common.by import By

    for element in driver.find_elements(
        By.CSS_SELECTOR, "[class*='error'], [class*='Error']"
    ):
        text = (element.text or "").strip()
        if text and any(marker in text.casefold() for marker in _ERROR_MARKERS):
            return text
    return None


def login_with_browser(
    email: str,
    password: str,
    headless: bool = True,
    ask_code=None,
) -> list[dict]:
    """Completa el login (credenciales + código por correo) y devuelve cookies."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By

    ask_code = ask_code or _ask_code_on_terminal

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,1024")
    driver = webdriver.Chrome(options=options)
    try:
        log.info("Abriendo la página de acceso del portal…")
        driver.get(LOGIN_URL)
        driver.find_element(By.NAME, "usuario").send_keys(email)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.NAME, "conectar").click()

        deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
        code_sent = False
        while time.monotonic() < deadline:
            source = driver.page_source
            if any(marker in source for marker in _SESSION_MARKERS):
                log.info("Sesión iniciada en el portal.")
                return driver.get_cookies()
            error = _error_text(driver)
            if error is not None:
                raise AuthenticationError(
                    f"El portal rechazó el inicio de sesión: {error}"
                )
            if not code_sent:
                field = _code_field(driver)
                if field is not None:
                    code = ask_code()
                    field.clear()
                    field.send_keys(code)
                    form = field.find_element(By.XPATH, "ancestor::form")
                    submit_buttons = form.find_elements(
                        By.CSS_SELECTOR, "input[type='submit'], button[type='submit']"
                    )
                    if submit_buttons:
                        submit_buttons[0].click()
                    else:
                        form.submit()
                    code_sent = True
                    continue
            time.sleep(1)
        raise AuthenticationError(
            "No se pudo completar el inicio de sesión en el tiempo previsto. "
            "Compruebe las credenciales (BOE_SUBASTAS_EMAIL / "
            "BOE_SUBASTAS_PASSWORD) y vuelva a intentarlo, si es necesario con "
            "BOE_SUBASTAS_HEADLESS=0 para ver el navegador."
        )
    finally:
        driver.quit()


def prepare_authenticated_session(session: requests.Session) -> None:
    """Deja `session` autenticada: cookies guardadas o login con navegador.

    Orden: 1) cookies persistidas aún válidas; 2) login con Selenium usando
    las credenciales del entorno, persistiendo las cookies resultantes.
    Eleva `AuthenticationError` si nada de lo anterior es posible.
    """
    path = default_session_file()

    cookies = load_cookies(path)
    if cookies:
        apply_cookies(session, cookies)
        if session_is_connected(session):
            log.info("Reutilizando la sesión guardada en %s", path)
            return
        log.info("La sesión guardada ha caducado; se iniciará sesión de nuevo.")
        session.cookies.clear()

    email = os.environ.get("BOE_SUBASTAS_EMAIL")
    password = os.environ.get("BOE_SUBASTAS_PASSWORD")
    if not email or not password:
        raise AuthenticationError(
            "Faltan credenciales: defina BOE_SUBASTAS_EMAIL y "
            "BOE_SUBASTAS_PASSWORD (véase .env.example) o guarde una sesión "
            "válida."
        )

    headless = os.environ.get("BOE_SUBASTAS_HEADLESS", "1") != "0"
    cookies = login_with_browser(email, password, headless=headless)
    apply_cookies(session, cookies)
    if not session_is_connected(session):
        raise AuthenticationError(
            "El login pareció completarse pero la sesión de scraping no quedó "
            "autenticada."
        )
    save_cookies(path, cookies)
    log.info("Sesión iniciada y guardada en %s", path)
