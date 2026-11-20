"""Compile and observe explicit scenario steps over snapshot values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from ..case import (
    Case,
    Entity,
    entry_pairs,
    entry_statements,
    names_earlier_step,
    states_revision,
)
from ..case_assertions import CaseFailure, write_value_equal
from ..database_binding import PhysicalTable
from ..inheritance import Family
from ..temporality import temporal_axes
from ..write_plan import assigns_nothing

# A mutate publishes rows conditionally, only when it declares expectRows.
_ALWAYS_ROW_PUBLISHING_ACTIONS = frozenset({"access"})


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
    the `uow` group it belongs to, its declared Database Calls, its golden, and the
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
    database_calls: Any
    statements: _Golden

    def presented(self, dialect: str) -> list[str]:
        """Every golden SQL text this step lists for *dialect*, in the order its
        call presented them."""
        return self.statements.sql(dialect)

    @property
    def flush_golden(self) -> _Golden:
        """The golden of the Flush this step's call presented, where it presented one."""
        return self.statements


type SubmissionKind = Literal["keyed", "target", "predicate"]


@dataclass(frozen=True)
class Submission:
    """One entry of a buffered write step, read once.

    ``pointer`` is the entry's own case pointer, which a refusal and a reference
    name it by. ``entity`` and ``key`` name the one object a keyed or
    target submission writes — the canonical Entity spelling and its
    primary-key values by attribute name — and are ``None`` for a predicate
    write, which names rows only its predicate selects. ``refusal`` is the code
    the entry declares its verb refuses it with, and ``settles_on`` the find its
    ``on`` names, resolved. ``empty`` marks a submission that writes nothing,
    and so leaves nothing pending: a predicate write whose verb opens no flush —
    an amendment assigning nothing, or a replacement of an Entity whose only
    writable member is its key — or a keyed or target amendment naming nothing
    beside its key, which is dropped once validated.
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
    empty: bool

    @property
    def mutation(self) -> str:
        return str(self.entry.get("mutation"))

    @property
    def inserts(self) -> bool:
        return self.kind == "keyed" and self.mutation in _INSERT_MUTATIONS

    @property
    def flushes(self) -> bool:
        """Whether its call runs a flush: an accepted predicate write that
        writes something, which executes in the flush it runs."""
        return self.kind == "predicate" and self.refusal is None and not self.empty

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
    them. ``affected_rows`` is the count a direct predicate write states its
    verb returns, ``None`` for any other write. ``runs_flush`` marks a direct
    predicate write that writes something, whose call runs a Flush of what its
    group has pending and executes in it, its own statement last.
    """

    entries: tuple[dict[str, Any], ...]
    submissions: tuple[Submission, ...]
    affected_rows: int | None
    runs_flush: bool

    @property
    def flush_golden(self) -> _Golden:
        """The golden of the Flush this step presents: a predicate write's
        statements before its own, or a keyed write step's whole list, which is
        its group's commit Flush when it is the group's last step."""
        return _Golden(self.statements.entries[:-1] if self.runs_flush else self.statements.entries)


@dataclass(frozen=True)
class _UngroupedWrite(_Step):
    """A write that is its own unit of work: committed on the provider's
    autocommit connection, or applied and discarded in a session of its own.

    ``entries`` are its buffered keyed instructions, carried in the neutral form
    write grading takes them in, exactly as :class:`_GroupedWrite`'s are, and
    ``affected_rows`` is the count a direct predicate write states.
    """

    entries: tuple[dict[str, Any], ...]
    rolls_back: bool
    affected_rows: int | None


@dataclass(frozen=True)
class _BoundaryAction(_Step):
    """A lifecycle verb that commits DML and observes nothing."""

    verb: str


