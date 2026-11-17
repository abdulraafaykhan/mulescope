"""Property 9: config sourcing.

No threshold, weight, model name, timeout or limit may be a literal in
``backend/app/domain``, ``backend/app/services`` or ``backend/app/graph``; such
values come from settings or ``config/*.yaml``. The property is checked
exhaustively (Hypothesis is not in the stack) by parsing every module in those
packages with :mod:`ast` and walking the tree, one parametrized case per module.

Heuristics:

* **Numeric literals.** Any ``int``/``float``/``complex`` constant is flagged
  unless its value is in the allow-list ``{0, 1, -1}``. ``-1`` is recognised as
  unary minus applied to the literal ``1``. Booleans are not numbers here.
* **Model-name strings.** A string constant is flagged when it contains, case
  insensitively, a known model-family token: ``llama``, ``gemini``, ``gemma``,
  ``gpt``, ``mixtral``, ``mistral``, ``claude`` or ``qwen``.
* **Duration strings.** A string constant is flagged when the whole value is a
  number followed by a time unit, for example ``"30d"``, ``"7 days"``,
  ``"3600s"``, ``"500ms"``, ``"2h"`` or ``"1 week"``.
* **Exemptions.** Docstrings (the first string expression of a module, class or
  function) are skipped. Bodies of enum classes (any class with a base whose
  name ends in ``Enum``, such as ``StrEnum``) are skipped, because enum member
  values are closed-set identifiers, not tunables.

The checker also covers the string parts of f-strings. A sanity test runs the
checker on synthetic offending and clean sources so the heuristics stay honest,
and the walk asserts it found at least the domain modules, so the test remains
meaningful as ``services/`` and ``graph/`` gain modules.

**Validates: Requirements 3.6**
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from backend.app.core.settings import PROJECT_ROOT

pytestmark = pytest.mark.unit

_SCANNED_PACKAGES: Final[tuple[str, ...]] = (
    "backend/app/domain",
    "backend/app/services",
    "backend/app/graph",
)
_ALLOWED_NUMBERS: Final[frozenset[int]] = frozenset({0, 1, -1})
_MODEL_NAME: Final[re.Pattern[str]] = re.compile(
    r"llama|gemini|gemma|gpt|mixtral|mistral|claude|qwen", re.IGNORECASE
)
_DURATION: Final[re.Pattern[str]] = re.compile(
    r"^\s*\d+(?:\.\d+)?\s*"
    r"(?:ms|millis(?:econds?)?|s|secs?|seconds?|m|mins?|minutes?"
    r"|h|hrs?|hours?|d|days?|w|wks?|weeks?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Finding:
    """One offending literal found by the checker."""

    line: int
    kind: str
    value: str


def _is_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_enum_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if isinstance(name, str) and name.endswith("Enum"):
            return True
    return False


class _LiteralChecker(ast.NodeVisitor):
    """Collects numeric and string literals that violate the config-sourcing rule."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def _visit_body(self, body: list[ast.stmt]) -> None:
        for index, stmt in enumerate(body):
            if index == 0 and _is_docstring(stmt):
                continue
            self.visit(stmt)

    def visit_Module(self, node: ast.Module) -> None:
        self._visit_body(node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword)
        if not _is_enum_class(node):
            self._visit_body(node.body)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        self.visit(node.args)
        if node.returns is not None:
            self.visit(node.returns)
        self._visit_body(node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        operand = node.operand
        if (
            isinstance(node.op, ast.USub)
            and isinstance(operand, ast.Constant)
            and _is_number(operand.value)
        ):
            self._check_number(-operand.value, node.lineno)
            return
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        value = node.value
        if _is_number(value):
            self._check_number(value, node.lineno)
        elif isinstance(value, str):
            if _MODEL_NAME.search(value):
                self.findings.append(Finding(node.lineno, "model_name", value))
            elif _DURATION.match(value):
                self.findings.append(Finding(node.lineno, "duration", value))

    def _check_number(self, value: complex, line: int) -> None:
        if value not in _ALLOWED_NUMBERS:
            self.findings.append(Finding(line, "number", repr(value)))


def _is_number(value: object) -> bool:
    return isinstance(value, int | float | complex) and not isinstance(value, bool)


def check_source(source: str) -> list[Finding]:
    """Return every config-sourcing violation in a Python source string."""
    checker = _LiteralChecker()
    checker.visit(ast.parse(source))
    return checker.findings


def _modules() -> list[Path]:
    files: list[Path] = []
    for package in _SCANNED_PACKAGES:
        root = PROJECT_ROOT / package
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


_MODULES: Final[list[Path]] = _modules()


def test_walk_finds_domain_modules() -> None:
    domain_root = PROJECT_ROOT / "backend/app/domain"
    found = {p.resolve() for p in _MODULES}
    assert (domain_root / "__init__.py").resolve() in found
    assert (domain_root / "enums.py").resolve() in found
    for package in _SCANNED_PACKAGES:
        assert (PROJECT_ROOT / package / "__init__.py").resolve() in found, package


def test_checker_flags_offending_source() -> None:
    offending = '''
"""Module docstring mentioning llama-3 and 30d is fine."""
TIMEOUT = 30
RATIO = 0.75
FLOOR = -5
MODEL = "llama-3.1-8b-instant"
OTHER = f"gemini-{TIMEOUT}"
TTL = "7 days"
WINDOW = "3600s"

def score(x: int) -> int:
    """Docstring with gpt-4o and 2h is fine."""
    return x * 3
'''
    findings = check_source(offending)
    counts = {kind: sum(f.kind == kind for f in findings) for kind in {f.kind for f in findings}}
    assert counts == {"number": 4, "model_name": 2, "duration": 2}, findings


def test_checker_accepts_clean_source() -> None:
    clean = '''
"""Clean module: values come from settings; llama and 30d only in docstrings."""
from enum import IntEnum, StrEnum

class Provider(StrEnum):
    """Members may look like model families."""
    GEMINI = "gemini"
    CLAUDE = "claude"

class Level(IntEnum):
    HIGH = 3

def pick(items: list[int], threshold: float) -> int:
    """Return the first index, or -1."""
    if not items:
        return -1
    return items[0] + 1 if items[0] > threshold else 0

LABEL = "disposition"
'''
    assert check_source(clean) == []


@pytest.mark.parametrize(
    "path", _MODULES, ids=[p.relative_to(PROJECT_ROOT).as_posix() for p in _MODULES]
)
def test_module_has_no_config_literals(path: Path) -> None:
    findings = check_source(path.read_text(encoding="utf-8"))
    assert not findings, f"config literal(s) in {path.name}: {findings}"
