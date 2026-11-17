"""Property 8: no secrets in code.

Checks, exhaustively over finite sets (Hypothesis is not in the stack):

* every ``.py`` file under ``backend/``, ``datagen/``, ``evals/`` and ``tests/``
  is free of API-key-shaped literals (Groq ``gsk_`` keys, Google ``AIza`` keys,
  long string literals assigned to a ``*_api_key`` name) and of Mongo URIs
  with embedded credentials (``user:pass@``);
* every env-backed field of the four settings classes is listed in
  ``.env.example``;
* ``.env.example`` carries no credentialed URI and leaves every API key empty;
* ``.gitignore`` ignores ``.env`` but keeps ``.env.example``.

Self-exclusion: this file is NOT excluded from the scan. The detector regexes
are assembled from string fragments at import time, so no literal in this file
matches them, and the positive samples used to sanity-check the detectors are
also built at runtime.

Safety: the walk only opens ``*.py`` files inside the ``mulescope/`` project
root, prunes ``.venv`` and cache directories, and refuses any file whose name
starts with ``.env``. The only env-style file ever read is ``.env.example``.

**Validates: Requirements 3.4, 3.5**
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Final

import pytest

from backend.app.core.settings import (
    PROJECT_ROOT,
    ApiSettings,
    BaseAppSettings,
    DatagenSettings,
    EvalsSettings,
)

pytestmark = pytest.mark.unit

_SCAN_ROOTS: Final[tuple[str, ...]] = ("backend", "datagen", "evals", "tests")
_PRUNED_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".venv",
        "venv",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "node_modules",
        "build",
        "dist",
    }
)
_ENV_EXAMPLE: Final[Path] = PROJECT_ROOT / ".env.example"
_GITIGNORE: Final[Path] = PROJECT_ROOT / ".gitignore"

# Detector patterns, assembled from fragments so this file never matches itself.
_GROQ_KEY: Final[re.Pattern[str]] = re.compile("gs" + "k_" + r"[A-Za-z0-9]{20,}")
_GOOGLE_KEY: Final[re.Pattern[str]] = re.compile("AI" + "za" + r"[0-9A-Za-z_\-]{30,}")
_API_KEY_ASSIGNMENT: Final[re.Pattern[str]] = re.compile(
    "_api" + "_key" + r"\b[^=\n]*=\s*(?:SecretStr\()?[\"'][^\"'\s]{16,}[\"']"
)
_CREDENTIALED_MONGO_URI: Final[re.Pattern[str]] = re.compile(
    "mongo" + "db" + r"(?:\+srv)?://[^\s/@:\"']+:[^\s/@\"']+@"
)
_DETECTORS: Final[dict[str, re.Pattern[str]]] = {
    "groq_key": _GROQ_KEY,
    "google_key": _GOOGLE_KEY,
    "api_key_assignment": _API_KEY_ASSIGNMENT,
    "credentialed_mongo_uri": _CREDENTIALED_MONGO_URI,
}

_SETTINGS_CLASSES: Final[tuple[type[BaseAppSettings], ...]] = (
    BaseAppSettings,
    ApiSettings,
    DatagenSettings,
    EvalsSettings,
)


def _is_env_file(path: Path) -> bool:
    """Return True for any ``.env``-style file, which the scan must never open."""
    return path.name.startswith(".env")


def _source_files() -> list[Path]:
    """List every ``.py`` file under the scan roots, pruning venv and caches."""
    files: list[Path] = []
    for root_name in _SCAN_ROOTS:
        root = PROJECT_ROOT / root_name
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _PRUNED_DIRS]
            for filename in filenames:
                path = Path(dirpath) / filename
                if path.suffix == ".py" and not _is_env_file(path):
                    files.append(path)
    return sorted(files)


_FILES: Final[list[Path]] = _source_files()


def _findings(text: str) -> list[str]:
    """Return ``"<detector>: line N"`` entries without echoing the matched value."""
    found: list[str] = []
    for name, pattern in _DETECTORS.items():
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            found.append(f"{name}: line {line_no}")
    return found


def _env_var_names(cls: type[BaseAppSettings]) -> set[str]:
    """Return the env var name for every field of a settings class."""
    names: set[str] = set()
    prefix = str(cls.model_config.get("env_prefix", "") or "")
    for field_name, info in cls.model_fields.items():
        alias = info.validation_alias
        env_name = alias if isinstance(alias, str) else f"{prefix}{field_name}"
        names.add(env_name.upper())
    return names


def _read_env_example() -> str:
    assert _ENV_EXAMPLE.name == ".env.example"  # guard: never any other env file
    return _ENV_EXAMPLE.read_text(encoding="utf-8")


def _gitignore_ignores(name: str) -> bool:
    """Evaluate root-level ``.gitignore`` rules for a file name (last match wins)."""
    ignored = False
    for raw in _GITIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        if pattern.endswith("/"):
            continue  # directory-only rule, never matches a file
        if fnmatch.fnmatchcase(name, pattern.lstrip("/")):
            ignored = not negate
    return ignored


def test_scan_covers_files_and_never_env() -> None:
    assert _FILES, "no source files found to scan"
    assert Path(__file__).resolve() in {p.resolve() for p in _FILES}
    for path in _FILES:
        assert not _is_env_file(path)
        assert PROJECT_ROOT in path.resolve().parents
        assert not set(path.relative_to(PROJECT_ROOT).parts) & _PRUNED_DIRS


def test_detectors_catch_runtime_built_samples() -> None:
    body = "x" * 32
    samples = {
        "groq_key": "gs" + "k_" + body,
        "google_key": "AI" + "za" + body,
        "api_key_assignment": "groq" + "_api_key = '" + body + "'",
        "credentialed_mongo_uri": "mongo" + "db+srv://user:" + "pw@host/db",
    }
    for name, sample in samples.items():
        assert _DETECTORS[name].search(sample), name
    assert not _CREDENTIALED_MONGO_URI.search("mongodb://localhost:27017")
    assert not _API_KEY_ASSIGNMENT.search("groq_api_key: SecretStr | None = None")


@pytest.mark.parametrize(
    "path", _FILES, ids=[p.relative_to(PROJECT_ROOT).as_posix() for p in _FILES]
)
def test_source_file_has_no_secrets(path: Path) -> None:
    findings = _findings(path.read_text(encoding="utf-8"))
    assert not findings, f"secret-shaped literal(s) in {path.name}: {findings}"


@pytest.mark.parametrize("cls", _SETTINGS_CLASSES, ids=lambda c: c.__name__)
def test_env_example_lists_every_settings_field(cls: type[BaseAppSettings]) -> None:
    text = _read_env_example()
    missing = sorted(
        name
        for name in _env_var_names(cls)
        if not re.search(rf"^[ \t]*#?[ \t]*{re.escape(name)}=", text, re.MULTILINE)
    )
    assert not missing, f".env.example is missing: {missing}"


def test_env_example_has_no_credentials_and_empty_keys() -> None:
    text = _read_env_example()
    assert not _findings(text)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().upper().endswith("_API_KEY"):
            assert value.strip() == "", f"{key.strip()} must be empty in .env.example"


def test_gitignore_ignores_env_but_keeps_example() -> None:
    assert _gitignore_ignores(".env")
    assert _gitignore_ignores(".env.local")
    assert not _gitignore_ignores(".env.example")
