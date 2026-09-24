"""Fail when a test calls a whole-interpreter reader without acquiring an
interpreter of its own.

Each collected item's scheduling class is derived from what it requires
(``tests/conftest.py``), so a test calling a reader without the boundary below is
classified ``dbfree`` while needing an interpreter no other test shares.

**The rule is over direct calls.** A ``test_*`` function that calls a reader —
by the name it was imported under from ``memory_instruments``, or as an attribute
of that module — must carry ``@in_a_child_interpreter``. Every other route is
answered where the reading is taken: each reader refuses to run in a process the
boundary did not start, so a test reaching one through a helper, a wrapper, or
import-time code fails in the shared process instead of passing against its heap.

A module holding a boundary must also answer ``serve_one_measurement`` from its
``__main__``; otherwise its child imports the module, serves nothing, and exits
cleanly.

Three structural facts are checked with it, because the rule is vacuous without
them: every declared reader must still name a function the instruments define,
the boundary must exist, and the classifier's own attribute must be spelled the
way the instruments set it.

Usage
-----
* ``python tools/check_instrument_access.py``          check (default)
* ``python tools/check_instrument_access.py --check``  check (explicit)

Same ``--check``/exit-1 contract as ``tools/check_database_access.py``: it never
mutates anything and exits non-zero on any finding.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypeIs

_TOOL = "tools/check_instrument_access.py"
WORKSPACE = Path(__file__).resolve().parents[1]
TESTS_ROOT = WORKSPACE / "tests"
INSTRUMENTS = TESTS_ROOT / "unit" / "memory_instruments.py"
CONFTEST = TESTS_ROOT / "conftest.py"

INSTRUMENT_MODULE_NAME = "memory_instruments"

BOUNDARY = "in_a_child_interpreter"
"""The decorator that acquires an interpreter of its own for one measurement."""

SERVER = "serve_one_measurement"
"""What a module holding a measurement answers from its ``__main__``."""

ATTRIBUTE_CONSTANT = "OWN_INTERPRETER_ATTRIBUTE"
CLASSIFIER_CONSTANT = "_OWN_INTERPRETER_ATTRIBUTE"

# The instruments whose reading is taken over the whole process: the two survivor
# samples and the two whole-heap censuses list every tracked object, and the four
# byte readings each collect the whole heap and read a tracer the whole process
# shares.
WHOLE_INTERPRETER_READERS: frozenset[str] = frozenset(
    {
        "allocation",
        "first_run",
        "high_water",
        "live_graph",
        "retained",
        "survivors",
        "whole_heap",
        "whole_heap_across",
    }
)

type _Function = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class Finding:
    """One violation, addressed the way an editor jumps to it."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _constant(tree: ast.Module, name: str) -> str | None:
    """The string a module-level ``name = "..."`` assignment binds."""
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        for target in targets:
            named = isinstance(target, ast.Name) and target.id == name
            if named and isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
    return None


def _decorated(function: _Function) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == BOUNDARY
        for decorator in function.decorator_list
    )


def _instrument_bindings(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """The names *tree*'s imports bind to a reader, mapped to that reader, and the
    dotted names they bind to the instruments module itself."""
    readers: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            from_instruments = (node.module or "").rsplit(".", maxsplit=1)[-1]
            for alias in node.names:
                if from_instruments == INSTRUMENT_MODULE_NAME:
                    if alias.name in WHOLE_INTERPRETER_READERS:
                        readers[alias.asname or alias.name] = alias.name
                elif alias.name == INSTRUMENT_MODULE_NAME:
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.rsplit(".", maxsplit=1)[-1] == INSTRUMENT_MODULE_NAME:
                    modules.add(alias.asname or alias.name)
    return readers, modules


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted(node.value)
        return None if owner is None else f"{owner}.{node.attr}"
    return None


def _called_readers(function: _Function, readers: dict[str, str], modules: set[str]) -> set[str]:
    """Every reader *function* calls directly, by an imported name or off the
    instruments module."""
    called: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id in readers:
            called.add(readers[callee.id])
        elif (
            isinstance(callee, ast.Attribute)
            and callee.attr in WHOLE_INTERPRETER_READERS
            and _dotted(callee.value) in modules
        ):
            called.add(callee.attr)
    return called


def _main_guard(node: ast.stmt) -> TypeIs[ast.If]:
    """Whether *node* is ``if __name__ == "__main__":`` exactly, the one spelling
    whose body runs in the child the boundary starts and nowhere else."""
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    named = isinstance(test.left, ast.Name) and test.left.id == "__name__"
    compared = len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
    main = test.comparators[0]
    return named and compared and isinstance(main, ast.Constant) and main.value == "__main__"


def _serves(tree: ast.Module, modules: set[str]) -> bool:
    """Whether *tree*'s ``__main__`` block calls the server, by name or off the
    instruments module."""
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == SERVER)
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == SERVER
                and _dotted(node.func.value) in modules
            )
        )
        for guard in tree.body
        if _main_guard(guard)
        for statement in guard.body
        for node in ast.walk(statement)
    )


def _check_structure() -> list[Finding]:
    """The three facts the rule rests on."""
    findings: list[Finding] = []
    instruments = ast.parse(INSTRUMENTS.read_text())
    defined = {
        node.name
        for node in ast.walk(instruments)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    for name in sorted(WHOLE_INTERPRETER_READERS | {BOUNDARY, SERVER}):
        if name not in defined:
            findings.append(
                Finding(
                    str(INSTRUMENTS.relative_to(TESTS_ROOT.parent)),
                    1,
                    f"`{_TOOL}` names `{name}`, which this module no longer defines",
                )
            )
    declared = _constant(instruments, ATTRIBUTE_CONSTANT)
    classifier = _constant(ast.parse(CONFTEST.read_text()), CLASSIFIER_CONSTANT)
    if declared is None or classifier is None or declared != classifier:
        findings.append(
            Finding(
                str(CONFTEST.relative_to(TESTS_ROOT.parent)),
                1,
                f"the classifier's `{CLASSIFIER_CONSTANT}` ({classifier!r}) and the "
                f"instruments' `{ATTRIBUTE_CONSTANT}` ({declared!r}) must be the same "
                f"attribute; the runner reads what the boundary sets",
            )
        )
    return findings


def audit(root: Path) -> list[Finding]:
    """Every finding the direct-call rule raises over the test modules under
    *root*, which a scratch tree can stand in for."""
    findings: list[Finding] = []
    for path in sorted(root.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        relative = str(path.relative_to(root.parent))
        readers, modules = _instrument_bindings(tree)
        functions = sorted(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            ),
            key=lambda node: node.lineno,
        )
        for node in functions:
            if not node.name.startswith("test_") or _decorated(node):
                continue
            called = _called_readers(node, readers, modules)
            if called:
                findings.append(
                    Finding(
                        relative,
                        node.lineno,
                        f"`{node.name}` calls {', '.join(sorted(called))} and carries no "
                        f"`@{BOUNDARY}`, so it reads the whole interpreter in a process the "
                        f"rest of the suite shares",
                    )
                )
        if any(_decorated(node) for node in functions) and not _serves(tree, modules):
            findings.append(
                Finding(
                    relative,
                    1,
                    f"this module holds a `@{BOUNDARY}` measurement but its "
                    f'`if __name__ == "__main__":` block never calls `{SERVER}`, so the '
                    f"child it starts can serve nothing",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check (the only mode)")
    parser.parse_args(argv)
    findings = _check_structure() + audit(TESTS_ROOT)
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"{_TOOL}: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print(f"{_TOOL}: whole-interpreter readers are called only under `{BOUNDARY}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
