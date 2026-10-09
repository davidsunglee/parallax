"""Reading a Scenario's authored steps, once.

What each step is, before a database exists: which kind it is, which earlier steps
it names, which Unit Work group it belongs to, and which golden statements it
lists. What comes out is a closed set of variants carrying only the fields their
kind has, so no later phase of this package asks a raw step dictionary what it
means. The rules refused here are the ones those readings settle — which kind a
step is, and that the references this package's own later phases resolve, a
step's ``on`` sources and a read's ``sameObjectAs`` anchor, name earlier steps —
and nothing downstream decides either a second time. What only a run can answer,
that the step a reference names actually published an observation, is the read
oracle's and is refused during execution. What the document says about itself —
which find a settling write may name, which earlier step EITHER identity anchor
names, whether a step's dialect maps cover each other — is asked of every case,
in every lane, by :mod:`~reference_harness.schema_validate`, so it is not
restated here. ``differentObjectFrom`` is bounded there and only there: no lane
this package executes grades it, so a bound restated here would hold nowhere it
is read.

Dialect-free by construction. A step's golden SQL is dialect-keyed, so a compiled
step holds the entries it authored rather than one dialect's resolution of them,
and :class:`_Golden` is where that resolution happens for whichever dialect is
executing.

Each buffered entry is a **submission**, addressed by its own pointer
``/scenario/<n>/write/<k>``, and each `uow` group has a **fate** read from
``then.units``. The rules those readings settle are refused here too: a
submission's ``on`` names an earlier find of its own group or an earlier,
unrefused insert of it; every label ``then.units`` names is a group; a flush
failure is reported where the group last flushes; a group's submissions share one
Transaction Instant; and the submission forms and refusals only a state-graded
case may carry appear nowhere else.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..case import Case, Entity, entry_pairs, entry_statements, names_earlier_step
from ..case_assertions import CaseFailure
from ..predicate_write_validate import requires_predicate_write_materialization

# A mutate publishes rows conditionally, only when it declares expectRows.
_ALWAYS_ROW_PUBLISHING_ACTIONS = frozenset({"load", "access"})


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
    raw step" holds by construction rather than by discipline; the row observation oracle is
    handed a step index and asks the case itself, in its own vocabulary. The
    adapter-delegated observables a
    step may also declare are validated by the schema and graded by each language's
    API Conformance Suite, never here.
    """

    index: int
    group: str | None
    round_trips: Any
    statements: _Golden


type SubmissionKind = Literal["keyed", "target", "predicate"]


@dataclass(frozen=True)
class Submission:
    """One entry of a buffered write step, read once.

    ``pointer`` is the entry's own case pointer, which a refusal and a reference
    name it by. ``entity`` and ``key`` name the one object a keyed or
    caller-addressed submission writes — the canonical Entity spelling and its
    primary-key values by attribute name — and are ``None`` for a predicate
    write, which names rows only its predicate selects. ``refusal`` is the code
    the entry declares its verb refuses it with, and ``settles_on`` the find its
    ``on`` names, resolved. ``flushes`` marks a predicate write whose target
    requires materialization: its verb flushes every submission of its group
    still pending, those before it in its own step included, before it resolves
    its selection.
    """

    pointer: str
    step: int
    position: int
    kind: SubmissionKind
    entry: Mapping[str, Any]
    entity: Entity | None
    key: Mapping[str, Any] | None
    refusal: str | None
    settles_on: _SettledOn | None
    flushes: bool = False

    @property
    def mutation(self) -> str:
        return str(self.entry.get("mutation"))

    @property
    def inserts(self) -> bool:
        return self.kind == "keyed" and self.mutation in _INSERT_MUTATIONS

    def names(self, entity: Entity, key: Mapping[str, Any]) -> bool:
        """Whether this submission writes the object ``key`` names of ``entity``."""
        return (
            self.entity is not None
            and self.key is not None
            and self.entity.canonical_name == entity.canonical_name
            and dict(self.key) == dict(key)
        )


