"""Tipos, constantes y vocabulario del dominio del Portal de Subastas del BOE.

Los códigos de filtro reproducen los del buscador avanzado de la fuente
(`subastas_ava.php`, pares ``campo[i]``/``dato[i]``). Los literales de las
etiquetas son los que muestra el portal y no se traducen.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

from boe_subastas.version import SCHEMA_VERSION, SCRAPER_VERSION, SOURCE

BASE_URL = "https://subastas.boe.es/"

USER_AGENT = (
    f"boe-subastas/{SCRAPER_VERSION} "
    "(+https://github.com/es-property-data/es-boe-subastas)"
)

# Códigos INE de provincia.
PROVINCES: dict[str, str] = {
    "01": "Araba/Álava",
    "02": "Albacete",
    "03": "Alicante/Alacant",
    "04": "Almería",
    "05": "Ávila",
    "06": "Badajoz",
    "07": "Illes Balears",
    "08": "Barcelona",
    "09": "Burgos",
    "10": "Cáceres",
    "11": "Cádiz",
    "12": "Castellón/Castelló",
    "13": "Ciudad Real",
    "14": "Córdoba",
    "15": "A Coruña",
    "16": "Cuenca",
    "17": "Girona",
    "18": "Granada",
    "19": "Guadalajara",
    "20": "Gipuzkoa",
    "21": "Huelva",
    "22": "Huesca",
    "23": "Jaén",
    "24": "León",
    "25": "Lleida",
    "26": "La Rioja",
    "27": "Lugo",
    "28": "Madrid",
    "29": "Málaga",
    "30": "Murcia",
    "31": "Navarra",
    "32": "Ourense",
    "33": "Asturias",
    "34": "Palencia",
    "35": "Las Palmas",
    "36": "Pontevedra",
    "37": "Salamanca",
    "38": "Santa Cruz de Tenerife",
    "39": "Cantabria",
    "40": "Segovia",
    "41": "Sevilla",
    "42": "Soria",
    "43": "Tarragona",
    "44": "Teruel",
    "45": "Toledo",
    "46": "Valencia/València",
    "47": "Valladolid",
    "48": "Bizkaia",
    "49": "Zamora",
    "50": "Zaragoza",
    "51": "Ceuta",
    "52": "Melilla",
    "00": "No consta",
}

# dato[0] — SUBASTA.ORIGEN
ORIGINS: dict[str, str] = {
    "J": "Judicial",
    "N": "Notarial",
    "A": "AEAT",
    "R": "Otras administraciones tributarias",
    "G": "Subastas administrativas generales",
}

# dato[2] — SUBASTA.ESTADO.CODIGO
STATUSES: dict[str, str] = {
    "PU": "Prox. apertura",
    "EJ": "Celebrándose",
    "SU": "Suspendida",
    "CA": "Cancelada",
    "PC": "Concluida en Portal de Subastas",
    "FS": "Finalizada por Autoridad Gestora",
}

# dato[3] — BIEN.TIPO
ASSET_TYPES: dict[str, str] = {
    "I": "Inmuebles",
    "V": "Vehículos",
    "M": "Otros bienes muebles",
}

# dato[4] — subtipo de bien
ASSET_SUBTYPES: dict[str, str] = {
    # Inmuebles
    "501": "Vivienda",
    "502": "Local comercial",
    "503": "Garaje",
    "504": "Trastero",
    "505": "Nave industrial",
    "506": "Solar",
    "507": "Finca rústica",
    "599": "Otros (inmuebles)",
    # Vehículos
    "9101": "Turismos",
    "9102": "Industriales",
    "9103": "Otros (vehículos)",
    # Otros bienes muebles
    "13": "Aeronaves",
    "14": "Buques",
    "18": "Concesiones administrativas",
    "4": "Derechos de propiedad industrial",
    "3": "Derechos de propiedad intelectual",
    "1": "Derechos de traspaso",
    "2": "Instalaciones",
    "17": "Joyas, obras de arte y antigüedades",
    "5": "Maquinaria",
    "8": "Mercaderías y materias primas",
    "7": "Mobiliario",
    "11": "Tarjetas de transporte",
    "16": "Tranvía",
    "6": "Utensilios y herramientas",
    "15": "Vagón",
    "99": "Otros bienes y derechos",
}


def _normalize(text: str) -> str:
    flat = unicodedata.normalize("NFKD", text)
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return " ".join(flat.casefold().split())


def province_code(value: str) -> str:
    """Devuelve el código INE de una provincia a partir de su código o nombre.

    Acepta el código de dos dígitos (``"07"``, ``"7"``) o el nombre en
    cualquiera de sus formas oficiales (``"Illes Balears"``, ``"Alacant"``),
    sin distinguir mayúsculas ni tildes.
    """
    raw = value.strip()
    if raw.isdigit():
        code = raw.zfill(2)
        if code in PROVINCES:
            return code
        raise ValueError(f"Código de provincia desconocido: {value!r}")
    needle = _normalize(raw)
    for code, name in PROVINCES.items():
        variants = [name] + name.split("/")
        if any(_normalize(variant) == needle for variant in variants):
            return code
    raise ValueError(
        f"Provincia desconocida: {value!r}. Use el código INE o el nombre "
        "oficial (p. ej. '07' o 'Illes Balears')."
    )


def envelope(external_id: str, url: str | None, data: dict) -> dict:
    """Construye el sobre de intercambio definido en schemas/item.schema.json."""
    return {
        "meta": {
            "source": SOURCE,
            "schema_version": SCHEMA_VERSION,
            "scraper_version": SCRAPER_VERSION,
            "external_id": external_id,
            "url": url,
            "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "data": data,
    }
