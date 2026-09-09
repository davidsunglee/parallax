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

An acquisition reached on an INSTANCE is resolved the same way. A name bound to a
call of a declared constructor is tracked as an instance of it, through the same
binding forms and containers a seam itself is followed through, and a declared
member read on such a name is the acquisition that member is. This tree declares
no such constructor: every acquisition here is a module-level callable or a
container class, and a member listed without a constructor declaring it would
match calls that acquire nothing.

The rule follows a value through this module's own bindings and stops at a call
boundary: a seam handed to a function or returned out of one is beyond it, because
deciding whether the callee calls it would take the whole program rather than one
syntax tree. Reporting an argument regardless would report the sites that hand a
seam over precisely to keep it from being constructed, which is the point where a
syntactic rule stops being able to tell the two apart. An instance arriving from a
helper's return value is outside it for the same reason.

One call may be waived, on the line it is reported at, by a
``# database-access: <why>`` marker carrying a reason. Waiving is a reviewed diff
line carrying its justification, exactly as ``# noqa`` and ``# pyright: ignore``
are, and a marker with no reason after the colon is NOT honored: an escape hatch
that could be taken silently would be the relaxation this guard exists to refuse.

The marker is recognized as a COMMENT the tokenizer sees, and it speaks for
exactly one call. Text spelling it inside a string literal — a connection string,
a message a test asserts on — is not a waiver, and a line reporting two
acquisitions is reported however it is annotated, since one reason cannot say
which of the two it was written for. Both follow from the same thing that makes
the hatch worth having: the waiver a reviewer reads beside a call has to be the
waiver the rule honored.