@dataclass(frozen=True)
class _RowPublishingStep(_Step):
    """A row-publishing step whose observation the Object Query oracle owns.

    This includes a ``mutate`` declaring ``expectRows`` beside the read
    workflows. Its group, when it has one, selects the reader it is handed.
    ``flush`` is the Flush a grouped find's call runs before its read, which
    this package executes; the oracle reads ``statements`` alone.
    """

    flush: _Golden

    @property
    def flush_golden(self) -> _Golden:
        """The golden of the Flush this step's call presented, where it presented one."""
        return self.flush

    def presented(self, dialect: str) -> list[str]:
        return [*self.flush.sql(dialect), *self.statements.sql(dialect)]


type _CompiledStep = _GroupedWrite | _UngroupedWrite | _BoundaryAction | _RowPublishingStep

type Shortfall = Literal["missingTarget", "staleWrite", "optimisticConflict", "failedPrecondition"]
type FlushError = Literal["temporalConflict"]


@dataclass(frozen=True)
class GroupFlush:
    """One nonempty Flush a group runs.

    ``at`` is where it runs — a find's or a flushing predicate write's step, or
    ``"commit"`` — and ``site`` the step whose call presented it, which lists its
    golden (`m-case-format` *Which step a statement belongs to*): ``at`` itself,
    or the group's last step for the commit's Flush. ``flushed`` holds the
    pointers of the submissions it ran: those still pending when it began, and a
    buffered predicate submission's own, which executes in the Flush its call
    runs. A direct predicate write's own statement is its step's, not a
    submission's.
    """

    site: int
    at: int | Literal["commit"]
    flushed: tuple[str, ...]


@dataclass(frozen=True)
class FlushFailure:
    """The failure a rolled-back group's flush reports: where the flush ran — a
    step index, or ``"commit"`` — and the object it names, beside exactly one of
    its Shortfall and an ``error`` that is no Shortfall. ``site`` is the step
    whose golden lists the failing Flush, and ``flushed`` holds the pointers of
    the submissions it ran, the ones still pending when it began — when several
    flushes run at one step, when any of them began."""

    at: int | Literal["commit"]
    site: int
    entity: Entity
    key: Mapping[str, Any]
    shortfall: Shortfall | None
    error: FlushError | None
    flushed: tuple[str, ...]


@dataclass(frozen=True)
class UnitFate:
    """One `uow` group as a unit of work: its own steps, in order, whether it
    commits or rolls back after its last one, each Flush it runs in order, the
    flush failure that rolled it back where one did, and the one Transaction
    Instant its submissions state."""

    label: str
    steps: tuple[int, ...]
    rolls_back: bool
    flushes: tuple[GroupFlush, ...]
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
        return any(step.presented(dialect) for step in self.steps)

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
        _assert_golden_submissions(case, steps, submissions)
    units = _unit_fates(case, steps, state_graded=state_graded)
    if state_graded:
        _assert_state_graded_document(case, steps, submissions)
    else:
        _assert_statement_placement(case, steps, units)
    return CompiledScenario(case=case, steps=steps, units=units, state_graded=state_graded)


