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
module's functions AND over those of every first-party module it imports; a name
bound to another name — by ``import ... as``, by assignment of any shape, by a
walrus, or to the string that spells it — is resolved back to the one it stands
for; and a reader is reached both where it is CALLED, at either end of a dot or
through the string handed to a ``getattr``, and where it is merely HANDED
somewhere, since ``partial(retained)`` and ``stack.callback(retained)`` name no
call site at all. That second half is why a name the surrounding code binds
itself is excluded from it: the tree holds locals spelled exactly like readers,
and a rule that cannot tell them apart is one that has to be turned off.

**Import-time code is inside the rule, and cannot be decorated out of it.** A
test module's module-level statements and a class body's run during collection,
in the process the whole suite shares, and so does every module-level statement
of anything the module imports — so a reading taken there is the failure this
tool exists to catch, in the one place no ``@in_a_child_interpreter`` can be
written. It is therefore a finding on sight rather than a reachability question
about some test. The one exclusion is the ``__main__`` block, which runs only in
a child that the boundary itself started, and a function's body, which runs when
something calls it and is resolved through the call graph instead.

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


def _string(node: ast.expr) -> str | None:
    """The string *node* is, or ``None`` where it is not one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _renamings(tree: ast.Module) -> dict[str, str]:
    """Every local name in *tree* that stands for another name.

    ``from memory_instruments import retained as size`` and ``size = retained``
    both leave a reader reachable under a name the reader does not have, which is
    the one way a call-spelling rule fails silently: the call still reads the
    whole interpreter and the guard sees a name it has never heard of. Both
    spellings are therefore resolved back, transitively, so a chain of renames
    answers the reader at the end of it.

    Every shape a binding comes in is read, because which one a module happens to
    write is not a fact about what it requires: a bare assignment, an annotated
    one, a tuple unpacked from a tuple, and a walrus all bind the same way. Import
    renames are collected from anywhere in the module and bindings from anywhere
    in it too, because a local rebinding inside a helper hides a reader exactly as
    well as a module-level one.
    """
    direct: dict[str, str] = {}

    def bind(target: ast.expr, value: ast.expr) -> None:
        if isinstance(target, ast.Tuple | ast.List) and isinstance(value, ast.Tuple | ast.List):
            for element, bound in zip(target.elts, value.elts, strict=False):
                bind(element, bound)
        elif isinstance(target, ast.Name) and isinstance(value, ast.Name):
            direct[target.id] = value.id
        elif isinstance(target, ast.Name) and isinstance(value, ast.Attribute):
            direct[target.id] = value.attr
        elif isinstance(target, ast.Name) and (spelled := _string(value)) is not None:
            direct[target.id] = spelled

    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    direct[alias.asname] = alias.name.rsplit(".", maxsplit=1)[-1]
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target, node.value)
        elif isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value is not None:
            bind(node.target, node.value)

    def resolved(name: str, walking: frozenset[str]) -> str:
        stands_for = direct.get(name)
        if stands_for is None or name in walking:
            return name
        return resolved(stands_for, walking | {name})

    return {name: resolved(name, frozenset()) for name in direct}


def _spelled(node: ast.AST) -> set[str]:
    """Every name *node* itself names as something to reach, ignoring its children.

    **Handing a reader somewhere is reaching it, whoever calls it in the end.**
    Enumerating the shapes a call comes in is what a spelling rule cannot finish —
    ``retained(...)`` is one, and ``getattr(module, "retained")()``,
    ``partial(retained)()``, ``ExitStack().callback(retained)`` and every wrapper
    not yet written are others — so the rule is not over call shapes. A name in
    CALLEE position is reached, and so is a name an expression hands to a call,
    positionally or by keyword, whether that call runs it, stores it or wraps it.
    What no rule over source can see is a name assembled at run time out of pieces
    that are not the name, and :func:`_bound_names` is what keeps the widened half
    from firing on a local that merely shares a reader's spelling.

    A string is a name too where a string is how a name is spelled — handed to a
    call, or used as a subscript key — because that is what ``getattr`` and
    ``globals()[...]`` take. The rule over-reports a string nobody meant as a
    name, which is the direction this guard declares for.
    """
    if isinstance(node, ast.Call):
        handed = (_string(argument) for argument in _handed(node))
        return _callee_names(node.func) | {name for name in handed if name is not None}
    if isinstance(node, ast.Subscript):
        key = _string(node.slice)
        return {key} if key is not None else set()
    return set()


def _handed(node: ast.Call) -> tuple[ast.expr, ...]:
    """Every expression *node* hands its callee, positionally or by keyword."""
    return (*node.args, *(keyword.value for keyword in node.keywords))


def _passed(node: ast.AST, bound: frozenset[str], renamings: Mapping[str, str]) -> set[str]:
    """Every name *node* hands to a call and does not bind itself.

    ``bound`` is what makes this half of the rule usable: a name-based rule cannot
    tell ``retained`` the instrument from ``retained`` the local a test happens to
    build and pass on, and the tree holds both. A name the code itself binds is
    not the reader of that name — unless the binding is exactly what makes it one,
    which is what ``renamings`` holds, so ``name = "retained"`` followed by
    ``getattr(module, name)`` still resolves.
    """
    if not isinstance(node, ast.Call):
        return set()
    return {
        argument.id
        for argument in _handed(node)
        if isinstance(argument, ast.Name) and (argument.id not in bound or argument.id in renamings)
    }


def _bound_names(node: ast.AST) -> frozenset[str]:
    """Every name *node* binds itself, which is therefore its own rather than the
    module-level reader spelled the same way.

    Imports are deliberately absent: an import is how a reader's name ARRIVES in a
    module, not how it is shadowed, so treating one as a binding would shadow
    every reader from itself.
    """
    bound: set[str] = set()
    for each in ast.walk(node):
        if isinstance(each, ast.Name) and isinstance(each.ctx, ast.Store):
            bound.add(each.id)
        elif isinstance(each, ast.arg):
            bound.add(each.arg)
        elif isinstance(each, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            bound.add(each.name)
        elif isinstance(each, ast.ExceptHandler):
            bound |= {each.name} if each.name is not None else set()
    return frozenset(bound)


def _callee_names(func: ast.expr) -> set[str]:
    """What a call expression names as its callee."""
    if isinstance(func, ast.Name):
        return {func.id}
    if isinstance(func, ast.Attribute):
        return {func.attr}
    if isinstance(func, ast.NamedExpr):
        return _callee_names(func.value)
    return set()


def _called_names(node: ast.AST, renamings: Mapping[str, str]) -> set[str]:
    """Every name *node* or anything under it reaches, resolved through renames.

    ``report.retained(...)``, ``retained(...)`` and ``size(...)`` after
    ``import retained as size`` all reach the same reading, and which one a test
    writes is a consequence of how it imported rather than of what it requires."""
    bound = _bound_names(node)
    spelled: set[str] = set()
    for each in ast.walk(node):
        spelled |= _spelled(each) | _passed(each, bound, renamings)
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


def _call_graph(tree: ast.Module, reached: Sequence[ast.Module]) -> dict[str, set[str]]:
    """What every function of *tree* and of *reached* calls, by name.

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
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                calls.setdefault(node.name, set()).update(_called_names(node, renamings))
    return calls