@dataclass(frozen=True)
class _GroupedWrite(_Step):
    """A buffered write inside a `uow` group: it applies on the group's held
    session and the GROUP, not this step, commits or rolls back.

    ``entries`` are the step's buffered keyed instructions in the neutral form
    write grading takes them in, which is why they are carried rather than
    resolved: the rows and mutations are :mod:`..write_plan`'s vocabulary, not a
    Scenario one. ``submissions`` are the same entries as this package reads
    them.
    """

    entries: tuple[dict[str, Any], ...]
    submissions: tuple[Submission, ...]


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
class _RowPublishingStep(_Step):
    """A row-publishing step whose observation the Object Query oracle owns.

    This includes a ``mutate`` declaring ``expectRows`` beside the read
    workflows. Its group, when it has one, selects the reader it is handed.
    """


@dataclass(frozen=True)
class _UnresolvedList(_Step):
    """The construction of a query-backed list that has not resolved: zero round
    trips, zero rows, and no observation until a later step accesses it."""


type _CompiledStep = (
    _GroupedWrite | _UngroupedWrite | _BoundaryAction | _RowPublishingStep | _UnresolvedList
)

type Shortfall = Literal["missingTarget", "staleWrite", "optimisticConflict", "failedPrecondition"]


@dataclass(frozen=True)
class FlushFailure:
    """The failure a rolled-back group's flush reports: where the flush ran — a
    step index, or ``"commit"`` — and the object and Shortfall it names.
    ``flushed`` holds the pointers of the submissions that flush ran, the ones
    still pending when it began — when several flushes run at one step, when
    any of them began."""

    at: int | Literal["commit"]
    entity: Entity
    key: Mapping[str, Any]
    shortfall: Shortfall
    flushed: tuple[str, ...]

    @property
    def flushed_steps(self) -> frozenset[int]:
        """The write steps whose submissions that flush ran."""
        return frozenset(int(pointer.split("/")[2]) for pointer in self.flushed)


@dataclass(frozen=True)
class UnitFate:
    """One `uow` group as a unit of work: its own steps, in order, whether it
    commits or rolls back after its last one, the flush failure that rolled it
    back where one did, and the one Transaction Instant its submissions state."""

    label: str
    steps: tuple[int, ...]
    rolls_back: bool
    flush_failure: FlushFailure | None
    instant: str | None

    @property
    def last_step(self) -> int:
        return self.steps[-1]


@dataclass(frozen=True)
class CompiledScenario:
    """One Scenario's steps as this package reads them, in authored order, and
    each `uow` group's fate."""

    case: Case
    steps: tuple[_CompiledStep, ...]
    units: Mapping[str, UnitFate]
    state_graded: bool

    def has_golden(self, dialect: str) -> bool:
        """True if any step lists golden SQL for *dialect*."""
        return any(step.statements.sql(dialect) for step in self.steps)

    def submissions(self) -> tuple[Submission, ...]:
        """Every submission of every grouped write step, in authored order."""
        return tuple(
            submission
            for step in self.steps
            if isinstance(step, _GroupedWrite)
            for submission in step.submissions
        )


def compile_scenario(case: Case) -> CompiledScenario:
    """Read *case*'s Scenario, refusing the defects its own document settles.

    Runs unconditionally, because everything it decides is a property of the
    document rather than of a dialect: a rule left to the dialect-keyed judgement
    would hold on some runs and not others.
    """
    if not case.scenario:
        raise CaseFailure(f"{case.path.name}: scenario case has no steps")
    state_graded = case.state_graded
    steps = tuple(_compile_step(case, index, step) for index, step in enumerate(case.scenario))
    submissions = [
        submission
        for step in steps
        if isinstance(step, _GroupedWrite)
        for submission in step.submissions
    ]
    _assert_submission_sources(case, steps, submissions)
    if not state_graded:
        _assert_golden_submissions(case, submissions)
    units = _unit_fates(case, steps, state_graded=state_graded)
    if state_graded:
        _assert_state_graded_document(case, steps, submissions)
    return CompiledScenario(case=case, steps=steps, units=units, state_graded=state_graded)


