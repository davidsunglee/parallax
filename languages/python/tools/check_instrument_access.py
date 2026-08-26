"""Fail when a test reads the whole interpreter without acquiring one of its own.

Each collected item's scheduling class is derived from what it requires
(``tests/conftest.py``), so an item that reads the whole process without the
boundary below is classified ``dbfree`` while needing an interpreter no other
test shares. That failure is silent rather than loud: the reading still happens
and still passes, taken against a heap the rest of the suite decided the size of
and a floor that moves with it, so ``dbfree`` stops being true of what it selects
and the reading stops being a property of its own subject.

**The rule is over what a module IMPORTED, not over how it spells a call.** A
reader is a function object, and the only way one enters a module is an import of
it or of the module defining it; nothing a source file writes can produce one
otherwise. So each module is first asked which of its OWN names hold a reader —
whatever ``from memory_instruments import retained as size`` and ``import
memory_instruments as m`` happen to bind — and a function reaches a reader when it
MENTIONS one of those names anywhere, in any position: called, handed to a
wrapper, returned, packed into a tuple, taken off a dot, or named by the string a
``getattr`` takes. No enumeration of call shapes can leave a shape out, because
there is none.

That import gate is what makes a mention rule usable. Reader names are ordinary
English words and the suites are full of locals spelled like them; a rule over
bare spellings fires on all of them. A module that never imported the instruments
holds no reader whatever it spells, so its mentions are not reads — and inside a
module that did, a local rebinding one of the names it imported is reported, which
is the direction this guard declares for.

Reachability is then resolved over the test module's functions AND over those of
every first-party module it imports, since a test reaching a reader through a
helper requires the resource exactly as much as one calling it directly, and the
suites here wrap every reading in helpers.

**Import-time code is inside the rule, and cannot be decorated out of it.** A
test module's module-level statements and a class body's run during collection,
in the process the whole suite shares, and so does every module-level statement
of anything the module imports — so a reading taken there is the failure this
tool exists to catch, in the one place no ``@in_a_child_interpreter`` can be
written. It is therefore a finding on sight rather than a reachability question
about some test. A function's body is outside it — that runs when something calls
it, and is resolved through the call graph instead — as is the ``__main__`` block,
which runs only in a child the boundary itself started, and an ``__all__``
assignment, which declares a surface rather than reaching one.

A guard can only answer for the modules it is pointed at, so the modules a suite
may import are also kept free of readers structurally:
`tools/instance_state_overhead` imports no instrument at all and the reading it
drives lives in a script nothing imports.

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
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
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


def _decorated(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id == BOUNDARY
        for decorator in function.decorator_list
    )


INSTRUMENT_MODULE_NAME = "memory_instruments"
"""The module every whole-interpreter reader is defined in and imported from."""

READER_TOKENS: frozenset[str] = WHOLE_INTERPRETER_READERS | {INSTRUMENT_MODULE_NAME}
"""What reaching one of them is reported as: a reader, or the module they hang off."""


def _reader_names(tree: ast.Module) -> dict[str, str]:
    """Every name *tree* binds that holds a reader, mapped to what it holds.

    The whole predicate rests here rather than on how a call is written.
    ``from memory_instruments import retained as size`` binds a reader under
    ``size``; a star import binds all of them; ``import memory_instruments as m``
    binds the module every reader can be taken off, so ``m`` itself stands for one;
    and a module that DEFINES a reader holds it under that name, which is what
    keeps the instruments' own helpers inside the rule. Which module an imported
    name came from is not checked, so a first-party re-export is caught with no
    special case — nothing outside these suites exports a callable spelled like a
    reader, and reporting one that did is the direction this guard declares for.

    Collected from anywhere in the module, since an import inside a function binds
    a reader exactly as well as one at the top.
    """
    held: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            from_instruments = (node.module or "").rsplit(".", maxsplit=1)[-1]
            for alias in node.names:
                if alias.name in WHOLE_INTERPRETER_READERS:
                    held[alias.asname or alias.name] = alias.name
                elif alias.name == "*" and from_instruments == INSTRUMENT_MODULE_NAME:
                    held.update({reader: reader for reader in WHOLE_INTERPRETER_READERS})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.rsplit(".", maxsplit=1)[-1] == INSTRUMENT_MODULE_NAME:
                    held[alias.asname or alias.name.split(".")[0]] = INSTRUMENT_MODULE_NAME
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name in WHOLE_INTERPRETER_READERS:
                held[node.name] = node.name
    return held


def _spelled_by(node: ast.AST) -> Iterator[str]:
    """The name *node* itself spells, without descending into anything under it.

    Three shapes and no fourth, because a name in source is only ever written
    bare, at the end of a dot, or as the string something spells it with — which
    is what ``getattr(module, "retained")`` and ``globals()["retained"]`` take.

    A name being BOUND is not one being reached: ``retained = Observation()``
    shadows the reader rather than reading it, and the right-hand side of any
    binding that does reach one is read on its own.
    """
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, ast.Load):
            yield node.id
    elif isinstance(node, ast.Attribute):
        yield node.attr
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value


def _resolved(names: Iterable[str], held: Mapping[str, str]) -> set[str]:
    """*names* with the ones *held* binds read as the reader they hold.

    A name spelled like a reader that its module never imported and does not
    define is dropped rather than reported: the module holds no such object, so
    the name is its own. That is the gate the mention rule needs to be usable —
    reader names are ordinary English words and the suites are full of locals
    spelled like them.
    """
    resolved: set[str] = set()
    for name in names:
        if name in held:
            resolved.add(held[name])
        elif name not in READER_TOKENS:
            resolved.add(name)
    return resolved


def _mentioned(node: ast.AST, held: Mapping[str, str]) -> set[str]:
    """Every name *node* or anything under it mentions, resolved through *held*.

    Position is not consulted at all. A reader called, handed to ``partial``,
    returned from a helper, packed into a tuple, taken off a dot or named by a
    string is mentioned by the code that does it, and mentioning one is reaching
    it — whoever calls it in the end.
    """
    return _resolved(
        (name for each in ast.walk(node) for name in _spelled_by(each)),
        held,
    )


def _imported_files(tree: ast.Module, roots: Sequence[Path], seen: set[Path]) -> list[Path]:
    """Every module *tree* imports from *roots*, transitively, as its own file.

    Resolved by bare module name, which is how these modules are imported at run
    time, and by dotted path, so a module reached as ``unit.memory_instruments``
    is the same file as one reached bare and neither spelling is a way past the
    rule. *roots* rather than :data:`FIRST_PARTY_ROOTS` alone so an audited tree
    resolves its OWN helper modules: a rule about what a test reaches through a
    module it imported is untestable over a tree whose imports resolve elsewhere.
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
        for root in roots:
            if "." in name:
                dotted = root.joinpath(*name.split(".")).with_suffix(".py")
                candidates += [dotted] if dotted.is_file() else []
            else:
                candidates += sorted(root.rglob(f"{name}.py"))
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            found += [path, *_imported_files(ast.parse(path.read_text()), roots, seen)]
    return found


