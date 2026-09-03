"""Reglas de arquitectura vigiladas por `ast`.

- Imports internos absolutos.
- `parser/` es puro: sin red, sin reloj, sin ficheros, sin conocer el resto.
- Los módulos de página del parser no se importan entre sí; el núcleo no importa páginas.
- `client/search` y `client/collector` no se conocen; nadie importa `cli`.
"""

import ast
from pathlib import Path

from conftest import REPO

PACKAGE = REPO / "src" / "boe_subastas"
PAGES = {"listing", "general", "authority", "related", "assets", "bids"}
CORE = {"normalize", "dom", "detail"}
FORBIDDEN_IN_PARSER = {"requests", "selenium", "os", "time", "boe_subastas.client", "boe_subastas.auth", "boe_subastas.cli"}


def modules():
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        yield path.relative_to(PACKAGE).with_suffix("").as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0
        elif isinstance(node, ast.ImportFrom):
            yield node.module or "", node.level


def test_internal_imports_are_absolute():
    for name, tree in modules():
        assert all(level == 0 for _, level in imports(tree)), f"{name}: import relativo"


def test_parser_is_pure():
    for name, tree in modules():
        if not name.startswith("parser/"):
            continue
        for module, _ in imports(tree):
            assert not any(module == f or module.startswith(f + ".") for f in FORBIDDEN_IN_PARSER), (name, module)


def test_parser_pages_do_not_import_each_other_and_core_does_not_import_pages():
    for name, tree in modules():
        if not name.startswith("parser/"):
            continue
        short = name.split("/")[1]
        for module, _ in imports(tree):
            if module.startswith("boe_subastas.parser."):
                target = module.split(".")[2]
                if short in PAGES:
                    assert target in CORE, f"{name} importa la página {target}"
                if short in CORE:
                    assert target in CORE, f"{name} (núcleo) importa la página {target}"


def test_client_modules_and_cli_dependencies():
    for name, tree in modules():
        targets = {module for module, _ in imports(tree)}
        assert "boe_subastas.cli" not in targets, f"{name} importa cli"
        if name == "client/search":
            assert "boe_subastas.client.collector" not in targets
        if name == "client/collector":
            assert "boe_subastas.client.search" not in targets
        if name.startswith("client/"):
            assert not any(t.startswith("boe_subastas.auth") for t in targets), name
