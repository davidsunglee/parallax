"""Fail when a harness test can reach a live database outside its designated
fixture::

    uv run python -m reference_harness.check_database_access

Each collected item's scheduling class is derived from its fixture closure
(``tests/conftest.py``), so an item that acquires a database by any other route
is classified ``dbfree`` while needing a container. That failure is silent
rather than loud: CI runners have Docker, so the mis-classified item passes in
the database-free job instead of erroring, and ``dbfree`` stops being true of
what it selects.

The guard is a call-level rule, not an import-level one. Importing a provider
module is legitimate — the dialect and error-classification tests exercise its
pure functions — while *calling* one of the seams below boots a container. Each
call's target is resolved through the importing module's own bindings, so a
local name that merely looks like a seam is not one, and a seam reached under an
alias still is — including a local name the module first binds to a seam and
calls afterwards, through any of the forms that bind a name to an expression this
rule can read, a ``match`` capture as much as an assignment, however many names
the binding passed through, and through any container it was stored in and taken
back out of. A seam
a declared value reaches through a member rather than an importable name is
matched by that member's name on any receiver; this tree declares no such member.

The rule follows a value through this module's own bindings and stops at a call
boundary: a seam handed to a function or returned out of one is beyond it, because
deciding whether the callee calls it would take the whole program rather than one
syntax tree. Reporting an argument regardless would report the sites that hand a
seam over precisely to keep it from being constructed, which is the point where a
syntactic rule stops being able to tell the two apart.

Three structural facts are checked with it, because the rule is vacuous without
them: every declared seam must still name an importable callable, the designated
fixture must exist, and the classifier's own designated set must name exactly it.
"""

from __future__ import annotations

import ast
import importlib
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CLASSIFIER_CONSTANT",
    "CLASSIFIER_MODULE",
    "DATABASE_SEAMS",
    "ENTRY_POINT_FIXTURE",
    "ENTRY_POINT_MODULE",
    "SEAM_MEMBERS",
    "TESTS_ROOT",
    "Finding",
    "audit",
    "main",
    "seam_calls",
    "unresolved_seams",
]

TESTS_ROOT = Path(__file__).resolve().parents[2] / "tests"

ENTRY_POINT_MODULE = "test_compatibility.py"
ENTRY_POINT_FIXTURE = "provider"
CLASSIFIER_MODULE = "conftest.py"
CLASSIFIER_CONSTANT = "_DATABASE_FIXTURES"

# Fully qualified callables that acquire a live database. `provider_for` boots
# and tears down a container; the two container classes are the direct route to
# one; the two CLI entry points reach `provider_for` themselves.
DATABASE_SEAMS: frozenset[str] = frozenset(
    {
        "reference_harness.benchmark.main",
        "reference_harness.matrix.main",
        "reference_harness.providers.provider_for",
        "testcontainers.community.mysql.MySqlContainer",
        "testcontainers.community.postgres.PostgresContainer",
    }
)

# Members through which a declared value reaches one of the seams above, matched
# by name because such a call has no importable name of its own to resolve. Empty
# here: every acquisition in this tree is spelled as one of the seams above, and a
# member listed without a value declaring it would match calls that acquire
# nothing.
SEAM_MEMBERS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Finding:
    """One violation, addressed the way an editor jumps to it."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _imported_names(tree: ast.Module) -> dict[str, str]:
    """Map every name the module binds by import to the dotted path it names."""
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


def _acquisition_named(
    expression: ast.expr, bindings: dict[str, str], aliases: dict[str, str]
) -> str | None:
    """How *expression* is reported when it names an acquisition, else ``None``.

    An acquisition is named by a dotted path resolving to a declared seam, by a
    declared seam member — which has no importable name of its own for the dotted
    resolution to reach — by a plain name *aliases* already found to hold one, or by
    a container holding one, since storing an acquisition in a tuple, list, set, or
    dict and taking it back out is the same acquisition under a longer spelling. A
    container is reported by the first acquisition it holds rather than per element:
    the finding names what a call reaches, and one is enough to reach it.
    """
    if isinstance(expression, ast.Name) and expression.id in aliases:
        return aliases[expression.id]
    if isinstance(expression, ast.Attribute) and expression.attr in SEAM_MEMBERS:
        return f".{expression.attr}()"
    held: Sequence[ast.expr]
    if isinstance(expression, ast.Tuple | ast.List | ast.Set):
        held = expression.elts
    elif isinstance(expression, ast.Dict):
        held = expression.values
    elif isinstance(expression, ast.Subscript | ast.Starred):
        held = [expression.value]
    else:
        target = _resolved_target(expression, bindings)
        return target if target is not None and target in DATABASE_SEAMS else None
    for element in held:
        acquisition = _acquisition_named(element, bindings, aliases)
        if acquisition is not None:
            return acquisition
    return None


def _bound_names(target: ast.expr) -> list[str]:
    """Every plain name *target* binds, destructuring as far as the syntax goes.

    A name inside a tuple, list, or star pattern is bound to a part of the value
    rather than to the whole, which the rule cannot tell apart, so it binds all of
    them: a value holding an acquisition is one wherever it is unpacked to.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Starred):
        return _bound_names(target.value)
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in _bound_names(element)]
    return []


