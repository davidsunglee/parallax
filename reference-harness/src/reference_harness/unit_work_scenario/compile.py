"""Reading a Scenario's authored steps, once.

Every ordered semantic rule a Scenario answers to from its own document alone is
decided here, before a database exists: which kind each step is, which earlier
steps it names, which Unit Work group it belongs to, and which golden statements
it lists. What comes out is a closed set of variants carrying only the fields
their kind has, so no later phase asks a raw step dictionary what it means.

Dialect-free by construction. A step's golden SQL is dialect-keyed, so a compiled
step holds the entries it authored rather than one dialect's resolution of them,
and :class:`_Golden` is where that resolution happens for whichever dialect is
executing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..case import Case, entry_pairs, entry_statements
from ..case_assertions import CaseFailure, assert_step_on_sources

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

    No compiled step carries its authored dictionary. Everything a later phase
    reads is resolved here, so "execution does not reinterpret a raw step" holds by
    construction rather than by discipline; the adapter-delegated observables a
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
    """Read *case*'s Scenario, refusing a topology no execution could be correct on.

    Runs unconditionally, because everything it decides is a property of the
    document rather than of a dialect: a rule left to the dialect-keyed judgement
    would hold on some runs and not others.
    """
    if not case.scenario:
        raise CaseFailure(f"{case.path.name}: scenario case has no steps")
    _assert_source_finds(case)
    _assert_sql_bookkeeping(case)
    return CompiledScenario(
        case=case,
        steps=tuple(_compile_step(case, index, step) for index, step in enumerate(case.scenario)),
    )


def _compile_step(case: Case, index: int, step: dict[str, Any]) -> _CompiledStep:
    """Which kind of step this is, decided once.

    "Is this a read?" gets exactly one implementation by being written as its
    complement: the closed set of kinds this package executes itself is a write,
    an action whose verb neither loads nor accesses, and the zero-round-trip
    construction of a query-backed list that has not resolved. Every other step is
    a read.
    """
    label = step.get("uow")
    group = label if isinstance(label, str) else None
    common = (index, group, step.get("roundTrips"), _Golden(tuple(step.get("statements") or ())))

    if "write" in step:
        entries = _write_entries(step)
        rolls_back = step.get("rollback") is True
        if group is not None:
            return _GroupedWrite(*common, entries, rolls_back, _settled_on(case, step))
        return _UngroupedWrite(*common, entries, rolls_back)

    # `on` names earlier steps on every kind that carries it, so the bound is
    # decided here rather than by each owner mid-execution. A write's `on` is the
    # settling reference, which :func:`_assert_source_finds` has already read
    # under its own stricter rule.
    assert_step_on_sources(case, index, step)

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


def _settled_on(case: Case, step: Mapping[str, Any]) -> _SettledOn | None:
    """The find *step* settles against, or ``None`` when it settles against none.

    Every part of the reference is already validated (:func:`_assert_source_finds`),
    so what is left is to read the named step once.
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


def _assert_source_finds(case: Case) -> None:
    """Validate every write step's ``on`` — the find it settles against
    (`m-case-format` *Settling against a grouped find*).

    The reference is legal only where every part of it is meaningful: on a `uow`-
    grouped step whose ``write`` is the BUFFERED KEYED form, naming ONE earlier
    step of the SAME group that is a find. Every target profile is nameable,
    because on every one of them a unit of work may hold more than one piece of
    evidence about a key: a milestone chain holds several rows per key, and a
    versioned Non-Temporal key holds one observed generation per read of it.

    Structural and dialect-free, so it holds on every run rather than only where
    the case carries a golden for the dialect under test — the same reason the
    dialect-keyed cross-check that consumes the reference
    (:func:`~reference_harness.unit_work_scenario.judge.assert_settled_write`)
    cannot host it.
    """
    for index, step in enumerate(case.scenario):
        if "write" not in step or "on" not in step:
            continue
        source, label = step["on"], step.get("uow")
        if not isinstance(label, str):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against a find but declares no "
                f"`uow` group — the evidence a write consumes is transaction-scoped, and an "
                f"ungrouped write shares a unit of work with no find."
            )
        if not isinstance(source, int) or isinstance(source, bool):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on is {source!r}; a write step settles "
                f"against exactly ONE find, named by its index — a keyed write settles "
                f"against the one observed state the value it was handed came from."
            )
        if not 0 <= source < index:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}].on references step {source!r}, which is "
                f"not a real EARLIER step (0 <= source < {index})."
            )
        origin = case.scenario[source]
        if "objectQuery" not in origin or origin.get("uow") != label:
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against step {source}, which is "
                f"not a find step of its own `uow` group {label!r}."
            )
        if not isinstance(step.get("write"), list):
            raise CaseFailure(
                f"{case.path.name}: scenario[{index}] settles against a find but its `write` is "
                f"not the buffered keyed form — a legacy string label carries no instruction and "
                f"a predicate-selected write consumes no single observation, so neither has "
                f"anything the named observation could reach."
            )


def _assert_sql_bookkeeping(case: Case) -> None:
    """Validate scenario-local binds and independent read-oracle maps.

    Scenario SQL is stored below each step rather than at ``then``.  The same
    per-dialect coverage rules therefore apply independently at that location,
    and a read oracle must correspond to the golden read it is the naive
    spelling of: one statement for an ordinary find, and a STREAMED step's whole
    page list for one delivery (`m-case-format` *Streamed read steps*), whose
    naive oracle answers the roots every page of it published.
    """
    for index, step in enumerate(case.scenario):
        entries = step.get("statements", [])
        if not isinstance(entries, list):
            continue
        for statement_index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("binds"), dict):
                continue
            sql = entry.get("sql")
            sql_keys = set(sql) if isinstance(sql, dict) else set()
            if set(entry["binds"]) != sql_keys:
                raise CaseFailure(
                    f"{case.path.name}: when.scenario[{index}].statements[{statement_index}] "
                    f"binds map keys {sorted(entry['binds'])} != sql map keys "
                    f"{sorted(sql_keys)}"
                )
        reference_sql = step.get("referenceSql")
        if reference_sql is None:
            continue
        if not entries or (len(entries) != 1 and "stream" not in step):
            raise CaseFailure(
                f"{case.path.name}: when.scenario[{index}] referenceSql needs the golden read "
                "it is the naive spelling of — exactly one statement for an ordinary find, "
                "and a streamed step's own pages for one delivery"
            )
        if not isinstance(reference_sql, dict):
            continue
        sql = entries[0].get("sql") if isinstance(entries[0], dict) else None
        sql_keys = set(sql) if isinstance(sql, dict) else set()
        if set(reference_sql) != sql_keys:
            raise CaseFailure(
                f"{case.path.name}: when.scenario[{index}].referenceSql map keys "
                f"{sorted(reference_sql)} != golden sql map keys {sorted(sql_keys)}"
            )
