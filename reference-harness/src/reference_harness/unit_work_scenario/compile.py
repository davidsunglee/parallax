"""Reading a Scenario's authored steps, once.

What each step is, before a database exists: which kind it is, which earlier steps
it names, which Unit Work group it belongs to, and which golden statements it
lists. What comes out is a closed set of variants carrying only the fields their
kind has, so no later phase of this package asks a raw step dictionary what it
means. The rules refused here are the ones those readings settle — which kind a
step is, and that every step it names is an earlier one — and nothing downstream
decides either a second time. What only a run can answer, that the step a
reference names actually published an observation, is the read oracle's and is
refused during execution. What the document says about itself —
which find a settling write may name, whether a step's dialect maps cover each
other — is asked of every case, in every lane, by
:mod:`~reference_harness.schema_validate`, so it is not restated here.

Dialect-free by construction. A step's golden SQL is dialect-keyed, so a compiled
step holds the entries it authored rather than one dialect's resolution of them,
and :class:`_Golden` is where that resolution happens for whichever dialect is
executing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..case import Case, entry_pairs, entry_statements, names_earlier_step
from ..case_assertions import CaseFailure

# The m-case-format lifecycle verbs that READ: a `load` triggers a deferred fetch
# and an `access` reads an already-loaded set. Every other verb either commits
# buffered DML or acts in memory, and is a boundary this package executes.
_ACTION_READ_VERBS = frozenset({"load", "access"})


@dataclass(frozen=True)
class _Golden:
    """The golden SQL entries one step lists, read for the executing dialect.

    A step's ``statements`` are authored per dialect, so the entries survive
    compilation unresolved and every later reader asks for the dialect it is
    running — the one place a Scenario's golden turns into text and binds.
    """

    entries: tuple[Any, ...]

    def pairs(self, dialect: str) -> list[tuple[str, list[Any]]]:
        return entry_pairs(list(self.entries), dialect)

    def sql(self, dialect: str) -> list[str]:
        return entry_statements(list(self.entries), dialect)


@dataclass(frozen=True)
class _SettledOn:
    """The find a settled write names, resolved to what that step published.

    Resolving the reference is compilation's, so nothing downstream reaches back
    into another step's dictionary to find out what the write settled against: the
    rows that read declares it returned, and the Object Query whose position says
    whether those rows carry a variant at all.
    """

    index: int
    object_query: Mapping[str, Any] | None
    observed_rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class _Step:
    """What every compiled step has, whatever kind it is: its authored position,
    the `uow` group it belongs to, its declared round trips, its golden, and the
    step it was read from.

    ``group`` is on every kind because the held-session lifecycle is: a label
    names one transaction, and which steps fall inside it is decided by the label
    alone, not by what those steps do.

    No compiled step carries its authored dictionary. Every fact this package's
    own later phases read is resolved here, so "execution does not reinterpret a
    raw step" holds by construction rather than by discipline; the read oracle is
    handed a step index and asks the case itself, in its own vocabulary. The
    adapter-delegated observables a
    step may also declare are validated by the schema and graded by each language's
    API Conformance Suite, never here.
    """

    index: int
    group: str | None
    round_trips: Any
    statements: _Golden


@dataclass(frozen=True)
class _GroupedWrite(_Step):
    """A buffered write inside a `uow` group: it applies on the group's held
    session and the GROUP, not this step, commits or rolls back.

    ``entries`` are the step's buffered keyed instructions in the neutral form
    write grading takes them in, which is why they are carried rather than
    resolved: the rows and mutations are :mod:`..write_plan`'s vocabulary, not a
    Scenario one.
    """

    entries: tuple[dict[str, Any], ...]
    rolls_back: bool
    settles_on: _SettledOn | None


@dataclass(frozen=True)
class _UngroupedWrite(_Step):
    """A write that is its own unit of work: committed on the provider's
    autocommit connection, or applied and discarded in a session of its own.

    ``entries`` are its buffered keyed instructions, carried in the neutral form
    write grading takes them in, exactly as :class:`_GroupedWrite`'s are.
    """

    entries: tuple[dict[str, Any], ...]
    rolls_back: bool


@dataclass(frozen=True)
class _BoundaryAction(_Step):
    """A lifecycle verb that commits DML and observes nothing."""

    verb: str


@dataclass(frozen=True)
class _Read(_Step):
    """A step whose observation the Object Query oracle owns. Its group, when it
    has one, is what selects the reader it is handed."""


@dataclass(frozen=True)
class _UnresolvedList(_Step):
    """The construction of a query-backed list that has not resolved: zero round
    trips, zero rows, and no observation until a later step accesses it."""


type _CompiledStep = _GroupedWrite | _UngroupedWrite | _BoundaryAction | _Read | _UnresolvedList


@dataclass(frozen=True)
class CompiledScenario:
    """One Scenario's steps as this package reads them, in authored order."""

    case: Case
    steps: tuple[_CompiledStep, ...]

    def has_golden(self, dialect: str) -> bool:
        """True if any step lists golden SQL for *dialect*."""
        return any(step.statements.sql(dialect) for step in self.steps)