def _readers_through(calls: Mapping[str, set[str]]) -> Callable[[Iterable[str]], frozenset[str]]:
    """Which readers a set of spelled names reaches, following *calls* onwards.

    One resolver per call graph rather than one per question, so a helper deep in
    a chain is walked once however many tests reach it.
    """
    functions = frozenset(calls)
    resolved: dict[str, frozenset[str]] = {}

    def onwards(spelled: Iterable[str], walking: frozenset[str]) -> frozenset[str]:
        found = set(spelled) & WHOLE_INTERPRETER_READERS
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


def _import_time(node: ast.AST) -> Iterator[ast.AST]:
    """Every node under *node* that runs when its module is imported.

    A function's body is not import-time code — it runs when something calls it,
    which the call graph answers — but everything a ``def`` evaluates to make the
    function is: its decorators, its parameter defaults and annotations, its
    return annotation and its type parameters. A lambda is the same shape with no
    body to exclude by name, so its defaults are read and its body is not. Every
    statement of a class body runs at import too. The ``__main__`` block is the
    one exclusion, because it runs only in a child the boundary itself started.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            evaluated = (*child.decorator_list, child.args, *child.type_params)
            yield from _each(*evaluated, *((child.returns,) if child.returns else ()))
            continue
        if isinstance(child, ast.Lambda):
            yield from _each(child.args)
            continue
        if _main_guard(child):
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
    renamings = _renamings(tree)
    bound = _bound_names(tree)
    findings: list[Finding] = []
    for node in _import_time(tree):
        reached = readers(_shallow(node, bound, renamings))
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


def _shallow(node: ast.AST, bound: frozenset[str], renamings: Mapping[str, str]) -> set[str]:
    """What *node* itself spells, without descending into anything under it."""
    spelled = _spelled(node) | _passed(node, bound, renamings)
    return {renamings.get(name, name) for name in spelled}


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
    holds the routes it is meant to catch. A guard nothing plants against is a
    guard whose next widening is checked by hand, which is how each of the last
    three left a hole behind it.
    """
    findings: list[Finding] = []
    at_import: dict[Path, list[Finding]] = {}
    for path in sorted(root.rglob("test_*.py")):
        tree = ast.parse(path.read_text())
        relative = _reported(path, root)
        files = _imported_files(tree, {path.resolve()})
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