def _pattern_names(pattern: ast.pattern) -> list[str]:
    """Every name *pattern* captures, at any depth.

    A capture nested in a sequence, mapping, class, or alternative pattern holds
    part of the subject rather than the whole, which the rule cannot tell apart, so
    every capture is bound to the subject: a subject holding an acquisition is one
    wherever a pattern captures it.
    """
    names: list[str] = []
    for node in ast.walk(pattern):
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name is not None:
            names.append(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            names.append(node.rest)
    return names


def _value_bindings(node: ast.AST) -> list[tuple[list[str], ast.expr]]:
    """The names *node* binds and the expression it binds them to, for every form
    that binds a name to an expression this module can read.

    The enumeration is the point: assignment, annotation, walrus, iteration,
    ``with``, comprehension, ``match`` capture, and parameter defaults are one
    rule, so a seam reached by rewriting the binding into a form the rule had not
    enumerated is not an escape but an omission. The forms deliberately outside it
    bind no expression a seam could reach: an import binds a dotted path, which
    :func:`_imported_names` resolves instead, and ``def``, ``class``, ``type``, and
    ``except ... as`` bind a definition or a raised exception.
    """
    if isinstance(node, ast.Assign):
        return [([name for t in node.targets for name in _bound_names(t)], node.value)]
    if isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value is not None:
        return [(_bound_names(node.target), node.value)]
    if isinstance(node, ast.For | ast.AsyncFor | ast.comprehension):
        return [(_bound_names(node.target), node.iter)]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [(_bound_names(node.optional_vars), node.context_expr)]
    if isinstance(node, ast.Match):
        return [(_pattern_names(case.pattern), node.subject) for case in node.cases]
    if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef | ast.Lambda):
        positional = [*node.args.posonlyargs, *node.args.args]
        defaulted = positional[len(positional) - len(node.args.defaults) :]
        pairs = list(zip(defaulted, node.args.defaults, strict=True))
        pairs += [
            (argument, default)
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
            if default is not None
        ]
        return [([argument.arg], default) for argument, default in pairs]
    return []


def _local_aliases(tree: ast.Module, bindings: dict[str, str]) -> dict[str, str]:
    """Every plain name *tree* binds to an acquisition without calling it, including
    through a chain of such names.

    Calling a seam through a local name is the same acquisition as calling it
    where it is spelled, so a name bound to one is treated as the acquisition it
    holds — and a name bound to *that* name holds it too, which is why the bindings
    are collected until they stop growing rather than in one pass. Growth is the only
    direction: a name that ever holds an acquisition is never assumed to have lost it,
    so the collection is module-wide rather than per scope, independent of the order
    the bindings appear in, and terminating. Over-reporting fails a run loudly, while
    under-reporting is exactly the silent misclassification this guard exists to
    prevent.
    """
    aliases: dict[str, str] = {}
    growing = True
    while growing:
        growing = False
        for node in ast.walk(tree):
            for names, value in _value_bindings(node):
                acquisition = _acquisition_named(value, bindings, aliases)
                if acquisition is None:
                    continue
                for name in names:
                    if name not in aliases:
                        aliases[name] = acquisition
                        growing = True
    return aliases


def seam_calls(tree: ast.Module) -> list[tuple[int, str]]:
    """Every call in *tree* that acquires a live database.

    A call is one when its target resolves to a declared seam, when it calls a
    declared seam member — the indirection a scope's recipe reaches a seam through
    when what names it is a declared value rather than an import — or when it calls
    a local name the module bound to either, through any of the forms
    :func:`_value_bindings` enumerates and however many names and containers the
    binding passed through on the way.

    A value that leaves through a call — passed as an argument, or returned out of
    one — is outside the rule: what a callee does with a seam is not decidable from
    this module's syntax, and the sites that hand one over here hand it to something
    that replaces it rather than calls it.
    """
    bindings = _imported_names(tree)
    aliases = _local_aliases(tree, bindings)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        acquisition = _acquisition_named(node.func, bindings, aliases)
        if acquisition is not None:
            found.append((node.lineno, acquisition))
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

    classifier = tests_root / CLASSIFIER_MODULE
    if not classifier.is_file():
        findings.append(Finding(CLASSIFIER_MODULE, 0, f"{CLASSIFIER_MODULE} does not exist"))
    else:
        classifier_tree = ast.parse(classifier.read_text(encoding="utf-8"))
        declared = _declared_database_fixtures(classifier_tree)
        if declared != frozenset({ENTRY_POINT_FIXTURE}):
            findings.append(
                Finding(
                    CLASSIFIER_MODULE,
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


def main(argv: list[str]) -> int:
    """Audit the harness test tree.

    The tree is not a parameter — the harness has exactly one, located from this
    module. Exit codes: 0 — every live database acquisition goes through the
    designated fixture; 1 — at least one does not, or a structural precondition
    of the rule fails; 2 — usage error.
    """
    if argv:
        print(
            "usage: python -m reference_harness.check_database_access",
            file=sys.stderr,
        )
        return 2

    stale = unresolved_seams()
    findings = audit(TESTS_ROOT)
    if not stale and not findings:
        print(f"database-access check OK: live access is confined to `{ENTRY_POINT_FIXTURE}`")
        return 0

    if stale:
        print(
            f"database-access check FAILED ({len(stale)} unresolved seam(s)): a seam that\n"
            "  names nothing importable guards nothing, and the call-site audit reports a\n"
            "  clean tree either way.",
            file=sys.stderr,
        )
        for seam in stale:
            print(f"  - {seam}", file=sys.stderr)
    if findings:
        print(
            f"database-access check FAILED ({len(findings)} violation(s)): each collected item's\n"
            "  scheduling class is derived from its fixture closure, so an item reaching a\n"
            "  database another way is selected by `-m dbfree`.",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - tests/{finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
