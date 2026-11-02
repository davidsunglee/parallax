"""Fail when a test can reach a class's resource outside its designated fixture.

Each collected item's scheduling class is derived from its fixture closure
(``tests/conftest.py``), so an item that reaches a resource by any other route is
classified ``dbfree`` while needing it. That failure is silent rather than loud:
CI runners have Docker, so an item acquiring a database on its own passes in the
database-free job, and an item reaching the provider fails only where no
credentials happen to be present — and ``dbfree`` stops being true of what it
selects.

Two resource classes are confined, each by its own command (``--class``), over
one table of seams sorted by what each does:

* a **provisioning** seam starts a local server, and only ``profile_run`` may;
* a **connection** seam opens a database connection, which either fixture may,
  since a hosted cluster and a local container are reached the same way; and
* a **provider** seam reaches the provider — its parameter store, its credential
  chain, or the certificate bundle it publishes — and only ``aws_run`` may.

The `db` command reports provisioning and connection seams outside their
fixtures, and the `cloud` command reports provider seams outside theirs, so each
violation is reported once, by the command whose resource it reaches. A fixture
spans its own body in the entry module and, for ``aws_run``, the support modules
that implement it: those modules are the fixture's own execution, reached from a
test only through the provider seams they define.

The guard is a call-level rule, not an import-level one. Importing the adapter
or the provisioning module is legitimate — the internal-behavior surface
type-checks error translation against fake connections and reads the module's
constants — while *calling* one of the seams below opens a socket. Each call's
target is resolved through the importing module's own bindings, so a local name
that merely looks like a seam is not one, and a seam reached under an alias
still is — including a local name the module first binds to a seam and calls
afterwards, through any of the forms that bind a name to an expression this rule
can read, a ``match`` capture as much as an assignment, however many names the
binding passed through, and through any container it was stored in and taken back
out of. A declared
matrix profile reaches a seam through a member rather than an importable name —
naming the provisioner it opens, and opening it itself — so those members are
matched by name as well, on any receiver: the member is matched rather than
resolved, so a call the rule cannot type is reported rather than trusted. That
direction is deliberate — a false report is a loud failure a reader resolves,
while the state this guard exists to catch is silent on any host with Docker.

An acquisition reached on an INSTANCE is resolved the same way. The shipped
adapter's ``open`` is an instance method, so a dotted resolution alone reads it
only where it is written through the class, and ``adapter.open()`` — the ordinary
spelling — would resolve to nothing. A name bound to a call of a declared
constructor is therefore tracked as an instance of it, through the same binding
forms and containers a seam itself is followed through, and a declared member
read on such a name is the acquisition that member is.

The rule follows a value through this module's own bindings and stops at a call
boundary: a seam handed to a function or returned out of one is beyond it, because
deciding whether the callee calls it would take the whole program rather than one
syntax tree. Reporting an argument regardless would report the sites that hand a
seam over precisely to keep it from being constructed — patching the class the
declared profile holds so a construction fails loudly is one of them — so the
boundary is where a syntactic rule stops being able to tell the two apart. An
instance arriving from a helper's return value is outside it for the same reason.

One call may be waived, on the line it is reported at, by the reporting class's
marker — ``# database-access: <why>`` or ``# cloud-access: <why>`` — carrying a
reason. The marker exists because a rule strong enough to catch a rogue
``adapter.open()`` also catches a test that proves what ``open`` delegates to with
the delegate stubbed out — an acquisition in spelling that reaches no server.
Waiving it is a reviewed diff line carrying its justification, exactly as
``# noqa`` and ``# pyright: ignore`` are, and a marker with no reason after the
colon is NOT honored: an escape hatch that could be taken silently would be the
relaxation this guard exists to refuse.

The marker is recognized as a COMMENT the tokenizer sees, and it speaks for
exactly one call. Text spelling it inside a string literal — a connection string,
a message a test asserts on — is not a waiver, and a line reporting two
acquisitions is reported however it is annotated, since one reason cannot say
which of the two it was written for. Both follow from the same thing that makes
the hatch worth having: the waiver a reviewer reads beside a call has to be the
waiver the rule honored.

Structural facts are checked with it, because the rule is vacuous without them:
every declared seam must still name an importable callable, every declared
instance member must still be a declared seam, every declared profile must still
hold one on a declared seam member, the designated fixtures and their declared
implementing modules must exist, and the classifier's own table must map exactly
those fixtures to their classes.

Usage
-----
* ``python tools/check_resource_access.py --class db``     the local database
* ``python tools/check_resource_access.py --class cloud``  the provider-hosted environment

It never mutates anything and exits non-zero on any finding.
"""