def _compile_step(case: Case, index: int, step: dict[str, Any]) -> _CompiledStep:
    """Classify a step and validate the sources it references."""
    label = step.get("uow")
    group = label if isinstance(label, str) else None
    common = (index, group, step.get("databaseCalls"), _Golden(tuple(step.get("statements") or ())))

    _assert_on_sources(case, index, step)

    boundary_verb = _boundary_verb(step)
    if boundary_verb is not None:
        _assert_no_action_observables(case, index, step)
        return _BoundaryAction(*common, boundary_verb)

    _assert_identity_anchor(case, index, step)
    if "write" in step:
        entries = _write_entries(step)
        affected_rows = step.get("expectAffectedRows")
        if group is not None:
            write = step["write"]
            runs_flush = isinstance(write, Mapping) and not _writes_nothing(case, write)
            return _GroupedWrite(
                *common, entries, _submissions(case, index, entries), affected_rows, runs_flush
            )
        return _UngroupedWrite(*common, entries, step.get("rollback") is True, affected_rows)

    return _RowPublishingStep(*common, _Golden(tuple(step.get("flush") or ())))


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
    targets, or the find a settling
    write was handed a value by. So the bound is one rule over every kind of step,
    decided once here rather than by each owner mid-execution, and every reader
    downstream may address the step it names.

    Only the bound. Whether the named step published anything is a property of the
    run rather than of the document — a step that fails its own observable
    publishes nothing — so the observation oracle refuses that during execution.
    """
    on = step.get("on")
    if on is not None and (
        not isinstance(on, int) or isinstance(on, bool) or not names_earlier_step(on, index)
    ):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].on references step {on!r}, "
            f"which is not a real EARLIER step (0 <= source < {index}); a step's "
            f"`on` names a result some earlier step already produced."
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
        "predicate" if "target" in entry else "target" if states_revision(entry) else "keyed"
    )
    entity: Entity | None = None
    key: Mapping[str, Any] | None = None
    if kind != "predicate":
        entity = case.model.entity(str(entry.get("entity", "")))
        row = entry.get("row")
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
        empty=_writes_nothing(case, entry)
        if kind == "predicate"
        else entity is not None and assigns_nothing(entity, entry),
    )


def _writes_nothing(case: Case, entry: Mapping[str, Any]) -> bool:
    mutation = entry.get("mutation")
    if mutation == "amend":
        return not entry.get("assignments")
    if mutation != "replace":
        return False
    target = entry.get("target") or {}
    entity = case.model.entity(str(target.get("entity", "")))
    return not entity.value_objects and all(
        attribute.get("primaryKey") or attribute.get("readOnly") for attribute in entity.attributes
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
                f"opens its row and a target or predicate write names its own."
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


def _assert_golden_submissions(
    case: Case, steps: tuple[_CompiledStep, ...], submissions: list[Submission]
) -> None:
    """Refuse the forms only a state-graded case carries.

    A golden-graded step's SQL is the independent lowering of its buffer,
    graded against the find each keyed write settles against or the revision
    each target write states, with the reads its flush owes counted from the
    document (`m-case-format` *Buffered keyed write instructions*). A predicate
    or refused submission has no golden statement that grading could align it
    with. A target submission is admitted where what it costs follows from the
    document alone: it is the only submission of its group naming its object,
    and no earlier find of the group may have returned a row of that object
    (:func:`_observes`), so nothing pending or observed stands in for its
    acquisition or composes with it; and under Locking its Entity has no Valid
    Time, since the coverage a Bitemporal acquisition holds is stored state the
    document does not state.
    """
    for submission in submissions:
        if submission.kind == "target" and submission.refusal is None:
            _assert_golden_target(case, steps, submissions, submission)
            continue
        if submission.kind != "keyed" or submission.refusal is not None:
            raise CaseFailure(
                f"{case.path.name}: {submission.pointer} is a "
                f"{'refused' if submission.refusal is not None else submission.kind} "
                f"submission, which only a `grading: state` scenario carries."
            )


def _assert_golden_target(
    case: Case,
    steps: tuple[_CompiledStep, ...],
    submissions: list[Submission],
    target: Submission,
) -> None:
    entity, key = target.entity, target.key
    assert entity is not None and key is not None  # a target submission names its object
    where = f"{case.path.name}: {target.pointer}"
    group = steps[target.step].group
    if case.concurrency_mode == "locking" and any(
        axis.dimension == "valid-time" for axis in temporal_axes(entity.runtime_facts)
    ):
        raise CaseFailure(
            f"{where} is a Locking target submission of a Bitemporal Entity, whose acquired "
            f"coverage only a `grading: state` scenario leaves unstated."
        )
    for other in submissions:
        if other is not target and steps[other.step].group == group and other.names(entity, key):
            raise CaseFailure(
                f"{where} is a target submission of an object {other.pointer} also writes in "
                f"its group, which only a `grading: state` scenario carries."
            )
    for step in steps[: target.step]:
        if (
            isinstance(step, _RowPublishingStep)
            and step.group == group
            and _observes(case, step, entity, key)
        ):
            raise CaseFailure(
                f"{where} is a target submission of an object scenario[{step.index}] of its "
                f"group observed, which only a `grading: state` scenario carries."
            )


def _observes(case: Case, step: _RowPublishingStep, entity: Entity, key: Mapping[str, Any]) -> bool:
    """Whether the find *step* may have returned a row of the object *key* names.

    Object identity is the inheritance family's. A find reaching that family
    through an include path may have returned the object below its roots, which
    its document need not state, so it is taken to have; one rooted in that
    family returned it unless its stated root rows omit it.
    """
    found = case.scenario[step.index]
    query = found.get("objectQuery")
    if not isinstance(query, Mapping):
        return False
    family = Family(case.model.entity_defs)
    identity = family.root_of(entity.canonical_name)
    reached = (
        family.relationship_target(segment.get("rel"))
        for path in query.get("includes") or ()
        for segment in path.get("segments") or ()
    )
    if any(target is not None and family.root_of(target) == identity for target in reached):
        return True
    if family.root_of(str(query.get("target"))) != identity:
        return False
    keyed = [attribute for attribute in entity.attributes if attribute.get("primaryKey")]
    if "expectRows" in found:
        rows, spelling = found["expectRows"] or (), "column"
    elif isinstance(found.get("expectGraph"), Mapping):
        rows, spelling = next(iter(found["expectGraph"].values()), ()), "name"
    else:
        return True
    return any(
        isinstance(row, Mapping)
        and all(
            write_value_equal(row.get(attribute[spelling]), key[attribute["name"]])
            for attribute in keyed
        )
        for row in rows
    )


def _unit_fates(
    case: Case, steps: tuple[_CompiledStep, ...], *, state_graded: bool
) -> dict[str, UnitFate]:
    """Each `uow` group's fate, read off ``then.units``.

    A golden-graded group the case states no fate for commits; a state-graded
    case states every group's. A flush failure is reported where the group's
    last flush runs: at its last step where that is a find with writes pending
    before it or a write step whose last flush a predicate submission ran, and
    otherwise at commit, which flushes what is still pending. Every submission
    of a group states the same instant, because one unit of work holds one
    Transaction Instant.
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
        flushes = _group_flushes(members)
        fates[label] = UnitFate(
            label=label,
            steps=tuple(step.index for step in members),
            rolls_back=fate.get("outcome") == "rolledBack",
            flushes=flushes,
            flush_failure=_flush_failure(case, label, members, flushes, fate.get("flushFailure")),
            instant=_group_instant(case, label, members),
        )
    return fates