def _call_graph(tree: ast.Module, reached: Sequence[ast.Module]) -> dict[str, set[str]]:
    """What every function of *tree* and of *reached* calls, by name.

    Two functions sharing a name are one entry whose calls are the UNION of
    theirs, because a bare name is all a call site gives: picking one of them
    would let a same-named function in another module hide a reader, and a guard
    that misses is worse than one that over-reports a helper nobody wrote. Which
    names hold a reader is asked per module, since that is a fact about the file
    whose imports bind them.
    """
    calls: dict[str, set[str]] = {}
    for module in (tree, *reached):
        held = _reader_names(module)
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                calls.setdefault(node.name, set()).update(_mentioned(node, held))
    return calls


def _readers_through(calls: Mapping[str, set[str]]) -> Callable[[Iterable[str]], frozenset[str]]:
    """Which readers a set of mentioned names reaches, following *calls* onwards.

    One resolver per call graph rather than one per question, so a helper deep in
    a chain is walked once however many tests reach it.
    """
    functions = frozenset(calls)
    resolved: dict[str, frozenset[str]] = {}

    def onwards(spelled: Iterable[str], walking: frozenset[str]) -> frozenset[str]:
        found = set(spelled) & READER_TOKENS
        for callee in spelled:
            if callee in functions:
                found |= through(callee, walking)
        return frozenset(found)

    def through(name: str, walking: frozenset[str]) -> frozenset[str]:
        if name in resolved:
            return resolved[name]
        if name in walking:
            return frozenset()
        answer = onwards(calls.get(name, set()), walking | {name})
        resolved[name] = answer
        return answer

    return lambda spelled: onwards(spelled, frozenset())


def _reaching_tests(
    tree: ast.Module, reached: Sequence[ast.Module]
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, frozenset[str]]]:
    """Each ``test_*`` in *tree* that reaches a reader, and which ones it reaches.

    Reachability is resolved over the module's own functions and over those of
    every module in *reached*, which is where its helpers live: a test calling a
    helper that calls a reader requires the resource as much as one calling the
    reader itself, and the helper is as often a function inside an imported
    module as one beside the test.
    """
    calls = _call_graph(tree, reached)
    readers = _readers_through(calls)
    own = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]
    return [
        (node, readers(calls.get(node.name, set())))
        for node in sorted(own, key=lambda node: node.name)
        if readers(calls.get(node.name, set()))
    ]