from __future__ import annotations

import argparse
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

type Resolver = Callable[[ast.expr, dict[str, str], Bound], str | None]
"""One question asked of an expression, answered as the string it is reported by."""

_TOOL = "tools/check_resource_access.py"
TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"

ENTRY_POINT_MODULE = "conftest.py"
CLASSIFIER_CONSTANT = "_RESOURCE_FIXTURES"

# Fully qualified callables that start a local server: a container, the
# provisioner owning one, a primary and its standby, or the profile's own
# provisioned run.
PROVISION_SEAMS: frozenset[str] = frozenset(
    {
        "parallax.conformance._replication.ReplicationPair.open",
        "parallax.conformance.profile.ProvisionedRun",
        "parallax.conformance.provision.Provisioner",
        "testcontainers.community.postgres.PostgresContainer",
        "testcontainers.core.container.DockerContainer",
    }
)

# Fully qualified callables that open a connection to a database somebody else
# started. Constructing `PostgresAdapter` is deliberately absent: it is immutable
# configuration that opens nothing at all, so what acquires is
# `PostgresAdapter.open`. Constructing either scoped control is likewise absent,
# since both take a session somebody else opened — only the ``open`` that opens
# one for itself acquires anything.
#
# The adapter's ``open`` is declared under both the package it is exported from
# and the module defining it, so importing the defining module is not a way past
# the dotted resolution. Reaching it on an instance is `INSTANCE_SEAMS` below.
CONNECT_SEAMS: frozenset[str] = frozenset(
    {
        "parallax.conformance._postgres_control.PostgresControl.open",
        "parallax.conformance._postgres_control.PostgresInterleavedExecution.open",
        "parallax.conformance._postgres_control.open_session",
        "parallax.postgres.PostgresAdapter.open",
        "parallax.postgres.adapter.PostgresAdapter.open",
        "psycopg.connect",
    }
)

# Fully qualified callables that reach the provider: the published environment,
# a cloud run's lifetime, the real ports that run reaches the environment through
# (constructed on the AWS credential chain, opened by fetching the certificate
# bundle, and opening IAM-signed sessions), the AWS credential chain, and the
# certificate bundle fetched over HTTP. `parallax.aws.rds_endpoint` is
# deliberately absent: it is configuration that resolves no credential until a
# connection is opened.
AWS_SEAMS: frozenset[str] = frozenset(
    {
        "botocore.session.Session",
        "botocore.session.get_session",
        "tests._support.aws_environment.PublishedEnvironment.load",
        "tests._support.aws_run.AwsPorts",
        "tests._support.aws_run.AwsPorts.open",
        "tests._support.aws_run.AwsPorts.session",
        "tests._support.aws_run.AwsRun.open",
        "urllib.request.urlopen",
    }
)

SEAMS: frozenset[str] = PROVISION_SEAMS | CONNECT_SEAMS | AWS_SEAMS
"""Every declared seam, which the call-site analysis resolves against."""