def _flush_failure(
    case: Case,
    label: str,
    members: list[_CompiledStep],
    flushes: tuple[GroupFlush, ...],
    authored: Any,
) -> FlushFailure | None:
    if not isinstance(authored, Mapping):
        return None
    candidates: dict[int | Literal["commit"], GroupFlush] = {}
    if flushes and flushes[-1].at in ("commit", members[-1].index):
        candidates[flushes[-1].at] = flushes[-1]
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
    failing = candidates[authored["at"]]
    return FlushFailure(
        at=authored["at"],
        site=failing.site,
        entity=case.model.entity(str(authored.get("entity", ""))),
        key=dict(authored.get("key") or {}),
        shortfall=authored.get("shortfall"),
        error=authored.get("error"),
        flushed=failing.flushed,
    )


def _group_flushes(members: list[_CompiledStep]) -> tuple[GroupFlush, ...]:
    """Each nonempty Flush a group runs, in order.

    A find flushes what is pending before it reads; a predicate write that
    writes something — a direct one, or a buffered predicate submission —
    flushes what is pending and executes in that Flush, so its Flush is nonempty
    whatever was pending; one writing nothing runs nothing and leaves what is
    pending as it was. The commit flushes what is still pending after the last
    step, and its Flush belongs to that step.
    """
    flushes: list[GroupFlush] = []
    pending: list[str] = []
    for step in members:
        if isinstance(step, _GroupedWrite):
            if step.runs_flush:
                flushes.append(GroupFlush(step.index, step.index, tuple(pending)))
                pending = []
            for submission in step.submissions:
                if submission.refusal is not None or submission.empty:
                    continue
                pending.append(submission.pointer)
                if submission.flushes:
                    flushes.append(GroupFlush(step.index, step.index, tuple(pending)))
                    pending = []
        elif isinstance(step, _RowPublishingStep) and pending:
            flushes.append(GroupFlush(step.index, step.index, tuple(pending)))
            pending = []
    if pending:
        flushes.append(GroupFlush(members[-1].index, "commit", tuple(pending)))
    return tuple(flushes)


