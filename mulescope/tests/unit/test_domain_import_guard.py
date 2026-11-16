"""Property 1: layer isolation.

For every module under ``backend/app/domain``, its transitive import set must
contain none of ``fastapi``, ``pymongo``, ``bson`` (shipped with pymongo),
``motor`` or ``langgraph``. The property is checked exhaustively (Hypothesis is
not in the stack): modules are enumerated with :func:`pkgutil.walk_packages`
and each is imported in a fresh interpreter, so modules already loaded by the
test process cannot mask or fake a result.

The child process is started with ``sys.executable`` and list arguments (no
shell), and prints only a JSON list of offending module names. It never reads
or echoes environment variables.

**Validates: Requirements 4.2**
"""

from __future__ import annotations

import json
import pkgutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DOMAIN_DIR: Final[Path] = PROJECT_ROOT / "backend" / "app" / "domain"
DOMAIN_PACKAGE: Final[str] = "backend.app.domain"
FORBIDDEN_PREFIXES: Final[tuple[str, ...]] = ("fastapi", "pymongo", "bson", "motor", "langgraph")
SUBPROCESS_TIMEOUT_SECONDS: Final[float] = 60.0

# Imports the module named in argv[1], then prints the sorted list of loaded
# top-level module names that match a forbidden prefix (argv[2:]).
_CHECK_SCRIPT: Final[str] = (
    "import importlib, json, sys\n"
    "importlib.import_module(sys.argv[1])\n"
    "prefixes = tuple(sys.argv[2:])\n"
    "hits = sorted(\n"
    "    name for name in sys.modules\n"
    "    if name.split('.', 1)[0] in prefixes\n"
    ")\n"
    "print(json.dumps(hits))\n"
)


def _domain_modules() -> list[str]:
    """Return the dotted names of the domain package and all its submodules."""
    names = [DOMAIN_PACKAGE]
    for info in pkgutil.walk_packages([str(DOMAIN_DIR)], prefix=f"{DOMAIN_PACKAGE}."):
        names.append(info.name)
    return sorted(names)


def _forbidden_imports(module: str) -> list[str]:
    """Import ``module`` in a fresh interpreter and return forbidden modules it loaded."""
    result = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT, module, *FORBIDDEN_PREFIXES],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, f"importing {module} failed:\n{result.stderr}"
    hits: list[str] = json.loads(result.stdout.strip().splitlines()[-1])
    return hits


DOMAIN_MODULES: Final[list[str]] = _domain_modules()


@pytest.mark.unit
def test_walk_finds_domain_modules() -> None:
    """The enumeration is not vacuous: it finds the package and ``enums``."""
    assert DOMAIN_PACKAGE in DOMAIN_MODULES
    assert f"{DOMAIN_PACKAGE}.enums" in DOMAIN_MODULES


@pytest.mark.unit
@pytest.mark.parametrize("module", DOMAIN_MODULES)
def test_domain_module_imports_no_framework(module: str) -> None:
    """Importing a domain module pulls in no FastAPI, PyMongo/bson, Motor or LangGraph."""
    hits = _forbidden_imports(module)
    assert hits == [], f"{module} transitively imports forbidden modules: {hits}"


@pytest.mark.unit
def test_guard_detects_forbidden_import() -> None:
    """Sanity check: the same subprocess guard flags a module that imports pymongo."""
    hits = _forbidden_imports("pymongo")
    assert "pymongo" in hits
    assert "bson" in hits