# Constructors whose INSTANCES acquire, and the members that do the acquiring.
# Constructing an adapter is immutable configuration that opens nothing, so the
# constructor is not itself a seam; what it produces is a value whose `open` is
# one, and `adapter.open()` is how that is written everywhere except a test
# naming the class. Declaring the constructor is what lets the rule tell such a
# value from any other receiver, which is why matching `open` by name — the way
# `SEAM_MEMBERS` matches a profile's members — is not the rule here: `open` is a
# common enough member that name-matching it would report scores of calls that
# reach nothing. `unbacked_instance_seams` keeps each member honest by requiring
# it to be a declared seam under its own constructor.
INSTANCE_SEAMS: Mapping[str, frozenset[str]] = {
    "parallax.postgres.PostgresAdapter": frozenset({"open"}),
    "parallax.postgres.adapter.PostgresAdapter": frozenset({"open"}),
    "tests._support.aws_run.AwsPorts": frozenset({"session"}),
}

# Members through which a declared value reaches one of the seams above. A matrix
# profile names the provisioner it opens and opens it itself, so a database is
# acquired as ``<profile>.provisioner()`` or as ``<profile>.provisioned()`` — calls
# with no importable name of their own for the dotted resolution to reach. Such a
# call is matched by member name instead, and `unbacked_profiles` keeps that match
# honest by requiring every declared profile to still hold a seam on one of them.
# Both members provision.
SEAM_MEMBERS: frozenset[str] = frozenset({"provisioned", "provisioner"})


@dataclass(frozen=True)
class SeamKind:
    """What one group of seams does, which fixtures may call it, and the refusal
    a call elsewhere is reported with."""

    seams: frozenset[str]
    fixtures: frozenset[str]
    reaches: str


PROVISION = SeamKind(PROVISION_SEAMS, frozenset({"profile_run"}), "starts a local database server")
CONNECT = SeamKind(
    CONNECT_SEAMS, frozenset({"profile_run", "aws_run"}), "opens a database connection"
)
PROVIDER = SeamKind(AWS_SEAMS, frozenset({"aws_run"}), "reaches a provider-hosted environment")


@dataclass(frozen=True)
class ResourceClass:
    """One confined scheduling class: its designated fixture, the support modules
    implementing that fixture, the waiver marker its command honors, and the seam
    groups its command reports."""

    fixture: str
    implementations: tuple[str, ...]
    marker: str
    kinds: tuple[SeamKind, ...]

    @property
    def waiver(self) -> re.Pattern[str]:
        return re.compile(rf"#\s*{self.marker}:[ \t]*(?P<why>\S.*?)\s*$")


RESOURCE_CLASSES: Mapping[str, ResourceClass] = {
    "db": ResourceClass("profile_run", (), "database-access", (PROVISION, CONNECT)),
    "cloud": ResourceClass(
        "aws_run",
        ("_support/aws_run.py", "_support/aws_environment.py"),
        "cloud-access",
        (PROVIDER,),
    ),
}
"""Each confined class by name, as `tests/conftest.py`'s classifier names it."""


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
    """Every entry of :data:`SEAMS` that no longer names a callable.

    The seam set is hand-maintained against code it does not import, so a
    renamed or deleted seam would otherwise leave the guard reporting success
    over a rule that matches nothing.
    """
    return tuple(seam for seam in sorted(SEAMS) if not _resolves_to_callable(seam))


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
            if f"{constructor}.{member}" not in SEAMS
        )
    )


def unbacked_profiles() -> tuple[str, ...]:
    """Every declared profile holding no declared seam on a :data:`SEAM_MEMBERS`
    member.

    A member is matched by name rather than resolved, so it guards nothing unless
    the profiles still acquire their database through one. A provisioner renamed,
    replaced by something uncallable, or moved out of :data:`SEAMS` would
    otherwise leave the audit matching a member no acquisition goes through. One
    backed member is enough: the others are further forms of opening what it
    declares — a profile provisioning itself opens the class it holds — and a form
    that opens something is a method rather than a class this can resolve.
    """
    from parallax.conformance.profile import PROFILES

    unbacked: list[str] = []
    for profile in PROFILES:
        reached = False
        for member in SEAM_MEMBERS:
            target = getattr(profile, member, None)
            if isinstance(target, type):
                reached |= f"{target.__module__}.{target.__qualname__}" in PROVISION_SEAMS
        if not reached:
            unbacked.append(profile.name)
    return tuple(unbacked)


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
    return target if target is not None and target in SEAMS else None


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