def _main_guard(node: ast.AST) -> bool:
    """Whether *node* is the ``if __name__ == "__main__":`` block, exactly.

    Exactly, because this is the one exclusion from the import-time rule and
    every other test on ``__name__`` runs during collection: ``!=`` runs the
    branch in every process but the child, and a comparison against another
    string runs it in none. Anything but the one spelling is import-time code and
    is read as such.
    """
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    named = isinstance(left, ast.Name) and left.id == "__name__"
    return named and isinstance(right, ast.Constant) and right.value == "__main__"


def _export_list(node: ast.AST) -> bool:
    """Whether *node* is an ``__all__`` assignment.

    A module's export list spells the names it re-exports and reaches none of
    them: the strings there are a declaration about this module's own surface,
    where every other string spelling a reader is one something is about to look
    up.
    """
    if not isinstance(node, ast.Assign | ast.AnnAssign):
        return False
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets)


def _import_time(node: ast.AST) -> Iterator[ast.AST]:
    """Every node under *node* that runs when its module is imported.

    A function's body is not import-time code — it runs when something calls it,
    which the call graph answers — but everything a ``def`` evaluates to make the
    function is: its decorators, its parameter defaults and annotations, its
    return annotation and its type parameters. A lambda is the same shape with no
    body to exclude by name, so its defaults are read and its body is not. Every
    statement of a class body runs at import too. Two exclusions: the ``__main__``
    block, because it runs only in a child the boundary itself started, and an
    ``__all__`` assignment, which declares a surface rather than reaching one.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            evaluated = (*child.decorator_list, child.args, *child.type_params)
            yield from _each(*evaluated, *((child.returns,) if child.returns else ()))
            continue
        if isinstance(child, ast.Lambda):
            yield from _each(child.args)
            continue
        if _main_guard(child) or _export_list(child):
            continue
        yield child
        yield from _import_time(child)


def _each(*nodes: ast.AST) -> Iterator[ast.AST]:
    """*nodes* and everything under them that runs when their module is imported."""
    for node in nodes:
        yield node
        yield from _import_time(node)


def _reported(path: Path, root: Path) -> str:
    """*path* as an editor jumps to it, from whichever root it sits under."""
    for base in (root.parent, TESTS_ROOT.parent):
        if path.is_relative_to(base):
            return str(path.relative_to(base))
    return str(path)


def _reading_at_import(
    path: Path,
    tree: ast.Module,
    readers: Callable[[Iterable[str]], frozenset[str]],
    root: Path,
) -> list[Finding]:
    """Every import-time statement of *path* that reaches a reader.

    Reported at the statement rather than at the module, because there is no
    decorator to add and nothing to reclassify: the repair is to move the reading
    into a function the boundary can start a child for, and the line that has to
    move is the finding.
    """
    held = _reader_names(tree)
    findings: list[Finding] = []
    for node in _import_time(tree):
        reached = readers(_resolved(_spelled_by(node), held))
        if not reached:
            continue
        findings.append(
            Finding(
                _reported(path, root),
                getattr(node, "lineno", 1),
                f"this runs when the module is imported and reaches "
                f"{', '.join(sorted(reached))}, so it reads the whole interpreter during "
                f"collection, in the process the rest of the suite shares; no "
                f"`@{BOUNDARY}` can cover it",
            )
        )
    return findings


def _check_structure() -> list[Finding]:
    """The three facts the rule rests on."""
    findings: list[Finding] = []
    instruments = ast.parse(INSTRUMENTS.read_text())
    exported = {
        node.name
        for node in ast.walk(instruments)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
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


def audit(root: Path) -> list[Finding]:
    """Every finding the reachability rule raises over the test modules under
    *root*.

    Parameterized by root so the rule can be exercised over a scratch tree that
    holds the routes it is meant to catch, including the helper modules a test
    reaches a reader through: *root* is searched for imports ahead of
    :data:`FIRST_PARTY_ROOTS`, so a planted tree resolves its own.
    """
    findings: list[Finding] = []
    at_import: dict[Path, list[Finding]] = {}
    roots = (root, *(each for each in FIRST_PARTY_ROOTS if each != root))
    for path in sorted(root.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        relative = _reported(path, root)
        files = _imported_files(tree, roots, {path.resolve()})
        imported = [ast.parse(each.read_text()) for each in files]
        readers = _readers_through(_call_graph(tree, imported))
        for each, each_tree in zip((path, *files), (tree, *imported), strict=True):
            at_import.setdefault(each, _reading_at_import(each, each_tree, readers, root))
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
            served = SERVER in _mentioned(tree, _reader_names(tree))
            if not served:
                findings.append(
                    Finding(
                        relative,
                        1,
                        f"this module holds a `@{BOUNDARY}` measurement but never calls "
                        f"`{SERVER}`, so the child it starts can serve nothing",
                    )
                )
    for path in sorted(at_import):
        findings += at_import[path]
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
    print(f"{_TOOL}: whole-interpreter readings are confined to `{BOUNDARY}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