def _assert_statement_placement(
    case: Case, steps: tuple[_CompiledStep, ...], units: Mapping[str, UnitFate]
) -> None:
    """Refuse a golden listed anywhere but at the step whose call presented it
    (`m-case-format` *Which step a statement belongs to*).

    A keyed write step that is not its group's last presents nothing of its
    own, since its writes wait for a later step's Flush; a native key
    reservation would be presented at its insert's own call, so a statement
    tagged ``purpose: reservation`` is passed over. A find lists a ``flush``
    exactly when its group has writes pending, since its call then runs one.
    """
    for fate in units.values():
        flushed_at = {flush.at for flush in fate.flushes}
        for index in fate.steps:
            step = steps[index]
            if isinstance(step, _GroupedWrite) and not step.runs_flush:
                own = [
                    entry
                    for entry in step.statements.entries
                    if not (isinstance(entry, Mapping) and entry.get("purpose") == "reservation")
                ]
                if own and index != fate.last_step:
                    raise CaseFailure(
                        f"{case.path.name}: scenario[{index}] lists {len(own)} golden "
                        f"statement(s), but it is a keyed write step before its group's last, "
                        f"whose call presents none: its writes belong to the step whose call "
                        f"presents the Flush delivering them."
                    )
            elif isinstance(step, _RowPublishingStep):
                pending = index in flushed_at
                if bool(step.flush.entries) != pending:
                    raise CaseFailure(
                        f"{case.path.name}: scenario[{index}] "
                        + (
                            "lists a `flush`, but its group has no writes pending, so its "
                            "call runs no Flush."
                            if not pending
                            else "lists no `flush`, but its group has writes pending, which "
                            "its call flushes before it reads."
                        )
                    )


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
    written: set[PhysicalTable] = set()
    for submission in submissions:
        if submission.empty:
            continue
        if submission.entity is not None:
            written.add(case.entity_table(submission.entity.canonical_name, None))
        else:
            target = submission.entry.get("target") or {}
            written.add(
                case.entity_table(
                    case.model.entity(str(target.get("entity", ""))).canonical_name, None
                )
            )
    unstated = [str(table) for table in sorted(written - set(case.expected_table_state))]
    if unstated:
        raise CaseFailure(
            f"{case.path.name}: then.tableState states no rows for {unstated}, which a "
            f"submission writes; a state-graded case states every table it writes."
        )


def _write_entries(step: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """One write step's own buffered entries, or none.

    A buffered submission list contributes entries; a predicate-selected mapping
    is graded separately from that buffer.
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


def _assert_identity_anchor(case: Case, index: int, step: Mapping[str, Any]) -> None:
    """Refuse a snapshot identity observable naming anything but an earlier step."""
    identity = step.get("sameObjectAs")
    if identity is None:
        return
    if step.get("action") != "access":
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].sameObjectAs is only a snapshot access observable"
        )
    if not isinstance(identity, int) or not names_earlier_step(identity, index):
        raise CaseFailure(
            f"{case.path.name}: scenario[{index}].sameObjectAs={identity!r} is not a real "
            f"EARLIER step (0 <= source < {index}); an identity claim names the object an "
            f"earlier step observed."
        )
