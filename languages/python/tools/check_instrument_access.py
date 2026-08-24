"""Fail when a test reads the whole interpreter without acquiring one of its own.

Each collected item's scheduling class is derived from what it requires
(``tests/conftest.py``), so an item that reads the whole process without the
boundary below is classified ``dbfree`` while needing an interpreter no other
test shares. That failure is silent rather than loud: the reading still happens
and still passes, taken against a heap the rest of the suite decided the size of
and a floor that moves with it, so ``dbfree`` stops being true of what it selects
and the reading stops being a property of its own subject.

The rule is reachability, not a call site. A test reaching a reader through its
own helpers requires the resource exactly as much as one calling it directly, and
the suites here wrap every reading in helpers. Module-level code is outside the
rule: the ``__main__`` block runs only in a child that the boundary itself
started.

Three structural facts are checked with it, because the rule is vacuous without
them: every declared reader must still name a callable the instruments export,
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

_TOOL = "tools/check_instrument_access.py"
TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"
INSTRUMENTS = TESTS_ROOT / "unit" / "memory_instruments.py"
CONFTEST = TESTS_ROOT / "conftest.py"

BOUNDARY = "in_a_child_interpreter"
"""The decorator that acquires an interpreter of its own for one measurement."""

SERVER = "serve_one_measurement"
"""What a module holding a measurement answers from its ``__main__``."""

ATTRIBUTE_CONSTANT = "OWN_INTERPRETER_ATTRIBUTE"
CLASSIFIER_CONSTANT = "_OWN_INTERPRETER_ATTRIBUTE"

# The instruments whose reading is taken over the whole process: the two survivor
# samples list every tracked object, and the three byte readings each collect the
# whole heap. `closure` is deliberately absent — it walks outwards from one object
# and reaches only what that object holds, so its cost and its answer are the
# measured structure's alone.
WHOLE_INTERPRETER_READERS: frozenset[str] = frozenset(
    {"allocation", "first_run", "live_graph", "retained", "survivors"}
)


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


def _decorated(function: ast.FunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == BOUNDARY
        for decorator in function.decorator_list
    )


def _reaching_tests(tree: ast.Module) -> list[tuple[ast.FunctionDef, frozenset[str]]]:
    """Each ``test_*`` in *tree* that reaches a reader, and which ones it reaches.

    Reachability is resolved over the module's own functions, which is where its
    helpers live: a test calling a helper that calls a reader requires the
    resource as much as one calling the reader itself.
    """
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    calls = {
        name: {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        }
        for name, node in functions.items()
    }
    resolved: dict[str, frozenset[str]] = {}

    def reaches(name: str, walking: frozenset[str]) -> frozenset[str]:
        if name in resolved:
            return resolved[name]
        if name in walking:
            return frozenset()
        found = calls.get(name, set()) & WHOLE_INTERPRETER_READERS
        for callee in calls.get(name, set()):
            if callee in functions:
                found |= reaches(callee, walking | {name})
        answer = frozenset(found)
        resolved[name] = answer
        return answer

    return [
        (node, reaches(name, frozenset()))
        for name, node in sorted(functions.items())
        if name.startswith("test_") and reaches(name, frozenset())
    ]


def _check_structure() -> list[Finding]:
    """The three facts the rule rests on."""
    findings: list[Finding] = []
    instruments = ast.parse(INSTRUMENTS.read_text())
    exported = {node.name for node in ast.walk(instruments) if isinstance(node, ast.FunctionDef)}
    for reader in sorted(WHOLE_INTERPRETER_READERS | {BOUNDARY, SERVER}):
        if reader not in exported:
            findings.append(
                Finding(
                    str(INSTRUMENTS.relative_to(TESTS_ROOT.parent)),
                    1,
                    f"`{_TOOL}` names `{reader}`, which this module no longer defines",
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


def _check_tree() -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        relative = str(path.relative_to(TESTS_ROOT.parent))
        reaching = _reaching_tests(tree)
        undecorated = [(node, readers) for node, readers in reaching if not _decorated(node)]
        for node, readers in undecorated:
            findings.append(
                Finding(
                    relative,
                    node.lineno,
                    f"`{node.name}` reaches {', '.join(sorted(readers))} and carries no "
                    f"`@{BOUNDARY}`, so it reads the whole interpreter in a process the "
                    f"rest of the suite shares",
                )
            )
        if reaching and any(_decorated(node) for node, _ in reaching):
            served = any(
                isinstance(call.func, ast.Name) and call.func.id == SERVER
                for call in ast.walk(tree)
                if isinstance(call, ast.Call)
            )
            if not served:
                findings.append(
                    Finding(
                        relative,
                        1,
                        f"this module holds a `@{BOUNDARY}` measurement but never calls "
                        f"`{SERVER}`, so the child it starts can serve nothing",
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check (the only mode)")
    parser.parse_args(argv)
    findings = _check_structure() + _check_tree()
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"{_TOOL}: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print(f"{_TOOL}: whole-interpreter readings are confined to `{BOUNDARY}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