def _compile_step(case: Case, index: int, step: dict[str, Any]) -> _CompiledStep:
    """Which kind of step this is, decided once and nowhere else.

    "Does this publish rows?" is written as its complement: the closed set of
    kinds this package executes itself is a write, an action other than ``load``,
    ``access``, or a ``mutate`` declaring ``expectRows``, and the
    zero-round-trip construction of a query-backed list that has not resolved —
    which a state-graded Scenario's find, listing no golden of its own, is not.
    Every other step publishes rows, and the observation oracle grades whichever
    step it is handed rather than asking that question again.

    Which kind a step is decides which rules it owes, so the classification comes
    before them: a boundary verb may declare no observable at all, and answering
    one of its identity claims with a bound would grade a key it was never
    entitled to carry. Only ``on``'s bound precedes the classification, because
    reading the find a settling write names reaches into the step it names.
    """
    label = step.get("uow")
    group = label if isinstance(label, str) else None
    common = (index, group, step.get("roundTrips"), _Golden(tuple(step.get("statements") or ())))

    _assert_on_sources(case, index, step)

    boundary_verb = _boundary_verb(step)
    if boundary_verb is not None:
        _assert_no_action_observables(case, index, step)
        return _BoundaryAction(*common, boundary_verb)
    _assert_identity_anchor(case, index, step)

    if "write" in step:
        entries = _write_entries(step)
        if group is not None:
            return _GroupedWrite(*common, entries, _submissions(case, index, entries))
        return _UngroupedWrite(*common, entries, step.get("rollback") is True)

    if (
        not case.state_graded
        and step.get("action") is None
        and not step.get("statements")
        and "stream" not in step
        and step.get("sameObjectAs") is None
        and step.get("on") is None
    ):
        return _UnresolvedList(*common)
    return _RowPublishingStep(*common)


def _boundary_verb(step: Mapping[str, Any]) -> str | None:
    """The lifecycle verb of a step that commits DML and observes nothing, or ``None``.

    A write step is never one however it is labelled: what it carries is buffered
    DML rather than a verb acting on an earlier step's object.
    """
    action = step.get("action")
    if (
        "write" in step
        or action is None
        or action in _ALWAYS_ROW_PUBLISHING_ACTIONS
        or (action == "mutate" and "expectRows" in step)
    ):
        return None
    return action


