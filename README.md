# Recolector del Portal de Subastas del BOE

[![Tests](https://github.com/es-property-data/es-boe-subastas/actions/workflows/tests.yml/badge.svg)](https://github.com/es-property-data/es-boe-subastas/actions/workflows/tests.yml)
[![Canary](https://github.com/es-property-data/es-boe-subastas/actions/workflows/canary.yml/badge.svg)](https://github.com/es-property-data/es-boe-subastas/actions/workflows/canary.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Licencia: Apache 2.0](https://img.shields.io/badge/licencia-Apache%202.0-blue.svg)](LICENSE)

Recolector del **Portal de Subastas de la Agencia Estatal Boletín Oficial del
Estado** (<https://subastas.boe.es>). Recorre el portal y emite cada subasta
como datos estructurados en formato JSON Lines, listos para procesar.

## Índice

1. [Características](#características)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Configuración](#configuración)
5. [Uso](#uso)
6. [Formato de salida](#formato-de-salida)
7. [Códigos de salida](#códigos-de-salida)
8. [Arquitectura](#arquitectura)
9. [Desarrollo y pruebas](#desarrollo-y-pruebas)
10. [Integración continua](#integración-continua)
11. [Aviso legal](#aviso-legal)
12. [Licencia](#licencia)

## Características

- **Búsqueda con filtros** por provincia, estado, origen, tipo de bien,
  localidad, código postal, dirección, autoridad gestora y fecha de inicio.
- **Recuperación por identificador** de subastas concretas o de lotes
  concretos (`SUB-JA-2026-265000/L2`).
- **Un sobre por unidad subastada**: cada lote es un ítem propio con su
  identificador estable.
- **Troceo automático** de las búsquedas que el portal rechaza por amplias.
- **Sesión de usuario registrado opcional** (`--auth`) para ver el importe de
  las pujas de las subastas en curso.
- **Salida en streaming** por stdout, validada contra un esquema JSON; logs y
  avisos por stderr.
- **Ritmo de peticiones fijo y conservador**: una petición cada 1,5 segundos
  como máximo, con hasta 3 intentos ante errores temporales, e identificación
  honesta ante el portal (User-Agent `boe-subastas/<versión>` con la URL del
  proyecto).
- **Multiplataforma**: Linux, macOS y Windows.

## Requisitos

| Requisito | Detalle |
|---|---|
| Python | 3.11 o superior |
| Git | para clonar el repositorio |
| Google Chrome | solo para `--auth`; Selenium descarga el driver automáticamente |
| Conexión a internet | acceso a `https://subastas.boe.es` |

Dependencias Python (se instalan solas): `requests`, `beautifulsoup4`,
`lxml`, `selenium`, `python-dotenv`; para desarrollo, `pytest` y
`jsonschema`; para el notebook de exploración, `pandas` y `notebook`. La lista informativa está en [requirements.txt](requirements.txt)
y la declaración canónica en [pyproject.toml](pyproject.toml).

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/es-property-data/es-boe-subastas.git
cd es-boe-subastas
```

### 2. Crear un entorno aislado

Con **conda**:

```bash
conda create -n es-boe-subastas python=3.11
conda activate es-boe-subastas
```

O con **venv** (Linux y macOS):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

En **Windows** (PowerShell):

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar el recolector

Instalación normal (modo editable, para que los cambios en el código se
apliquen sin reinstalar):

```bash
pip install -e .
```

Con las herramientas de desarrollo (tests y validación del esquema):

```bash
pip install -e ".[dev]"
```

Con el notebook de exploración (Jupyter y pandas):

```bash
pip install -e ".[notebook]"
```

Los grupos se combinan: `pip install -e ".[dev,notebook]"`.

### 4. Comprobar la instalación

```bash
boe-subastas --version
```

```bash
boe-subastas info
```

Y, si instalaste las herramientas de desarrollo, la batería de tests (no
necesita red):

```bash
pytest
```

## Configuración

El recolector funciona sin configuración. Solo `--auth` necesita variables de
entorno, que puede leer de un fichero `.env` en la carpeta del proyecto: copia
[.env.example](.env.example) a `.env` y rellénalo.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `BOE_SUBASTAS_EMAIL` | con `--auth` | Correo (o teléfono) del usuario registrado en el portal. |
| `BOE_SUBASTAS_PASSWORD` | con `--auth` | Contraseña del usuario. |
| `BOE_SUBASTAS_SESSION_FILE` | no | Ruta del fichero de sesión. Por defecto `~/.config/boe-subastas/session.json` (Linux y macOS) o `%APPDATA%\boe-subastas\session.json` (Windows). |
| `BOE_SUBASTAS_HEADLESS` | no | `0` para ver el navegador durante el inicio de sesión; por defecto oculto. |

Nunca escribas las credenciales en la línea de órdenes ni las subas al
repositorio: `.env` está en `.gitignore`.

## Uso

Tres subcomandos: `search` (descubrir subastas con filtros), `fetch`
(recuperar subastas concretas por identificador) e `info` (describir el
recolector sin tocar la red). `--help` en cada subcomando es la documentación
de referencia de sus opciones.

### Buscar subastas

```bash
# Todas las subastas de Illes Balears, en cualquier estado
boe-subastas search --province "Illes Balears" -o baleares.jsonl
```

```bash
# Solo las que se están celebrando ahora mismo, y solo inmuebles
boe-subastas search --province 07 --status EJ --asset-type I
```

| Opción | Campo en la fuente | Valores |
|---|---|---|
| `--province` | `BIEN.COD_PROVINCIA` | Código INE o nombre oficial (`07`, `"Illes Balears"`, `Alacant`). |
| `--status` | `SUBASTA.ESTADO.CODIGO` | `PU` Próxima apertura · `EJ` Celebrándose · `SU` Suspendida · `CA` Cancelada · `PC` Concluida en Portal de Subastas · `FS` Finalizada por Autoridad Gestora. |
| `--origin` | `SUBASTA.ORIGEN` | `J` Judicial · `N` Notarial · `A` AEAT · `R` Otras administraciones tributarias · `G` Administrativas generales. |
| `--asset-type` | `BIEN.TIPO` | `I` Inmuebles · `V` Vehículos · `M` Otros bienes muebles. |
| `--locality` | `BIEN.LOCALIDAD` | Texto libre. |
| `--postal-code` | `BIEN.CODPOSTAL` | Texto libre. |
| `--address` | `BIEN.DIRECCION` | Texto libre. |
| `--authority` | `SUBASTA.AUTORIDAD` | Texto libre. |
| `--since` | `SUBASTA.FECHA_INICIO` | Fecha ISO (`AAAA-MM-DD`). Filtra por fecha de inicio de la subasta; la fuente no expone fecha de modificación. |
| `--limit N` | — | Corta la emisión al alcanzar N sobres. |
| `-o FICHERO` | — | Escribe los datos en un fichero (truncándolo) en vez de en stdout. |

Si una búsqueda es tan amplia que el portal la rechaza («número de resultados
excesivo»), el recolector la trocea automáticamente en subconsultas (por
estado, por provincia y, como último recurso, por rangos de fecha de inicio)
y une los resultados sin duplicados. En el caso teórico de que ni una ventana
de un solo día quepa, esa ventana se omite dejando un error en stderr y la
recolección continúa.

Dato importante: **las subastas recién publicadas están en estado `PU`
(Próxima apertura)**, no en `EJ`. Para no perderse novedades, busca sin
`--status` o incluye `PU`.

### Recuperar subastas concretas

```bash
# Subastas por identificador; un lote concreto se pide con el sufijo /L<n>
boe-subastas fetch SUB-JA-2026-265000 SUB-JA-2026-265003/L2
```

### Describir el recolector

```bash
boe-subastas info
```

Emite una única línea JSON con la fuente, las versiones, los filtros
admitidos y el ritmo de peticiones. No accede a la red.

### Sesión de usuario registrado (`--auth`)

Sin sesión, el portal oculta el importe de las pujas de las subastas en curso
(«La subasta ha recibido alguna puja. Para ver su importe debe acceder como
usuario registrado»). Con `--auth`, el recolector inicia sesión con un usuario
registrado del portal y esos importes aparecen en los sobres.

```bash
boe-subastas search --province 07 --status EJ --auth
```

1. Configura `BOE_SUBASTAS_EMAIL` y `BOE_SUBASTAS_PASSWORD` (véase
   [Configuración](#configuración)).
2. La primera vez, el portal envía un código de verificación a tu correo: el
   recolector lo pide por la terminal. El inicio de sesión se hace con un
   navegador controlado por Selenium (`BOE_SUBASTAS_HEADLESS=0` para verlo).
3. La sesión se guarda en el fichero de sesión (con permisos restrictivos en
   Linux y macOS; en Windows lo protege el perfil de usuario) y se reutiliza
   en siguientes ejecuciones sin repetir el inicio de sesión mientras el
   portal la mantenga viva.

Si la sesión caduca a mitad de ejecución, el recolector lo detecta y termina
con código 3 en lugar de emitir datos incompletos en silencio. El código de
verificación se lee siempre de la terminal, nunca de una tubería, así que en
ejecuciones desatendidas (cron) una sesión caducada termina con código 3:
basta ejecutar una vez de forma interactiva para renovarla.

### Salida por canales

- **stdout** lleva únicamente los datos: una línea JSON por sobre, sin nada
  más. Se puede redirigir o encadenar con total seguridad
  (`boe-subastas search … | jq …`).
- **stderr** lleva todo lo demás: progreso, avisos y errores.

Cada sobre se emite en cuanto está listo (streaming) y valida contra
[schemas/item.schema.json](schemas/item.schema.json).

### Notebook de exploración

Para ver los datos de forma visual hay un cuaderno Jupyter en
[notebooks/explore_auctions.ipynb](notebooks/explore_auctions.ipynb), guardado
con sus resultados para poder leerlo directamente en GitHub. Busca las
subastas de una provincia, las presenta con `pandas` (tabla resumen, recuento
por estado, ficha de una subasta pestaña a pestaña) y guarda el resultado en
JSONL y CSV. Los parámetros (provincia, estado, tipo de bien, límite, sesión
registrada) se cambian en la primera celda.

```bash
pip install -e ".[notebook]"
jupyter notebook notebooks/explore_auctions.ipynb
```

Para validar cualquier fichero de salida contra el esquema:

```bash
python scripts/validate_output.py baleares.jsonl
```

## Formato de salida

Cada línea es un **sobre** con dos partes:

- **`meta`** — metadatos de la captura, iguales para todas las fuentes de la
  familia: `source`, `schema_version`, `scraper_version`, `external_id`,
  `url`, `scraped_at`.
- **`data`** — el contenido de la subasta tal y como lo publica el portal.

Ejemplo abreviado (un lote de una subasta judicial):

```json
{
  "meta": {
    "source": "boe_subastas",
    "schema_version": 1,
    "scraper_version": "1.0.0",
    "external_id": "SUB-JA-2026-265000/L1",
    "url": "https://subastas.boe.es/detalleSubasta.php?idSub=SUB-JA-2026-265000&ver=3&idLote=1",
    "scraped_at": "2026-09-01T18:13:05Z"
  },
  "data": {
    "identificador_subasta": "SUB-JA-2026-265000",
    "lote": {"numero": 1, "valor_subasta": 262046.95, "tasacion": 0.0, "puja_minima": "Sin puja mínima", "tramos_pujas": 5240.94, "importe_deposito": 13102.35, "cantidad_reclamada": null, "otros": null},
    "descripcion": "SUBASTA VIVIENDA EN SANT JORDI (SAN JOSÉ).",
    "bienes": [{"numero": 1, "tipo": "Inmueble", "subtipo": "Vivienda", "referencia_catastral": "1767906CD6016N0052UE", "vivienda_habitual": "Sí", "…": "…"}],
    "pujas": {"puja_mas_alta": null, "mensaje": "Sin pujas en el lote 1 de esta subasta", "certificado_cierre": null},
    "subasta": {"identificador": "SUB-JA-2026-265000", "tipo": "JUDICIAL EN VÍA DE APREMIO", "estado": "Celebrándose", "fecha_inicio": "2026-08-25T18:00:00+02:00", "fecha_conclusion": "2026-09-14T18:00:00+02:00", "lotes": 2, "…": "…"}
  }
}
```

### Campos de `data`

| Campo | Qué es |
|---|---|
| `identificador_subasta` | Número de expediente de la subasta madre; común a todos sus lotes. |
| `lote` | Si esta línea es un lote, su número y sus condiciones económicas (valor de subasta, tasación, fianza…); `null` si la subasta se vende entera. |
| `descripcion` / `descripcion_anuncio` | Resumen corto y texto largo del anuncio, tal cual los escribe el organismo. |
| `bienes` | Los objetos físicos que se venden: descripción legal, dirección, referencia catastral, si es vivienda habitual, quién lo ocupa, cargas que hereda el comprador, fotos y documentos. |
| `pujas` | La mejor oferta hasta ahora (si es visible), o el mensaje literal del portal; y el certificado de cierre si la subasta terminó. |
| `subasta` | La ficha de la subasta madre: quién la organiza y su contacto, fechas de inicio y conclusión, deuda reclamada, anuncio en el BOE, documentos, acreedores y administración concursal cuando el portal los publica. |

El detalle campo a campo, con descripciones pensadas para quien no conoce el
mundo de las subastas, está en el propio
[schemas/item.schema.json](schemas/item.schema.json).

### Reglas de normalización

- Los importes de los campos económicos son números en euros (`145660.86`).
- Las fechas van en ISO 8601 con su huso horario; si el portal no publica la
  forma con huso, se emiten sin él y corresponden a hora peninsular española.
- `null` significa siempre «el portal no da ese dato» (su «No consta»).
- Los textos se conservan literales, erratas incluidas: el recolector
  normaliza formato, nunca vocabulario.
- Las filas de la ficha que el recolector no tenga tipificadas no se pierden:
  se emiten en los campos `otros` con su etiqueta y su valor tal cual (así
  aparecen, por ejemplo, la matrícula y la marca en las subastas de
  vehículos).
- La salida es determinista: dos ejecuciones sobre una fuente sin cambios
  producen los mismos datos (solo cambia `scraped_at`).

## Códigos de salida

| Código | Significado |
|---|---|
| 0 | Ejecución correcta. |
| 1 | Error inesperado; también `fetch` cuando alguno de los identificadores pedidos no existe en la fuente. |
| 2 | Uso incorrecto: opción o argumento inválido, fichero de salida no escribible. |
| 3 | Fuente inaccesible: red, servidor, bloqueo o fallo de autenticación. |
| 4 | Estructura cambiada: se conectó y descargó, pero al menos un ítem no se pudo interpretar. Los ítems buenos se emiten igualmente. |

## Arquitectura

```
src/boe_subastas/
├── cli.py               # punto de entrada; traduce excepciones a códigos de salida
├── client/              # acceso a la fuente, por responsabilidad
│   ├── connection.py    #   conexión: HTTP, ritmo, reintentos, control de sesión
│   ├── search.py        #   búsqueda: consulta, paginación, particionado automático
│   └── collector.py     #   recolección: ficha completa -> sobres (subasta o lote)
├── parser/              # HTML -> dicts; funciones puras, sin red (un módulo por página)
│   ├── normalize.py     #   reglas de formato: importes, fechas, texto y URLs
│   ├── dom.py           #   ayudas genéricas sobre el árbol HTML
│   ├── detail.py        #   armazón común de la ficha (pestañas, avisos, bloques)
│   ├── listing.py       #   resultados del buscador
│   ├── general.py       #   pestaña «Información general»
│   ├── authority.py     #   pestaña «Autoridad gestora»
│   ├── related.py       #   pestaña «Relacionados»
│   ├── assets.py        #   pestaña «Bienes» / «Lotes»
│   └── bids.py          #   pestaña «Pujas»
├── auth.py              # inicio de sesión en el portal (Selenium)
├── models.py            # vocabulario del dominio y construcción del sobre
├── errors.py            # jerarquía de excepciones del paquete
└── version.py           # única fuente de verdad de las versiones
```

Versionado: `scraper_version` (versión del paquete) sigue versionado
semántico; `schema_version` solo se incrementa ante un cambio incompatible en
la forma de `data` (añadir un campo nuevo no la incrementa). Durante el
desarrollo ambas permanecen en `1.0.0` / `1`.

## Desarrollo y pruebas

```bash
pip install -e ".[dev]"
pytest
```

Los tests (`tests/`) no tocan la red: una conexión falsa sirve las capturas
reales del portal guardadas en `tests/fixtures/` y se comprueba el parser
página a página, el ensamblado de los sobres, su validez contra el esquema,
los códigos de salida del CLI y las reglas de arquitectura (imports
permitidos). Los fixtures son capturas hechas por las personas que mantienen
el repositorio; cuando el portal cambia, la captura nueva se añade junto a la
antigua y ambas deben seguir interpretándose.

La batería vive en `tests/` (sin `__init__.py`): un fichero por módulo del
paquete, más `test_collector.py` (ensamblado y validación de todos los sobres
contra el esquema), `test_cli.py` (canales y códigos de salida) y
`test_architecture.py` (reglas de imports). `conftest.py` aporta la conexión
falsa que sirve los fixtures.

Para validar a mano cualquier fichero de salida:

```bash
python scripts/validate_output.py baleares.jsonl
```

## Integración continua

| Workflow | Cuándo | Qué hace |
|---|---|---|
| **Tests** | en cada push a `main` y en cada pull request | Instala el paquete en Python 3.11, 3.12 y 3.13, comprueba el esquema y ejecuta la batería de tests. |
| **Canary** | cada lunes a las 06:00 UTC, o a mano desde *Actions → Canary → Run workflow* | Ejecuta el recolector contra el portal real con un caso conocido y valida la salida; si el código de salida es 4 o la salida no valida, abre o actualiza una incidencia con la etiqueta `canary`. La salida y los registros quedan como artefactos de la ejecución. |

Dependabot propone semanalmente las actualizaciones de las acciones de GitHub
y de las dependencias Python.

## Aviso legal

Este recolector accede únicamente a información publicada abiertamente por la
Agencia Estatal Boletín Oficial del Estado en su Portal de Subastas. El uso
que se haga de la herramienta y de los datos obtenidos es responsabilidad
exclusiva de quien la ejecuta.

## Licencia

[Apache 2.0](LICENSE).
