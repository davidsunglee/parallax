"""Fail when a test reads the whole interpreter without acquiring one of its own.

Each collected item's scheduling class is derived from what it requires
(``tests/conftest.py``), so an item that reads the whole process without the
boundary below is classified ``dbfree`` while needing an interpreter no other
test shares. That failure is silent rather than loud: the reading still happens
and still passes, taken against a heap the rest of the suite decided the size of
and a floor that moves with it, so ``dbfree`` stops being true of what it selects
and the reading stops being a property of its own subject.

The rule is reachability, not a call site, and not a spelling either. A test
reaching a reader through its own helpers requires the resource exactly as much
as one calling it directly, and the suites here wrap every reading in helpers; a
test reaching one through a module it imported requires it exactly as much again,
whether it names the reader bare or as an attribute of whatever it imported, and
whether or not it renamed it on the way. So reachability is resolved over the test
module's functions AND over those of every first-party module it imports, a call
is matched by the name it spells at either end of a dot, and a name bound to
another name — by ``import ... as`` or by assignment — is resolved back to the one
it stands for. Module-level code is outside the rule: the ``__main__`` block runs
only in a child that the boundary itself started.

A spelling rule catches only the routes it was taught, so the modules a suite may
import are also kept free of readers structurally: `tools/instance_state_overhead`
imports no instrument at all and the reading it drives lives in a script nothing
imports.

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_TOOL = "tools/check_instrument_access.py"
TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"
TOOLS_ROOT = Path(__file__).resolve().parent
INSTRUMENTS = TESTS_ROOT / "unit" / "memory_instruments.py"
CONFTEST = TESTS_ROOT / "conftest.py"

FIRST_PARTY_ROOTS = (TESTS_ROOT, TOOLS_ROOT)
"""Where a module a test imports by bare name can be resolved to a file.

Both, because the two are one import namespace at run time: a suite reaches the
instruments and their support code by putting ``tests/unit`` on the path, and a
report under ``tools/`` does the same, so a test importing that report imports
whatever it holds."""

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


def _renamings(tree: ast.Module) -> dict[str, str]:
    """Every local name in *tree* that stands for another name.

    ``from memory_instruments import retained as size`` and ``size = retained``
    both leave a reader reachable under a name the reader does not have, which is
    the one way a call-spelling rule fails silently: the call still reads the
    whole interpreter and the guard sees a name it has never heard of. Both
    spellings are therefore resolved back, transitively, so a chain of renames
    answers the reader at the end of it.

    Import renames are collected from anywhere in the module and assignments from
    anywhere in it too, because a local rebinding inside a helper hides a reader
    exactly as well as a module-level one.
    """
    direct: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    direct[alias.asname] = alias.name.rsplit(".", maxsplit=1)[-1]
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    direct[target.id] = node.value.id
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Attribute):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    direct[target.id] = node.value.attr

    def resolved(name: str, walking: frozenset[str]) -> str:
        stands_for = direct.get(name)
        if stands_for is None or name in walking:
            return name
        return resolved(stands_for, walking | {name})

    return {name: resolved(name, frozenset()) for name in direct}


def _called_names(node: ast.AST, renamings: Mapping[str, str]) -> set[str]:
    """Every name *node* calls, whether spelled bare, after a dot, or renamed.

    ``report.retained(...)``, ``retained(...)`` and ``size(...)`` after
    ``import retained as size`` all reach the same reading, and which one a test
    writes is a consequence of how it imported rather than of what it requires."""
    spelled = {
        call.func.id if isinstance(call.func, ast.Name) else call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name | ast.Attribute)
    }
    return {renamings.get(name, name) for name in spelled}


def _imported_files(tree: ast.Module, seen: set[Path]) -> list[Path]:
    """Every first-party module *tree* imports, transitively, as its own file.

    Resolved under :data:`FIRST_PARTY_ROOTS` — by bare module name, which is how
    these modules are imported at run time, and by dotted path, so a module
    reached as ``unit.memory_instruments`` is the same file as one reached bare
    and neither spelling is a way past the rule.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    found: list[Path] = []
    for name in sorted(names):
        candidates: list[Path] = []
        for root in FIRST_PARTY_ROOTS:
            if "." in name:
                dotted = root.joinpath(*name.split(".")).with_suffix(".py")
                candidates += [dotted] if dotted.is_file() else []
            else:
                candidates += sorted(root.rglob(f"{name}.py"))
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            found += [path, *_imported_files(ast.parse(path.read_text()), seen)]
    return found


def _reaching_tests(
    tree: ast.Module, reached: Sequence[ast.Module]
) -> list[tuple[ast.FunctionDef, frozenset[str]]]:
    """Each ``test_*`` in *tree* that reaches a reader, and which ones it reaches.

    Reachability is resolved over the module's own functions and over those of
    every module in *reached*, which is where its helpers live: a test calling a
    helper that calls a reader requires the resource as much as one calling the
    reader itself, and the helper is as often a function inside an imported
    module as one beside the test.

    Two functions sharing a name are one entry whose calls are the UNION of
    theirs, because a bare name is all a call site gives: picking one of them
    would let a same-named function in another module hide a reader, and a guard
    that misses is worse than one that over-reports a helper nobody wrote.
    Renamings are resolved per module, since which name stands for a reader is a
    fact about the file that spells it.
    """
    calls: dict[str, set[str]] = {}
    for module in (tree, *reached):
        renamings = _renamings(module)
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef):
                calls.setdefault(node.name, set()).update(_called_names(node, renamings))
    functions = frozenset(calls)
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

    own = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    return [
        (node, reaches(node.name, frozenset()))
        for node in sorted(own, key=lambda node: node.name)
        if reaches(node.name, frozenset())
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
        imported = [ast.parse(each.read_text()) for each in _imported_files(tree, {path.resolve()})]
        reaching = _reaching_tests(tree, imported)
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
            served = SERVER in _called_names(tree, _renamings(tree))
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