def _declared_resource_fixtures(tree: ast.Module) -> dict[str, str] | None:
    """The fixture-to-class table :data:`CLASSIFIER_CONSTANT` declares, if it is
    assigned a literal mapping of strings to strings at module level."""
    for node in tree.body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else node.targets
            if isinstance(node, ast.Assign)
            else []
        )
        if CLASSIFIER_CONSTANT not in [t.id for t in targets if isinstance(t, ast.Name)]:
            continue
        value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
        if isinstance(value, ast.Call) and len(value.args) == 1:
            value = value.args[0]
        if not isinstance(value, ast.Dict):
            return None
        pairs = [
            (key.value, item.value)
            for key, item in zip(value.keys, value.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(item, ast.Constant)
        ]
        if len(pairs) != len(value.keys) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in pairs
        ):
            return None
        return {str(key): str(item) for key, item in pairs}
    return None


def _unwaived(
    source: str,
    acquisitions: Sequence[tuple[int, str]],
    waiver: re.Pattern[str],
    refusal: Callable[[str], str],
) -> list[tuple[int, str]]:
    """Every one of *acquisitions* no *waiver* in *source* excuses, with the message
    it is reported by, which *refusal* completes for each reported target.

    A waiver is the line's own, not the file's: it excuses the one call a reader
    can see beside it. It must carry a reason — a bare marker is not honored — so
    that taking the escape hatch costs a justification a reviewer reads, which is
    the whole of what keeps a guard with an escape hatch worth having.

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
        if token.type == tokenize.COMMENT and waiver.search(token.string) is not None
    }
    reported_on = Counter(line for line, _ in acquisitions)
    unwaived: list[tuple[int, str]] = []
    for line, target in acquisitions:
        if line not in waived:
            unwaived.append((line, f"calls `{target}`, {refusal(target)}"))
        elif reported_on[line] > 1:
            unwaived.append(
                (
                    line,
                    f"calls `{target}`, one of {reported_on[line]} acquisitions written on this "
                    f"line; a waiver speaks for the single call beside it, so give each its own",
                )
            )
    return unwaived


def seam_kind(target: str) -> SeamKind:
    """The group a reported acquisition belongs to. A declared seam member is
    named by its member, which only a profile's provisioning reaches."""
    for kind in (PROVISION, CONNECT, PROVIDER):
        if target in kind.seams:
            return kind
    return PROVISION


def _refusal(target: str) -> str:
    kind = seam_kind(target)
    fixtures = " or ".join(f"`{fixture}`" for fixture in sorted(kind.fixtures))
    return f"which {kind.reaches}; only {fixtures} in {ENTRY_POINT_MODULE} may"


@dataclass(frozen=True)
class _Admission:
    """Where each designated fixture runs: its body's lines in the entry module,
    and the modules implementing it."""

    spans: Mapping[str, tuple[int, int]]

    def admits(self, kind: SeamKind, relative: str, line: int) -> bool:
        for fixture in kind.fixtures:
            if relative in _implementations(fixture):
                return True
            span = self.spans.get(fixture)
            if relative == ENTRY_POINT_MODULE and span is not None and span[0] <= line <= span[1]:
                return True
        return False


def _implementations(fixture: str) -> tuple[str, ...]:
    return next(
        (entry.implementations for entry in RESOURCE_CLASSES.values() if entry.fixture == fixture),
        (),
    )


