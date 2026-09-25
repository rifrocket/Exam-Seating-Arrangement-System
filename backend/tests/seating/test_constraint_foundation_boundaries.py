"""Architecture-boundary test for the Milestone 6 constraint foundation.

Asserts, by parsing the source (not by importing and inspecting
sys.modules, which could pass even if the module reached into a forbidden
package transitively through something already imported elsewhere) that
`app/seating/topology.py` and `app/seating/constraints.py` never import
FastAPI, SQLAlchemy, ReportLab, a repository, an HTTP client, or anything
under app.db / app.api — the same boundary the rest of app/seating/
already holds, per docs/architecture.md.
"""

import ast
from pathlib import Path

FORBIDDEN_MODULE_PREFIXES = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "reportlab",
    "httpx",
    "requests",
    "app.db",
    "app.api",
    "app.repositories",
)

MODULES_UNDER_TEST = (
    Path(__file__).resolve().parents[2] / "app" / "seating" / "topology.py",
    Path(__file__).resolve().parents[2] / "app" / "seating" / "constraints.py",
)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_topology_and_constraints_modules_have_no_forbidden_imports() -> None:
    for path in MODULES_UNDER_TEST:
        assert path.is_file(), f"expected file at {path}"
        imported = _imported_module_names(path.read_text())
        for module_name in imported:
            for forbidden in FORBIDDEN_MODULE_PREFIXES:
                assert not (module_name == forbidden or module_name.startswith(forbidden + ".")), (
                    f"{path.name} imports '{module_name}', which starts with forbidden prefix '{forbidden}'"
                )