def _assert_on_sources(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse an ``on`` naming anything but an EARLIER step of this Scenario.

    ``on`` names a result some earlier step already produced: the source an action
    targets, each coordinate group a batched load consumes, the find a settling
    write was handed a value by. So the bound is one rule over every kind of step,
    decided once here rather than by each owner mid-execution, and every reader
    downstream may address the step it names. ``on`` is OPTIONAL on the boundary
    verbs, which target the unit of work rather than a prior object; a boundary
    step that DOES carry one — a ``flush`` documenting its buffered write — owes
    the same bound.

    Only the bound. Whether the named step published anything is a property of the
    run rather than of the document — a step that fails its own observable
    publishes nothing — so the observation oracle refuses that during execution.
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


def _assert_identity_anchor(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a ``sameObjectAs`` naming anything but an EARLIER step of this Scenario.

    The observation oracle resolves the anchor to what that step observed and compares
    primary-key identities, so the index must address a step this Scenario
    authored before the oracle reaches for it. Its counterpart
    ``differentObjectFrom`` is graded by no lane this package executes, so the
    corpus-wide bound :mod:`~reference_harness.schema_validate` asks of both is
    the whole of that one's, and restating it here would be a rule with no reader.
    """
    identity = step.get("sameObjectAs")
    if identity is None:
        return
    if not isinstance(identity, int) or not names_earlier_step(identity, index):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].sameObjectAs={identity!r} is not a real "
            f"EARLIER step (0 <= source < {index}); an identity claim names the object an "
            f"earlier step observed."
        )


def _settled_on(case: Case, index: int, entry: Mapping[str, Any]) -> _SettledOn | None:
    """The find *entry* settles against, or ``None`` when its ``on`` names no
    find — none at all, or the insert whose value it writes through.

    The reference's shape is the case schema's and which step it may name is
    :mod:`~reference_harness.schema_validate`'s, both asked of every case before an
    executor sees it, so what is left is to bound it and read the named step once.
    """
    source = entry.get("on")
    if not isinstance(source, int) or isinstance(source, bool):
        return None
    if not names_earlier_step(source, index):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] has a write entry whose `on` references "
            f"step {source!r}, which is not a real EARLIER step (0 <= source < {index}); a "
            f"write settles against a result some earlier step already produced."
        )
    origin = case.scenario[source]
    return _SettledOn(
        index=source,
        object_query=origin.get("objectQuery"),
        observed_rows=tuple(origin.get("expectRows") or ()),
    )


_INSERT_MUTATIONS = frozenset({"insert", "insertUntil"})
_POINTER = re.compile(r"^/scenario/(\d+)/write/(\d+)$")


def _submissions(
    case: Case, index: int, entries: tuple[dict[str, Any], ...]
) -> tuple[Submission, ...]:
    """Each entry of a grouped write step as the submission it is."""
    return tuple(
        _submission(case, index, position, entry) for position, entry in enumerate(entries)
    )


def _submission(case: Case, index: int, position: int, entry: Mapping[str, Any]) -> Submission:
    kind: SubmissionKind = (
        "predicate" if "target" in entry else "target" if "row" in entry else "keyed"
    )
    entity: Entity | None = None
    key: Mapping[str, Any] | None = None
    flushes = False
    if kind == "predicate":
        target = entry.get("target")
        if isinstance(target, Mapping):
            flushes = requires_predicate_write_materialization(
                case.model.entity(str(target.get("entity", "")))
            )
    else:
        entity = case.model.entity(str(entry.get("entity", "")))
        row = entry.get("row") if kind == "target" else (entry.get("rows") or [None])[0]
        if isinstance(row, Mapping):
            key = {
                attribute["name"]: row.get(attribute["name"])
                for attribute in entity.attributes
                if attribute.get("primaryKey")
            }
    refusal = entry.get("expectError")
    return Submission(
        pointer=f"/scenario/{index}/write/{position}",
        step=index,
        position=position,
        kind=kind,
        entry=entry,
        entity=entity,
        key=key,
        refusal=refusal if isinstance(refusal, str) else None,
        settles_on=_settled_on(case, index, entry),
        flushes=flushes,
    )


def _assert_submission_sources(
    case: Case, steps: tuple[_CompiledStep, ...], submissions: list[Submission]
) -> None:
    """Refuse a submission ``on`` naming anything a value could not come from.

    An index names an earlier find, which :func:`_settled_on` bounds and
    :mod:`~reference_harness.schema_validate` holds to the submission's own
    group. A pointer names the value an earlier insert of the same group
    answered, so it must address an insert submission of that group that the
    verb accepted: a refused insert answered no value to write through.
    """
    by_pointer = {submission.pointer: submission for submission in submissions}
    group_of = {step.index: step.group for step in steps}
    for submission in submissions:
        source = submission.entry.get("on")
        if source is None:
            continue
        where = f"{case.path.name}: {submission.pointer}"
        if submission.kind != "keyed" or submission.inserts:
            raise CaseFailure(
                f"{where} carries `on`, which only an observed keyed write takes: an insert "
                f"opens its row and a caller-addressed or predicate write names its own."
            )
        if not isinstance(source, str):
            continue
        match = _POINTER.match(source)
        named = by_pointer.get(source) if match else None
        earlier = named is not None and (named.step, named.position) < (
            submission.step,
            submission.position,
        )
        if (
            named is None
            or not earlier
            or group_of[named.step] != group_of[submission.step]
            or not named.inserts
        ):
            raise CaseFailure(
                f"{where} writes through {source!r}, which is not an earlier insert submission "
                f"of its own `uow` group — a pointer names the value an insert answered."
            )
        if named.refusal is not None:
            raise CaseFailure(
                f"{where} writes through {source!r}, a submission its verb refuses, which "
                f"answered no value to write through."
            )


def _assert_golden_submissions(case: Case, submissions: list[Submission]) -> None:
    """Refuse the forms only a state-graded case carries.

    A golden-graded step's SQL is the independent lowering of its keyed buffer,
    graded statement by statement against the find each write settles against;
    neither a caller-addressed nor a predicate submission, nor a refused one, has
    a golden statement that grading could align it with.
    """
    for submission in submissions:
        if submission.kind != "keyed" or submission.refusal is not None:
            raise CaseFailure(
                f"{case.path.name}: {submission.pointer} is a "
                f"{'refused' if submission.refusal is not None else submission.kind} "
                f"submission, which only a `grading: state` scenario carries."
            )


def _unit_fates(
    case: Case, steps: tuple[_CompiledStep, ...], *, state_graded: bool
) -> dict[str, UnitFate]:
    """Each `uow` group's fate, read off ``then.units``.

    A golden-graded group the case states no fate for commits; a state-graded
    case states every group's. A flush failure is reported where the group's
    work last reaches the database: at its last step where that is a find with
    writes pending before it, and otherwise at commit, which flushes what is
    still pending. Every submission of a group states the same instant, because
    one unit of work holds one Transaction Instant.
    """
    authored = case.then.get("units") or {}
    groups: dict[str, list[_CompiledStep]] = {}
    for step in steps:
        if step.group is not None:
            groups.setdefault(step.group, []).append(step)
    unknown = sorted(set(authored) - set(groups))
    if unknown:
        raise CaseFailure(
            f"{case.path.name}: then.units names {unknown}, which label no `uow` group."
        )
    missing = sorted(set(groups) - set(authored))
    if state_graded and missing:
        raise CaseFailure(
            f"{case.path.name}: then.units states no fate for group(s) {missing}; a "
            f"state-graded case states every group's."
        )
    fates: dict[str, UnitFate] = {}
    for label, members in groups.items():
        fate = authored.get(label) or {}
        fates[label] = UnitFate(
            label=label,
            steps=tuple(step.index for step in members),
            rolls_back=fate.get("outcome") == "rolledBack",
            flush_failure=_flush_failure(case, label, members, fate.get("flushFailure")),
            instant=_group_instant(case, label, members),
        )
    return fates


def _flush_failure(
    case: Case, label: str, members: list[_CompiledStep], authored: Any
) -> FlushFailure | None:
    if not isinstance(authored, Mapping):
        return None
    last = members[-1]
    # Several materializing predicate submissions of one step each flush there,
    # and `at` cannot say which of them failed.
    candidates: dict[int | Literal["commit"], tuple[str, ...]] = {}
    for at, flushed in _group_flushes(members):
        if flushed and at in ("commit", last.index):
            candidates[at] = candidates.get(at, ()) + flushed
    if authored.get("at") not in candidates:
        where = (
            "nothing"
            if not candidates
            else " or ".join(f"at {at!r}" for at in sorted(candidates, key=str))
        )
        raise CaseFailure(
            f"{case.path.name}: then.units.{label}.flushFailure.at is {authored.get('at')!r}, "
            f"but the group's last flush runs {where} — a failed flush ends the unit of work, "
            f"so it is the last thing the group does."
        )
    return FlushFailure(
        at=authored["at"],
        entity=case.model.entity(str(authored.get("entity", ""))),
        key=dict(authored.get("key") or {}),
        shortfall=authored["shortfall"],
        flushed=candidates[authored["at"]],
    )


def _group_flushes(
    members: list[_CompiledStep],
) -> list[tuple[int | Literal["commit"], tuple[str, ...]]]:
    """Each flush a group runs, in order: where it runs — a find's step, the
    step of a predicate submission whose verb flushes, or ``"commit"`` — beside
    the pointers of the submissions still pending when it began."""
    flushes: list[tuple[int | Literal["commit"], tuple[str, ...]]] = []
    pending: list[str] = []
    for step in members:
        if isinstance(step, _GroupedWrite):
            for submission in step.submissions:
                if submission.refusal is not None:
                    continue
                if submission.flushes:
                    flushes.append((step.index, tuple(pending)))
                    pending = []
                pending.append(submission.pointer)
        elif isinstance(step, _RowPublishingStep):
            flushes.append((step.index, tuple(pending)))
            pending = []
    if pending:
        flushes.append(("commit", tuple(pending)))
    return flushes


def _group_instant(case: Case, label: str, members: list[_CompiledStep]) -> str | None:
    instants = {
        submission.entry["at"]
        for step in members
        if isinstance(step, _GroupedWrite)
        for submission in step.submissions
        if "at" in submission.entry
    }
    if len(instants) > 1:
        raise CaseFailure(
            f"{case.path.name}: group {label!r} states the Transaction Instants "
            f"{sorted(instants)}; one unit of work holds one."
        )
    return next(iter(instants), None)


def _assert_state_graded_document(
    case: Case, steps: tuple[_CompiledStep, ...], submissions: list[Submission]
) -> None:
    """Refuse what a state-graded case leaves its fates or its rows unable to say.

    Every write belongs to a group, so every write's fate is stated; and the
    final ``then.tableState`` states every table a submission writes, so what the
    groups did is stated whole.
    """
    for step in steps:
        if isinstance(step, _UngroupedWrite):
            raise CaseFailure(
                f"{case.path.name}: scenario[{step.index}] is an ungrouped write in a "
                f"state-graded case, whose fate then.units cannot state."
            )
    written: set[str] = set()
    for submission in submissions:
        if submission.entity is not None:
            written.add(submission.entity.table)
        else:
            target = submission.entry.get("target") or {}
            written.add(case.model.entity(str(target.get("entity", ""))).table)
    unstated = sorted(written - set(case.expected_table_state))
    if unstated:
        raise CaseFailure(
            f"{case.path.name}: then.tableState states no rows for {unstated}, which a "
            f"submission writes; a state-graded case states every table it writes."
        )


def _write_entries(step: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """One write step's own buffered entries, or none.

    A write step's ``write`` is a legacy string label, a single predicate-selected
    instruction (a mapping), or the buffered sequence of submissions (a list).
    """
    write = step.get("write")
    if not isinstance(write, list):
        return ()
    return tuple(entry for entry in write if isinstance(entry, dict))


def _assert_no_action_observables(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a row observable on a step whose verb observes no rows.

    Grading one would mean reading what an earlier step retained, which is private
    to the observation oracle, so a case authoring one is stating an observable this lane
    cannot answer and must fail loudly rather than pass vacuously.
    """
    allowed = {"expectRows"} if step.get("action") == "mutate" else set()
    declared = [
        key
        for key in ("expectRows", "expectGraph", "sameObjectAs")
        if key in step and key not in allowed
    ]
    if declared:
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}] is a {step['action']!r} action step "
            f"declaring {declared}; only the actions that always publish rows "
            f"{sorted(_ALWAYS_ROW_PUBLISHING_ACTIONS)} "
            "and a `mutate` declaring `expectRows` observe rows, so what such a "
            "step publishes is nothing to compare."
        )