def _structure(tests_root: Path, resource: ResourceClass) -> tuple[list[Finding], _Admission]:
    """The findings the entry module and declared implementations raise, and where
    each designated fixture runs."""
    findings: list[Finding] = []
    entry_module = tests_root / ENTRY_POINT_MODULE
    if not entry_module.is_file():
        findings.append(Finding(ENTRY_POINT_MODULE, 0, f"{ENTRY_POINT_MODULE} does not exist"))
        return findings, _Admission({})
    entry_tree = ast.parse(entry_module.read_text(encoding="utf-8"))
    spans: dict[str, tuple[int, int]] = {}
    for entry in RESOURCE_CLASSES.values():
        span = _entry_point_span(entry_tree, entry.fixture)
        if span is not None:
            spans[entry.fixture] = span
    if resource.fixture not in spans:
        findings.append(
            Finding(
                ENTRY_POINT_MODULE,
                0,
                f"the designated fixture `{resource.fixture}` is not defined here",
            )
        )
    for implementation in resource.implementations:
        if not (tests_root / implementation).is_file():
            findings.append(
                Finding(
                    implementation, 0, f"`{resource.fixture}` is implemented here, yet it is absent"
                )
            )
    expected = {entry.fixture: name for name, entry in RESOURCE_CLASSES.items()}
    declared = _declared_resource_fixtures(entry_tree)
    if declared != expected:
        findings.append(
            Finding(
                ENTRY_POINT_MODULE,
                0,
                f"`{CLASSIFIER_CONSTANT}` must map exactly {expected}, the fixtures this guard "
                f"permits; it reads {'a non-literal mapping' if declared is None else declared}",
            )
        )
    return findings, _Admission(spans)


def audit(tests_root: Path, class_name: str) -> list[Finding]:
    """Every *class_name* violation under *tests_root*, addressed relative to it."""
    resource = RESOURCE_CLASSES[class_name]
    findings, admission = _structure(tests_root, resource)
    for path in sorted(tests_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(tests_root).as_posix()
        source = path.read_text(encoding="utf-8")
        acquisitions = [
            (line, target)
            for line, target in seam_calls(ast.parse(source))
            if seam_kind(target) in resource.kinds
            and not admission.admits(seam_kind(target), relative, line)
        ]
        findings.extend(
            Finding(relative, line, message)
            for line, message in _unwaived(source, acquisitions, resource.waiver, _refusal)
        )
    return findings


def _report(title: str, explanation: str, entries: Sequence[object]) -> None:
    print(f"{_TOOL}: {len(entries)} {title}\n{explanation}", file=sys.stderr)
    for entry in entries:
        print(f"    {entry}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resource access is fixture-only.")
    parser.add_argument(
        "--class",
        dest="resource_class",
        required=True,
        choices=sorted(RESOURCE_CLASSES),
        help="the scheduling class whose resource to confine",
    )
    arguments = parser.parse_args(argv)
    class_name: str = arguments.resource_class
    resource = RESOURCE_CLASSES[class_name]
    # The provider seams live in this tree's own support modules, which resolve
    # only with the implementation root importable.
    root = str(TESTS_ROOT.parent)
    if root not in sys.path:
        sys.path.insert(0, root)

    stale = unresolved_seams()
    undeclared = unbacked_instance_seams()
    unbacked = unbacked_profiles()
    findings = audit(TESTS_ROOT, class_name)
    if not stale and not undeclared and not unbacked and not findings:
        print(f"{_TOOL}: `{class_name}` access is confined to `{resource.fixture}`")
        return 0
    if undeclared:
        _report(
            "declared instance member(s) are not declared seams under their own constructor.",
            "  A member matched on a typed receiver is resolved by nothing else, so one\n"
            "  renamed away would guard nothing quietly.",
            undeclared,
        )
    if stale:
        _report(
            "declared seam(s) name nothing importable.",
            "  A seam that resolves to nothing guards nothing, and the call-site audit\n"
            "  reports a clean tree either way.",
            stale,
        )
    if unbacked:
        _report(
            "declared profile(s) reach no declared seam through a declared seam member.",
            "  The audit matches those members by name, so a profile acquiring a database\n"
            "  another way is acquired outside the guard.",
            unbacked,
        )
    if findings:
        _report(
            f"`{class_name}` access(es) outside the designated fixture.",
            "  Each collected item's scheduling class is derived from its fixture closure,\n"
            "  so an item reaching this resource another way is selected by `-m dbfree`.",
            [f"tests/{finding}" for finding in findings],
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