def compile_scenario(case: Case) -> CompiledScenario:
    """Read *case*'s Scenario, refusing the defects its own document settles.

    Runs unconditionally, because everything it decides is a property of the
    document rather than of a dialect: a rule left to the dialect-keyed judgement
    would hold on some runs and not others.
    """
    if not case.scenario:
        raise CaseFailure(f"{case.path.name}: scenario case has no steps")
    return CompiledScenario(
        case=case,
        steps=tuple(_compile_step(case, index, step) for index, step in enumerate(case.scenario)),
    )


def _compile_step(case: Case, index: int, step: dict[str, Any]) -> _CompiledStep:
    """Which kind of step this is, decided once and nowhere else.

    "Is this a read?" is written as its complement: the closed set of kinds this
    package executes itself is a write, an action whose verb neither loads nor
    accesses, and the zero-round-trip construction of a query-backed list that has
    not resolved. Every other step is a read, and the read oracle grades whichever
    step it is handed rather than asking that question again.
    """
    label = step.get("uow")
    group = label if isinstance(label, str) else None
    common = (index, group, step.get("roundTrips"), _Golden(tuple(step.get("statements") or ())))

    _assert_step_references(case, index, step)

    if "write" in step:
        entries = _write_entries(step)
        rolls_back = step.get("rollback") is True
        if group is not None:
            return _GroupedWrite(*common, entries, rolls_back, _settled_on(case, step))
        return _UngroupedWrite(*common, entries, rolls_back)

    action = step.get("action")
    if action is not None and action not in _ACTION_READ_VERBS:
        _assert_no_action_observables(case, index, step)
        return _BoundaryAction(*common, action)
    if (
        action is None
        and not step.get("statements")
        and "stream" not in step
        and step.get("sameObjectAs") is None
        and step.get("on") is None
    ):
        return _UnresolvedList(*common)
    return _Read(*common)


def _assert_step_references(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a step naming anything but an EARLIER step of this Scenario.

    Every reference a step carries names a result some earlier step already
    produced: the source an action targets, each coordinate group a batched load
    consumes, the find a settling write was handed a value by, and the step whose
    object an identity claim is made against. So the bound is one rule over every
    kind of step, decided once here rather than by each owner mid-execution, and
    every reader downstream may address the step it names. ``on`` is OPTIONAL on
    the boundary verbs, which target the unit of work rather than a prior object;
    a boundary step that DOES carry one — a ``flush`` documenting its buffered
    write — owes the same bound.

    Only the bound. Whether the named step published anything is a property of the
    run rather than of the document — a step that fails its own observable
    publishes nothing — so the read oracle refuses that during execution.
    """
    on = step.get("on")
    sources = list(on) if isinstance(on, list) else [] if on is None else [on]
    if isinstance(on, list) and len(set(sources)) != len(sources):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].on {on!r} names a DUPLICATE source; "
            f"a coordinate-grouped action references each source at most once."
        )
    for source in sources:
        if not names_earlier_step(source, index):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on references step {source!r}, "
                f"which is not a real EARLIER step (0 <= source < {index}); a step's "
                f"`on` names a result some earlier step already produced."
            )
    identity = step.get("sameObjectAs")
    if identity is None:
        return
    if not isinstance(identity, int) or not names_earlier_step(identity, index):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].sameObjectAs={identity!r} is not a real "
            f"EARLIER step (0 <= source < {index}); an identity claim names the object an "
            f"earlier step observed."
        )


def _settled_on(case: Case, step: Mapping[str, Any]) -> _SettledOn | None:
    """The find *step* settles against, or ``None`` when it settles against none.

    The reference's shape is the case schema's and which step it may name is
    :mod:`~reference_harness.schema_validate`'s, both asked of every case before an
    executor sees it, and the bound is asserted above — so what is left is to read
    the named step once.
    """
    source = step.get("on")
    if source is None:
        return None
    origin = case.scenario[source]
    return _SettledOn(
        index=source,
        object_query=origin.get("objectQuery"),
        observed_rows=tuple(origin.get("expectRows") or ()),
    )


def _write_entries(step: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """One write step's own buffered KEYED entries, or none.

    A write step's ``write`` is a legacy string label, a single predicate-selected
    instruction (a mapping), or the buffered keyed sequence (a list) — only the
    last is a list of ``{mutation, entity, rows}`` entries.
    """
    write = step.get("write")
    if not isinstance(write, list):
        return ()
    return tuple(entry for entry in write if isinstance(entry, dict))


def _assert_no_action_observables(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a row observable on a step whose verb observes no rows.

    Grading one would mean reading what an earlier read retained, which is private
    to the read oracle, so a case authoring one is stating an observable this lane
    cannot answer and must fail loudly rather than pass vacuously.
    """
    declared = [key for key in ("expectRows", "expectGraph", "sameObjectAs") if key in step]
    if declared:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] is a {step['action']!r} action step "
            f"declaring {declared}; only the read verbs {sorted(_ACTION_READ_VERBS)} "
            f"observe rows, so what such a step publishes is nothing to compare."
        )
