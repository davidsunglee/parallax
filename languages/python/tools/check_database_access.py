"""Fail when a test can reach a live database outside its designated fixture.

Each collected item's scheduling class is derived from its fixture closure
(``tests/conftest.py``), so an item that acquires a database by any other route
is classified ``dbfree`` while needing a container. That failure is silent
rather than loud: CI runners have Docker, so the mis-classified item passes in
the database-free job instead of erroring, and ``dbfree`` stops being true of
what it selects.

The guard is a call-level rule, not an import-level one. Importing the adapter
or the provisioning module is legitimate — the internal-behavior surface
type-checks error translation against fake connections and reads the module's
constants — while *calling* one of the seams below opens a socket. Each call's
target is resolved through the importing module's own bindings, so a local name
that merely looks like a seam is not one, and a seam reached under an alias
still is.

Three structural facts are checked with it, because the rule is vacuous without
them: every declared seam must still name an importable callable, the designated
fixture must exist, and the classifier's own designated set must name exactly it.

Usage
-----
* ``python tools/check_database_access.py``          check (default)
* ``python tools/check_database_access.py --check``  check (explicit)

Same ``--check``/exit-1 contract as ``tools/check_untracked_sources.py``: it
never mutates anything and exits non-zero on any finding.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

_TOOL = "tools/check_database_access.py"
TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"

ENTRY_POINT_MODULE = "conftest.py"
ENTRY_POINT_FIXTURE = "provisioner"
CLASSIFIER_CONSTANT = "_DATABASE_FIXTURES"

# Fully qualified callables that acquire a live database. Constructing the
# provisioner or a container starts a server; the two ``connect`` seams open a
# socket to one. Constructing `PostgresAdapter` over an already-open connection
# is deliberately absent: the internal-behavior surface wraps fakes with it.
DATABASE_SEAMS: frozenset[str] = frozenset(
    {
        "parallax.conformance.provision.Provisioner",
        "parallax.postgres.PostgresAdapter.connect",
        "psycopg.connect",
        "testcontainers.community.postgres.PostgresContainer",
    }
)


@dataclass(frozen=True)
class Finding:
    """One violation, addressed the way an editor jumps to it."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Map every name the module binds by import to the dotted path it names.

    Function-local imports count: the designated fixture defers its own import
    of the provisioner so an unavailable provider skips rather than errors at
    collection.
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    head = alias.name.split(".")[0]
                    bindings[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _resolved_target(func: ast.expr, bindings: dict[str, str]) -> str | None:
    """The dotted path *func* names, with its head expanded through *bindings*.

    ``None`` when the callee is not a plain dotted name — a call on a subscript,
    a call of a call, or an attribute of a literal.
    """
    parts: list[str] = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    parts.reverse()
    head = bindings.get(parts[0])
    if head is None:
        return ".".join(parts)
    return ".".join([head, *parts[1:]])


def _resolves_to_callable(dotted: str) -> bool:
    """Whether *dotted* still names an importable callable.

    The longest importable prefix is the module; the rest is walked as
    attributes. A seam that resolves to a non-callable is as dead as a missing
    one — nothing spelled that way can be called.
    """
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        try:
            target: object = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for attribute in parts[split:]:
            if not hasattr(target, attribute):
                return False
            target = getattr(target, attribute)
        return callable(target)
    return False


def unresolved_seams() -> tuple[str, ...]:
    """Every entry of :data:`DATABASE_SEAMS` that no longer names a callable.

    The seam set is hand-maintained against code it does not import, so a
    renamed or deleted seam would otherwise leave the guard reporting success
    over a rule that matches nothing.
    """
    return tuple(seam for seam in sorted(DATABASE_SEAMS) if not _resolves_to_callable(seam))


def seam_calls(tree: ast.Module) -> list[tuple[int, str]]:
    """Every call in *tree* whose target resolves to a database seam."""
    bindings = _imported_names(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = _resolved_target(node.func, bindings)
            if target is not None and target in DATABASE_SEAMS:
                found.append((node.lineno, target))
    return sorted(found)


def _entry_point_span(tree: ast.Module, fixture: str) -> tuple[int, int] | None:
    """The line range of the top-level function named *fixture*, if it exists."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == fixture:
            return (node.lineno, node.end_lineno or node.lineno)
    return None


def _declared_database_fixtures(tree: ast.Module) -> frozenset[str] | None:
    """The fixture names :data:`CLASSIFIER_CONSTANT` designates, if it is assigned
    a literal set of strings at module level."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if CLASSIFIER_CONSTANT not in names:
            continue
        value = node.value
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        if not isinstance(value, ast.Set):
            return None
        literals = [e.value for e in value.elts if isinstance(e, ast.Constant)]
        if len(literals) != len(value.elts) or not all(isinstance(x, str) for x in literals):
            return None
        return frozenset(str(x) for x in literals)
    return None


def audit(tests_root: Path) -> list[Finding]:
    """Every violation under *tests_root*, addressed relative to it."""
    findings: list[Finding] = []
    allowed: tuple[int, int] | None = None

    entry_module = tests_root / ENTRY_POINT_MODULE
    if not entry_module.is_file():
        findings.append(Finding(ENTRY_POINT_MODULE, 0, f"{ENTRY_POINT_MODULE} does not exist"))
    else:
        entry_tree = ast.parse(entry_module.read_text(encoding="utf-8"))
        allowed = _entry_point_span(entry_tree, ENTRY_POINT_FIXTURE)
        if allowed is None:
            findings.append(
                Finding(
                    ENTRY_POINT_MODULE,
                    0,
                    f"the designated database fixture `{ENTRY_POINT_FIXTURE}` is not defined here",
                )
            )
        declared = _declared_database_fixtures(entry_tree)
        if declared != frozenset({ENTRY_POINT_FIXTURE}):
            findings.append(
                Finding(
                    ENTRY_POINT_MODULE,
                    0,
                    f"`{CLASSIFIER_CONSTANT}` must designate exactly "
                    f"{{{ENTRY_POINT_FIXTURE!r}}}, the fixture this guard permits; "
                    f"it reads {declared if declared is not None else 'a non-literal set'}",
                )
            )

    for path in sorted(tests_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(tests_root).as_posix()
        for line, target in seam_calls(ast.parse(path.read_text(encoding="utf-8"))):
            if relative == ENTRY_POINT_MODULE and allowed and allowed[0] <= line <= allowed[1]:
                continue
            findings.append(
                Finding(
                    relative,
                    line,
                    f"calls `{target}`, which acquires a live database; only the "
                    f"`{ENTRY_POINT_FIXTURE}` fixture in {ENTRY_POINT_MODULE} may",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live database access is fixture-only.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify every live database acquisition goes through the designated fixture (default)",
    )
    parser.parse_args(argv)

    stale = unresolved_seams()
    findings = audit(TESTS_ROOT)
    if not stale and not findings:
        print(f"{_TOOL}: live database access is confined to `{ENTRY_POINT_FIXTURE}`")
        return 0

    if stale:
        print(
            f"{_TOOL}: {len(stale)} declared seam(s) name nothing importable. A seam\n"
            "  that resolves to nothing guards nothing, and the call-site audit reports\n"
            "  a clean tree either way.",
            file=sys.stderr,
        )
        for seam in stale:
            print(f"    {seam}", file=sys.stderr)
    if findings:
        print(
            f"{_TOOL}: live database access outside the designated fixture. Each\n"
            "  collected item's scheduling class is derived from its fixture closure, so an\n"
            "  item reaching a database another way is selected by `-m dbfree`.",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"    tests/{finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