Four structural facts are checked with it, because the rule is vacuous without
them: every declared seam must still name an importable callable, every declared
instance member must still be a declared seam, the designated fixture must exist,
and the classifier's own designated set must name exactly it.
"""

from __future__ import annotations

import ast
import importlib
import io
import re
import sys
import tokenize
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "CLASSIFIER_CONSTANT",
    "CLASSIFIER_MODULE",
    "DATABASE_SEAMS",
    "ENTRY_POINT_FIXTURE",
    "ENTRY_POINT_MODULE",
    "INSTANCE_SEAMS",
    "SEAM_MEMBERS",
    "TESTS_ROOT",
    "WAIVER_MARKER",
    "Finding",
    "audit",
    "main",
    "seam_calls",
    "unbacked_instance_seams",
    "unresolved_seams",
]

type Resolver = Callable[[ast.expr, dict[str, str], Bound], str | None]
"""One question asked of an expression, answered as the string it is reported by."""

WAIVER_MARKER = "database-access"
_WAIVER = re.compile(rf"#\s*{WAIVER_MARKER}:[ \t]*(?P<why>\S.*?)\s*$")

TESTS_ROOT = Path(__file__).resolve().parents[2] / "tests"

# The fixture and the classifier that designates it live in the same file: more
# than one test module executes against a database, so the fixture belongs where
# every module can reach the one definition of it.
ENTRY_POINT_MODULE = "conftest.py"
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

# Constructors whose INSTANCES acquire, and the members that do the acquiring.
# Empty here for the same reason `SEAM_MEMBERS` is: every acquisition in this tree
# is spelled as a call of one of the seams above, and a member declared without a
# constructor holding it would guard nothing.
INSTANCE_SEAMS: Mapping[str, frozenset[str]] = {}


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


def unbacked_instance_seams() -> tuple[str, ...]:
    """Every :data:`INSTANCE_SEAMS` member that is not a declared seam under its own
    constructor.

    A member is matched on a receiver the rule typed rather than resolved, so
    nothing else would notice it being renamed or removed. Requiring it to be a
    declared seam under its constructor puts it back under
    :func:`unresolved_seams`, which does resolve it, and keeps the two spellings
    of one acquisition from drifting apart.
    """
    return tuple(
        sorted(
            f"{constructor}.{member}"
            for constructor, members in INSTANCE_SEAMS.items()
            for member in members
            if f"{constructor}.{member}" not in DATABASE_SEAMS
        )
    )


@dataclass(frozen=True)
class Bound:
    """What each plain name in one module holds, as far as its syntax says.

    Three questions the rule asks of a name, kept apart because their answers
    compose: a name may hold an ACQUISITION to call, the CONSTRUCTOR of a class
    whose instances acquire, or an INSTANCE of one. A name bound to an instance
    is how ``adapter.open()`` is reached, and one bound to a constructor is what
    makes rebinding the class first no different from naming it.
    """

    acquisitions: dict[str, str]
    constructors: dict[str, str]
    instances: dict[str, str]


def _held_elements(expression: ast.expr) -> Sequence[ast.expr] | None:
    """The elements *expression* holds as a container, or ``None`` if it is not one.

    Storing a value in a tuple, list, set, or dict and taking it back out is the
    same value under a longer spelling, so every resolver below looks through a
    container and answers with the first element that answers: what a call
    reaches is what the finding names, and one is enough to reach it.
    """
    if isinstance(expression, ast.Tuple | ast.List | ast.Set):
        return expression.elts
    if isinstance(expression, ast.Dict):
        return expression.values
    if isinstance(expression, ast.Subscript | ast.Starred):
        return [expression.value]
    return None


def _constructor_named(expression: ast.expr, bindings: dict[str, str], bound: Bound) -> str | None:
    """The :data:`INSTANCE_SEAMS` constructor *expression* names, else ``None``."""
    if isinstance(expression, ast.Name) and expression.id in bound.constructors:
        return bound.constructors[expression.id]
    held = _held_elements(expression)
    if held is not None:
        return _first(held, bindings, bound, _constructor_named)
    target = _resolved_target(expression, bindings)
    return target if target is not None and target in INSTANCE_SEAMS else None


def _instance_named(expression: ast.expr, bindings: dict[str, str], bound: Bound) -> str | None:
    """The constructor *expression* holds an instance of, else ``None``.

    An instance comes into existence at a call of a declared constructor and
    travels the way any other value does. It does not come back out of another
    call: what a helper returns is beyond the same boundary a seam handed to one
    is, and treating an unrelated call's result as an instance would report
    receivers this rule cannot type.
    """
    if isinstance(expression, ast.Name) and expression.id in bound.instances:
        return bound.instances[expression.id]
    if isinstance(expression, ast.Call):
        return _constructor_named(expression.func, bindings, bound)
    held = _held_elements(expression)
    return _first(held, bindings, bound, _instance_named) if held is not None else None


def _acquisition_named(expression: ast.expr, bindings: dict[str, str], bound: Bound) -> str | None:
    """How *expression* is reported when it names an acquisition, else ``None``.

    An acquisition is named by a dotted path resolving to a declared seam, by a
    declared seam member — which has no importable name of its own for the dotted
    resolution to reach — by a declared member read on a value *bound* holds an
    instance of, by a plain name *bound* already found to hold an acquisition, or
    by a container holding any of those.
    """
    if isinstance(expression, ast.Name) and expression.id in bound.acquisitions:
        return bound.acquisitions[expression.id]
    if isinstance(expression, ast.Attribute):
        if expression.attr in SEAM_MEMBERS:
            return f".{expression.attr}()"
        constructor = _instance_named(expression.value, bindings, bound)
        if constructor is not None and expression.attr in INSTANCE_SEAMS[constructor]:
            return f"{constructor}.{expression.attr}"
    held = _held_elements(expression)
    if held is not None:
        return _first(held, bindings, bound, _acquisition_named)
    target = _resolved_target(expression, bindings)
    return target if target is not None and target in DATABASE_SEAMS else None


def _first(
    held: Sequence[ast.expr],
    bindings: dict[str, str],
    bound: Bound,
    resolve: Resolver,
) -> str | None:
    """The first of *held* that *resolve* answers for."""
    for element in held:
        answer = resolve(element, bindings, bound)
        if answer is not None:
            return answer
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


def _bind(holder: dict[str, str], names: Sequence[str], answer: str | None) -> bool:
    """Bind each of *names* to *answer*, reporting whether any binding was new."""
    if answer is None:
        return False
    fresh = [name for name in names if name not in holder]
    holder.update(dict.fromkeys(fresh, answer))
    return bool(fresh)


def _local_bindings(tree: ast.Module, bindings: dict[str, str]) -> Bound:
    """Every plain name *tree* binds to an acquisition, a declared constructor, or an
    instance of one, including through a chain of such names.

    Calling a seam through a local name is the same acquisition as calling it
    where it is spelled, so a name bound to one is treated as the acquisition it
    holds — and a name bound to *that* name holds it too, which is why the bindings
    are collected until they stop growing rather than in one pass. Growth is the only
    direction: a name that ever holds an acquisition is never assumed to have lost it,
    so the collection is module-wide rather than per scope, independent of the order
    the bindings appear in, and terminating. Over-reporting fails a run loudly, while
    under-reporting is exactly the silent misclassification this guard exists to
    prevent.

    The three answers grow together because they feed each other: a name holding a
    constructor makes a call of it an instance, and a name holding an instance makes
    a declared member read on it an acquisition.
    """
    bound = Bound({}, {}, {})
    growing = True
    while growing:
        growing = False
        for node in ast.walk(tree):
            for names, value in _value_bindings(node):
                answers = (
                    (bound.acquisitions, _acquisition_named(value, bindings, bound)),
                    (bound.constructors, _constructor_named(value, bindings, bound)),
                    (bound.instances, _instance_named(value, bindings, bound)),
                )
                for holder, answer in answers:
                    growing |= _bind(holder, names, answer)
    return bound


def seam_calls(tree: ast.Module) -> list[tuple[int, str]]:
    """Every call in *tree* that acquires a live database.

    A call is one when its target resolves to a declared seam, when it calls a
    declared seam member — the indirection a scope's recipe reaches a seam through
    when what names it is a declared value rather than an import — when it calls a
    declared member on a value the module holds an instance of, or when it calls a
    local name the module bound to any of those, through any of the forms
    :func:`_value_bindings` enumerates and however many names and containers the
    binding passed through on the way.

    A value that leaves through a call — passed as an argument, or returned out of
    one — is outside the rule: what a callee does with a seam is not decidable from
    this module's syntax, and the sites that hand one over here hand it to something
    that replaces it rather than calls it.
    """
    bindings = _imported_names(tree)
    bound = _local_bindings(tree, bindings)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        acquisition = _acquisition_named(node.func, bindings, bound)
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


def _unwaived(source: str, acquisitions: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    """Every one of *acquisitions* no waiver in *source* excuses, with the message
    it is reported by.

    A waiver is the line's own, not the file's: it excuses the one call a reader
    can see beside it. It must carry a reason — a bare ``# database-access:`` is
    not honored — so that taking the escape hatch costs a justification a
    reviewer reads, which is the whole of what keeps a guard with an escape hatch
    worth having.

    Two things follow from that, and both are decided here. The marker is a
    COMMENT the tokenizer reports, so text spelling it inside a string literal is
    not a waiver: a rule reading raw lines would let an acquisition's own
    argument waive it, silently and with no line a reviewer reads as a waiver.
    And it speaks for one call, so a line reporting more than one acquisition is
    reported whatever is written beside it — a single reason cannot say which of
    them it was written for.
    """
    waived = {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and _WAIVER.search(token.string) is not None
    }
    reported_on = Counter(line for line, _ in acquisitions)
    unwaived: list[tuple[int, str]] = []
    for line, target in acquisitions:
        if line not in waived:
            unwaived.append(
                (
                    line,
                    f"calls `{target}`, which acquires a live database; only the "
                    f"`{ENTRY_POINT_FIXTURE}` fixture in {ENTRY_POINT_MODULE} may",
                )
            )
        elif reported_on[line] > 1:
            unwaived.append(
                (
                    line,
                    f"calls `{target}`, one of {reported_on[line]} acquisitions written on this "
                    f"line; a waiver speaks for the single call beside it, so give each its own",
                )
            )
    return unwaived


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
        source = path.read_text(encoding="utf-8")
        permitted = allowed if relative == ENTRY_POINT_MODULE else None
        acquisitions = [
            (line, target)
            for line, target in seam_calls(ast.parse(source))
            if permitted is None or not permitted[0] <= line <= permitted[1]
        ]
        findings.extend(
            Finding(relative, line, message) for line, message in _unwaived(source, acquisitions)
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
    undeclared = unbacked_instance_seams()
    findings = audit(TESTS_ROOT)
    if not stale and not undeclared and not findings:
        print(f"database-access check OK: live access is confined to `{ENTRY_POINT_FIXTURE}`")
        return 0

    if undeclared:
        print(
            f"database-access check FAILED ({len(undeclared)} undeclared instance member(s)):\n"
            "  a member matched on a typed receiver is resolved by nothing else, so one\n"
            "  renamed away would guard nothing quietly.",
            file=sys.stderr,
        )
        for member in undeclared:
            print(f"  - {member}", file=sys.stderr)
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
