"""The Keyed Write Validation Order, stated once and asserted of both representations.

Every keyed verb runs one order, and that order is what a caller observes as
refusal precedence (`python.md` §5 "The Keyed Write Validation Order is one
order"). One private ingress owns it and each representation answers only source
facts into it, so what a row here fixes is the ANSWER — the refusal's class,
code, message, and the point it landed at, or the DML a completing write emitted
— and each row asserts that same answer of the Typed verbs and of ``tx.wire``'s
in turn. Nothing here compares one representation to the other: two lanes
agreeing is what the order used to have to be characterized for, and what the
ingress now makes structural.

The expectations are stated as the order's own rules rather than as a golden per
row. :func:`_applicability_refusal` is the applicability half — which verb a
target's As-Of Axes admit and which window it may state — and reads as the three
stages that decide it, in the order the ingress runs them. What each admitted verb then emits is
:data:`_STATEMENTS`, keyed by the target's temporal profile, because how many
statements a write lowers to is a fact about the profile rather than about the
fixture.

A shape only one representation can express carries one assertion instead of two,
beside the row that proves the other representation cannot express it. A
malformed change document, an undeclared member, and an illegal assignment are
Wire-only because ``edit()`` judges a Typed assignment before ``tx.update()``
receives a value, and the Typed rows here assert that pre-emption over each
provenance rather than leaving it unstated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Final, cast

import pytest
from _keyed_write_drivers import (
    ACCOUNT_TARGET,
    BALANCE_TARGET,
    BLANK_CONTACT_TARGET,
    CONCURRENCIES,
    CONTACT_TARGET,
    DOCUMENT_TARGETS,
    PERSON_TARGET,
    POSITION_TARGET,
    REPRESENTATIONS,
    TARGETS,
    TX_PIN,
    UNTIL,
    VALID_FROM,
    VERBS,
    Answer,
    Change,
    Completed,
    Concurrency,
    Profile,
    Representation,
    Scenario,
    Source,
    Target,
    Verb,
    Window,
    answer,
    outcome,
    reachable,
)

from parallax.core.entity import EditError
from parallax.core.opt_lock import UnobservedVersionError
from parallax.core.unit_work import WriteInstructionError, WritePlanningError
from parallax.snapshot.handle import (
    KeyedWriteValueError,
    TransactionTimePinReadOnlyError,
    WriteEvidenceError,
)

_SOURCE_VERBS: tuple[Verb, ...] = (
    "update",
    "update_until",
    "delete",
    "terminate",
    "terminate_until",
)
_INSERT_VERBS: tuple[Verb, ...] = ("insert", "insert_until")
_BOUNDED_VERBS: tuple[Verb, ...] = ("insert_until", "update_until", "terminate_until")
_UPDATE_VERBS: frozenset[str] = frozenset({"update", "update_until"})
_ALL_TARGETS: tuple[Target, ...] = TARGETS + DOCUMENT_TARGETS

_MUTATIONS: Final[Mapping[Verb, str]] = {
    "insert": "insert",
    "insert_until": "insertUntil",
    "update": "update",
    "update_until": "updateUntil",
    "delete": "delete",
    "terminate": "terminate",
    "terminate_until": "terminateUntil",
}
"""The mutation token a refusal names, per verb: refusals about a target's own
rules spell the mutation, and the two applicability ones spell the method."""

_STATEMENTS: Final[Mapping[tuple[Profile, Verb], int]] = {
    ("non_temporal", "insert"): 1,
    ("non_temporal", "update"): 1,
    ("non_temporal", "delete"): 1,
    ("transaction_time", "insert"): 1,
    ("transaction_time", "update"): 2,
    ("transaction_time", "terminate"): 1,
    ("bitemporal", "insert"): 1,
    ("bitemporal", "insert_until"): 1,
    ("bitemporal", "update"): 3,
    ("bitemporal", "update_until"): 4,
    ("bitemporal", "terminate"): 2,
    ("bitemporal", "terminate_until"): 3,
}
"""How much DML each admitted verb emits, by the target's temporal profile.

A non-temporal row is written in place. A Transaction-Time-Only update closes the
current milestone and opens the next; a `terminate` only closes. A Bitemporal
write over an OBSERVED rectangle additionally splits it around the window it
states, which is why those counts are the largest and why a bounded verb's differ
from its plain peer's; an `insert` observes nothing and opens one rectangle, so it
costs the one statement every insert costs. Every pair this omits is one
:func:`_applicability_refusal` refuses.
"""


def _short(target: Target) -> str:
    """``target``'s Entity name as a refusal spells it, without its namespace."""
    return target.entity.rsplit(".", 1)[-1]


def _wrote(statements: int) -> Answer:
    return Answer(None, None, None, None, statements)


def _refused(
    error: type[Exception], message: str, *, code: str | None = None, statements: int = 0
) -> Answer:
    """A refusal the VERB raised, stated in full."""
    return Answer(error, code, message, "verb", statements)


def _refused_at_flush(error: type[Exception], message: str, *, statements: int) -> Answer:
    """A refusal the FLUSH raised over a write this order admitted, stated in
    full beside the DML the transaction had already emitted when it landed.

    Neither planning class carries a code, so the message is the only thing
    separating two verdicts about two different rules.
    """
    return Answer(error, None, message, "flush", statements)


def _unobserved_version(target: Target) -> Answer:
    """What a versioned row settled bare answers when the planner reaches it."""
    return _refused_at_flush(
        UnobservedVersionError,
        f"{_short(target)}: a keyed update/delete of a versioned row requires the version its "
        "source value observed (a prior find) — the framework never issues an implicit "
        "resolving read on behalf of a keyed write",
        statements=1,
    )


def _unobserved_milestone(scenario: Scenario) -> Answer:
    """What a milestoning write settled bare answers when the planner reaches it."""
    return _refused_at_flush(
        WritePlanningError,
        f"{_short(scenario.target)!r}: a temporal {_MUTATIONS[scenario.verb]!r} closes the "
        "current milestone, and every close requires the Temporal Observation it addresses, "
        "gates on, and carries state forward from (m-unit-work; m-opt-lock)",
        statements=1,
    )


def _applicability_refusal(scenario: Scenario, *, statements: int = 0) -> Answer | None:
    """The refusal ``scenario``'s target gives its verb, or ``None`` for a call the
    target admits and whose window it accepts.

    Three stages of the order, in the order they run. ``delete`` states no
    Valid-Time bound in any spelling, so a target that milestones its rows judges
    the VERB before the window gate is reached at all. The window gate then
    measures the bound a bounded verb states, which only a Bitemporal target
    admits, and orders the pair it accepted. A boundless ``terminate`` states
    nothing for that gate to measure and reaches preparation, which is where the
    converse half of applicability — a milestone verb aimed at a target deriving
    no As-Of Axis — is answered.

    ``statements`` is the DML already emitted when the refusal lands, which is
    non-zero only where a force-flushing read ran ahead of the verb.
    """
    target, verb = scenario.target, scenario.verb
    if verb == "delete" and target.profile != "non_temporal":
        return _refused(
            WriteInstructionError,
            f"Temporal objects like {_short(target)!r} do not support 'delete', "
            "which physically removes rows. Use 'terminate' instead.",
            statements=statements,
        )
    if verb in _BOUNDED_VERBS and target.profile != "bitemporal":
        shape = (
            "a Transaction-Time-Only" if target.profile == "transaction_time" else "a non-temporal"
        )
        return _refused(
            WriteInstructionError,
            f"{_short(target)}: {shape} {_MUTATIONS[verb]!r} takes no valid_from "
            f"({_short(target)!r} declares no Valid-Time dimension to bound)",
            statements=statements,
        )
    if verb in _BOUNDED_VERBS and scenario.window == "reversed":
        return _refused(
            WriteInstructionError,
            f"{_short(target)}: {_MUTATIONS[verb]!r} requires valid_from < until "
            f"(python.md §5) — got valid_from={UNTIL!r}, until={VALID_FROM!r}",
            statements=statements,
        )
    if verb == "terminate" and target.profile == "non_temporal":
        return _refused(
            WriteInstructionError,
            f"Non-temporal objects like {_short(target)!r} do not support 'terminate', "
            "which closes a row's history instead of removing it. Use 'delete' instead.",
            statements=statements,
        )
    return None


def _answers(scenario: Scenario, expected: Answer) -> None:
    """Assert both representations answer ``scenario`` with ``expected``.

    One expectation asserted twice rather than one lane measured against the
    other: a row that compared them would pass on two lanes that had drifted
    together, and the ingress is what makes their agreeing structural.

    Every expectation is one fixed :class:`Answer`, the repeated-insert refusal
    included: its advice clause is spelled from the interface that OPENED the
    row, which the scenario states, so it is fixed for a row rather than varying
    with the lane the row is driven on.
    """
    for representation in REPRESENTATIONS:
        if reachable(scenario, representation):
            assert answer(scenario, representation) == expected, representation


def _grid(
    targets: tuple[Target, ...] = TARGETS,
    verbs: tuple[Verb, ...] = VERBS,
    *,
    source: Source = "participating",
    change: Change = "ordinary",
    window: Window = "stated",
) -> tuple[Scenario, ...]:
    return tuple(
        Scenario(
            target=target,
            verb=verb,
            concurrency=concurrency,
            source=source,
            change=change,
            window=window,
        )
        for target in targets
        for verb in verbs
        for concurrency in CONCURRENCIES
    )


# --------------------------------------------------------------------------- #
# The valid grid: every verb against every temporality and every gate source,  #
# under both Concurrency Preferences. An invalid verb/temporality pair is a    #
# refusal row rather than an omission.                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario", _grid(targets=_ALL_TARGETS), ids=str)
def test_one_verb_over_a_participating_source_answers_its_target(scenario: Scenario) -> None:
    _answers(
        scenario,
        _applicability_refusal(scenario)
        or _wrote(_STATEMENTS[scenario.target.profile, scenario.verb]),
    )


# --------------------------------------------------------------------------- #
# The change axis. A net-zero chain and an untouched copy are the two ways a   #
# keyed update names members and changes nothing; both reduce to the same      #
# no-op the Wire lane reaches by comparing against what its source published,  #
# which is what licenses one comparison rule behind both representations. The  #
# document targets carry it past a scalar: a Value Object occurrence with a    #
# nested occurrence and a nested many, and a member stored absent whose        #
# restoration states an explicit null an untouched copy never names.           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    _grid(targets=_ALL_TARGETS, verbs=("update", "update_until"), change="net_zero")
    + _grid(targets=_ALL_TARGETS, verbs=("update", "update_until"), change="untouched"),
    ids=str,
)
def test_a_change_set_that_changes_nothing_buffers_nothing(scenario: Scenario) -> None:
    _answers(scenario, _applicability_refusal(scenario) or _wrote(0))


# --------------------------------------------------------------------------- #
# The source axis: a standalone read, whose evidence a participating read's    #
# shared lock would have supplied. Under an effective Locking strategy it      #
# licenses nothing; where the target supplies its own gate and the preference  #
# is Optimistic, the retained observation is the evidence and the write runs.  #
# --------------------------------------------------------------------------- #
def _unusable_evidence(target: Target) -> Answer:
    return _refused(
        WriteEvidenceError,
        f"write-evidence-unavailable: {target.entity}: the Locking strategy licenses this "
        "write through the shared row lock a read of THIS transaction holds, and the value "
        "handed to the verb came from no such read; read the row through this transaction "
        "and write what that read returned",
        code="write-evidence-unavailable",
    )


@pytest.mark.parametrize("scenario", _grid(verbs=_SOURCE_VERBS, source="standalone"), ids=str)
def test_a_standalone_source_answers_the_strategy_its_target_derives(scenario: Scenario) -> None:
    target = scenario.target
    locking = scenario.concurrency == "locking" or target.gate == "none"
    _answers(
        scenario,
        _applicability_refusal(scenario)
        or (
            _unusable_evidence(target)
            if locking
            else _wrote(_STATEMENTS[target.profile, scenario.verb])
        ),
    )


# --------------------------------------------------------------------------- #
# A finite Transaction-Time pin is read-only, and the refusal precedes         #
# everything the model or the change set decides — on the insert door too,     #
# whose argument here is the published node itself.                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    tuple(Scenario(target=POSITION_TARGET, verb=verb, source="pinned") for verb in VERBS),
    ids=str,
)
def test_a_pinned_source_is_read_only_whatever_verb_was_aimed_at_it(scenario: Scenario) -> None:
    _answers(
        scenario,
        _refused(
            TransactionTimePinReadOnlyError,
            f"{scenario.target.entity}: the write's source view is pinned at the finite "
            f"Transaction-Time instant {TX_PIN.isoformat()} and is read-only — the "
            "Transaction-Time past records what the system knew and is never rewritten "
            "(transaction-time-pin-read-only); read the current milestone "
            "(Transaction Time Latest) to mutate it",
            code="transaction-time-pin-read-only",
        ),
    )


# --------------------------------------------------------------------------- #
# The window axis. A reversed window is refused whatever else the call is,     #
# including when the change set nets to zero — window before no-op, in both    #
# representations.                                                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    _grid(verbs=_BOUNDED_VERBS, window="reversed")
    + _grid(verbs=("update_until",), window="reversed", change="net_zero"),
    ids=str,
)
def test_a_reversed_window_is_refused_before_the_change_set_is_weighed(
    scenario: Scenario,
) -> None:
    refusal = _applicability_refusal(scenario)
    assert refusal is not None  # every bounded verb states the reversed pair
    _answers(scenario, refusal)


# --------------------------------------------------------------------------- #
# The provenance axis. One buffered-insert ledger serves both representations, #
# so a write over a row THIS unit of work opened answers the same way whoever  #
# opened it: the pair coalesces into the insert's own statement, and a         #
# destructive verb cancels it to no DML at all. Three of the four crossings    #
# write the source the insert itself yielded; the fourth needs a read to       #
# produce a Wire source from a Typed insert, and that read force-flushes,      #
# which is a different scenario rather than the same one spelled differently   #
# (see `reachable`).                                                          #
# --------------------------------------------------------------------------- #
def _over_a_buffered_insert(scenario: Scenario) -> Answer:
    """What a write over a row this unit of work still holds buffered answers.

    The insert is the only statement either way: an assignment merges into the
    row the insert opens, and a `delete` or a `terminate` cancels the pair
    outright, so the transaction commits nothing at all.
    """
    if scenario.verb in _UPDATE_VERBS:
        return _wrote(1)
    return _wrote(0)


@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, change=change, opened_by=opener)
        for target in _ALL_TARGETS
        for verb in _SOURCE_VERBS
        for change in ("ordinary", "net_zero")
        for opener in REPRESENTATIONS
    ),
    ids=str,
)
def test_a_same_transaction_insert_licenses_the_write_whoever_opened_it(
    scenario: Scenario,
) -> None:
    _answers(scenario, _applicability_refusal(scenario) or _over_a_buffered_insert(scenario))


# --------------------------------------------------------------------------- #
# The same provenance, reached through a read of the row the insert opened.    #
# The read force-flushes, so the pair no longer coalesces — and this is the    #
# only route by which a Wire verb writes a row a TYPED insert opened, so it is #
# where all four crossings exist.                                             #
#                                                                             #
# The exemption is what makes it interesting: a flush retires nothing from the #
# ledger, so the write that follows is STILL exempted from resolving           #
# evidence and settles bare, discarding the observation the read supplied. The #
# flush then has nothing to gate on and refuses — a versioned row for its      #
# missing version, a temporal one for its missing observation — where an       #
# unversioned Non-Temporal row, which observes no state at all, writes.        #
# --------------------------------------------------------------------------- #
def _over_a_reread_insert(scenario: Scenario) -> Answer:
    if scenario.verb in _UPDATE_VERBS and scenario.change == "net_zero":
        return _wrote(1)
    if scenario.target.profile != "non_temporal":
        return _unobserved_milestone(scenario)
    if scenario.target.gate == "version":
        return _unobserved_version(scenario.target)
    return _wrote(2)


@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, change=change, source="reread", opened_by=opener)
        for target in _ALL_TARGETS
        for verb in _SOURCE_VERBS
        for change in ("ordinary", "net_zero")
        for opener in REPRESENTATIONS
    ),
    ids=str,
)
def test_a_write_over_a_reread_insert_settles_bare_whoever_opened_it(
    scenario: Scenario,
) -> None:
    _answers(
        scenario, _applicability_refusal(scenario, statements=1) or _over_a_reread_insert(scenario)
    )


# --------------------------------------------------------------------------- #
# The insert family's half of the same ledger. The exemption above lets an     #
# update follow this unit of work's own insert; the refusal here stops a       #
# second insert of that object, whichever representation opened the row and   #
# whichever spelled the repeat — a fresh payload needs no source, so every one #
# of the four crossings is reachable, buffered or flushed. It stands after     #
# preparation, so a target that admits no such verb answers that first.       #
# --------------------------------------------------------------------------- #
_REPEATED_INSERT_ADVICE: Final[Mapping[Representation, str]] = {
    "typed": (
        "write the change with `tx.update(inserted.edit(...))`, where `inserted` is the value "
        "the first insert took"
    ),
    "wire": (
        "write the change with `tx.wire.update(opened, {...})`, where `opened` is the node "
        "the first insert answered"
    ),
}
"""The update verb the refusal redirects to, keyed by the interface that OPENED
the row — the one clause of the message that is a representation's rather than
the order's, and the opener's rather than the refuser's. Each names the carrier
the FIRST insert produced, which is the only one that exists: two instances of
one primary key open one row, `tx.insert` answers nothing, and a Wire payload is
no keyed source at all."""


def _repeated_insert(scenario: Scenario, *, statements: int = 0) -> Answer:
    """What a second insert of an object this unit of work already opened answers."""
    # Only an opened row can be re-opened, so every row reaching here states its
    # opener — which is the interface whose update verb the advice names.
    assert scenario.opened_by is not None
    return _refused(
        KeyedWriteValueError,
        f"write-value-already-stored: {scenario.target.entity}: "
        f"{_MUTATIONS[scenario.verb]!r} was handed a value naming an object this "
        "transaction already buffered an insert of, so there is no row to open; "
        f"{_REPEATED_INSERT_ADVICE[scenario.opened_by]}",
        code="write-value-already-stored",
        statements=statements,
    )


@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, opened_by=opener)
        for target in _ALL_TARGETS
        for verb in _INSERT_VERBS
        for opener in REPRESENTATIONS
    ),
    ids=str,
)
def test_a_second_insert_of_an_object_this_unit_of_work_opened_is_refused_whoever_opened_it(
    scenario: Scenario,
) -> None:
    _answers(scenario, _applicability_refusal(scenario) or _repeated_insert(scenario))


@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, source="reread", opened_by=opener)
        for target in TARGETS
        for verb in _INSERT_VERBS
        for opener in REPRESENTATIONS
    ),
    ids=str,
)
def test_a_flushed_insert_still_refuses_a_second_insert_of_its_object(scenario: Scenario) -> None:
    # A flush retires nothing from the ledger — only a destructive write that
    # cancels an insert still PENDING in the buffer does, and a flushed insert is
    # not pending — so the participating read that force-flushed the insert
    # leaves it recorded: the row the store now holds is refused a second opening
    # at the verb rather than reaching the database as a primary-key violation,
    # and the insert's own statement is the only DML.
    _answers(
        scenario,
        _applicability_refusal(scenario, statements=1) or _repeated_insert(scenario, statements=1),
    )


# --------------------------------------------------------------------------- #
# Two defects at once: which one the caller hears.                            #
# --------------------------------------------------------------------------- #
_PINNED_AND_REVERSED: Final = Scenario(
    target=POSITION_TARGET,
    verb="update_until",
    source="pinned",
    window="reversed",
    label="pin-beats-window",
)


def test_a_pinned_source_beats_the_window_it_stated() -> None:
    _answers(
        _PINNED_AND_REVERSED,
        _refused(
            TransactionTimePinReadOnlyError,
            f"{POSITION_TARGET.entity}: the write's source view is pinned at the finite "
            f"Transaction-Time instant {TX_PIN.isoformat()} and is read-only — the "
            "Transaction-Time past records what the system knew and is never rewritten "
            "(transaction-time-pin-read-only); read the current milestone "
            "(Transaction Time Latest) to mutate it",
            code="transaction-time-pin-read-only",
        ),
    )


@pytest.mark.parametrize(
    "scenario",
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            change="net_zero",
            label="a-net-zero-write-needs-no-evidence",
        ),
        Scenario(
            target=CONTACT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            change="net_zero",
            label="a-net-zero-document-write-needs-no-evidence",
        ),
    ),
    ids=str,
)
def test_a_net_zero_change_set_is_dropped_before_evidence_is_asked_for(
    scenario: Scenario,
) -> None:
    # The source could license nothing, and the write asks it for nothing: the
    # no-op return precedes the evidence question, so a chain that took itself
    # back over an unusable source is silence rather than a refusal.
    _answers(scenario, _wrote(0))


# --------------------------------------------------------------------------- #
# Two defects at once over a source this unit of work inserted, crossed over   #
# every opener the source admits: whichever representation opened the row, the #
# window refusal and the net-zero no-op land in the same order.                #
# --------------------------------------------------------------------------- #
_INSERT_SOURCE_DEFECTS: Final[tuple[tuple[Scenario, Answer], ...]] = (
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            window="reversed",
            label="window-beats-the-insert-exemption",
        ),
        _wrote(0),
    ),
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            window="reversed",
            opened_until=True,
            label="window-beats-a-bounded-insert-exemption",
        ),
        _wrote(0),
    ),
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            window="reversed",
            change="net_zero",
            label="window-beats-a-net-zero-insert-source",
        ),
        _wrote(0),
    ),
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            window="reversed",
            source="reread",
            label="window-beats-a-reread-insert-source",
        ),
        _wrote(1),
    ),
    (
        Scenario(
            target=POSITION_TARGET,
            verb="insert_until",
            window="reversed",
            label="window-beats-the-repeated-insert-refusal",
        ),
        _wrote(0),
    ),
)
"""Each row's second half is the DML the transaction had already emitted when the
window refusal landed: nothing at all while the insert is still buffered, and the
insert's own statement once a participating read has force-flushed it. The last
row is the insert door's: a reversed window on a second opening of an object is
heard before the ledger is asked about that object."""


@pytest.mark.parametrize(
    ("scenario", "already"), _INSERT_SOURCE_DEFECTS, ids=lambda value: str(value)
)
@pytest.mark.parametrize("opener", REPRESENTATIONS)
def test_the_window_is_judged_over_an_inserted_source_too(
    scenario: Scenario, already: Answer, opener: Representation
) -> None:
    opened = replace(scenario, opened_by=opener)
    refusal = _applicability_refusal(opened, statements=already.statements)
    assert refusal is not None  # every row above states a reversed window
    _answers(opened, refusal)


@pytest.mark.parametrize(
    ("scenario", "statements"),
    (
        (
            Scenario(
                target=ACCOUNT_TARGET,
                verb="update",
                change="net_zero",
                label="a-net-zero-write-of-an-inserted-row",
            ),
            1,
        ),
        (
            Scenario(
                target=ACCOUNT_TARGET,
                verb="update",
                change="net_zero",
                source="reread",
                label="a-net-zero-write-of-a-reread-inserted-row",
            ),
            1,
        ),
    ),
    ids=lambda value: str(value),
)
@pytest.mark.parametrize("opener", REPRESENTATIONS)
def test_a_net_zero_write_of_an_inserted_row_leaves_the_insert_alone(
    scenario: Scenario, statements: int, opener: Representation
) -> None:
    _answers(replace(scenario, opened_by=opener), _wrote(statements))


# --------------------------------------------------------------------------- #
# The Wire-only half of the dual-defect set: a document a Typed caller cannot  #
# author, and a source only a Wire verb can be handed without provenance. Each #
# row states the one expectation, and the Typed rows below state where that    #
# same authoring is refused instead. The insert row is the payload's: a member #
# the Typed constructor refuses one layer earlier is preparation's refusal on  #
# the Wire door, and preparation is heard before the ledger is asked whether   #
# the object the payload names is already opening.                            #
#                                                                             #
# The last two rows fix where the authored document's own shape sits in the    #
# order: whether a document was STATED at all needs neither the source nor the #
# model and is heard over a source that lost its provenance, while what its    #
# members NAME is a judgement about the model that the source is resolved      #
# before.                                                                     #
# --------------------------------------------------------------------------- #
_MALFORMED: tuple[tuple[Scenario, str], ...] = (
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            window="reversed",
            wire_changes={"nope": 1},
            label="window-beats-an-undeclared-member",
        ),
        "requires valid_from < until",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            opened_by="wire",
            wire_changes={"nope": 1},
            label="an-undeclared-member-beats-the-insert-exemption",
        ),
        "undeclared member(s) ['nope']",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="insert",
            opened_by="wire",
            wire_changes={"version": 9},
            label="a-framework-owned-member-beats-the-repeated-insert-refusal",
        ),
        "framework-owned fields may not be assigned",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            wire_changes={"version": 9},
            label="an-illegal-assignment-beats-unusable-evidence",
        ),
        "framework-owned fields may not be assigned",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            wire_changes={"nope": 1},
            label="an-undeclared-member-beats-unusable-evidence",
        ),
        "undeclared member(s) ['nope']",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            wire_changes=cast("Mapping[str, object]", {1: "x"}),
            label="a-malformed-document-beats-everything",
        ),
        "is not one",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            lost_provenance=True,
            wire_changes=cast("Mapping[str, object]", {1: "x"}),
            label="a-malformed-document-beats-a-source-that-lost-its-provenance",
        ),
        "is not one",
    ),
    (
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            lost_provenance=True,
            wire_changes={"nope": 1},
            label="a-source-that-lost-its-provenance-beats-an-undeclared-member",
        ),
        "carries no such provenance",
    ),
)


@pytest.mark.parametrize(("scenario", "expected"), _MALFORMED, ids=lambda value: str(value))
def test_malformed_wire_input_earns_a_static_refusal(scenario: Scenario, expected: str) -> None:
    refused = answer(scenario, "wire")
    assert refused.error is WriteInstructionError
    assert refused.phase == "verb"
    assert refused.message is not None
    assert expected in refused.message
    assert refused.statements == 0


# --------------------------------------------------------------------------- #
# The Typed half of those same three authorings, over the provenances the Wire #
# rows above cross: a source a read published, and a source this unit of work  #
# opened through either representation. `edit()` refuses each before           #
# `tx.update()` receives a value, so the write reaches none of the stages the  #
# Wire lane refuses at and the transaction leaves nothing to undo.             #
# --------------------------------------------------------------------------- #
_TYPED_AUTHORINGS: tuple[tuple[Mapping[str, object], str], ...] = (
    ({"nope": 1}, "edit-unknown-member"),
    ({"version": 9}, "edit-framework-owned"),
    ({"id": 2}, "edit-primary-key"),
)

_TYPED_AUTHORING_SOURCES: tuple[Scenario, ...] = (
    Scenario(target=ACCOUNT_TARGET, verb="update", label="over-a-read-source"),
    Scenario(
        target=ACCOUNT_TARGET, verb="update", opened_by="wire", label="over-a-wire-insert-source"
    ),
    Scenario(
        target=ACCOUNT_TARGET, verb="update", opened_by="typed", label="over-a-typed-insert-source"
    ),
)


@pytest.mark.parametrize(
    ("assignment", "expected"),
    _TYPED_AUTHORINGS,
    ids=("undeclared-member", "framework-owned-member", "primary-key-member"),
)
@pytest.mark.parametrize("source", _TYPED_AUTHORING_SOURCES, ids=str)
def test_the_typed_lane_refuses_that_authoring_before_a_verb_receives_it(
    source: Scenario, assignment: Mapping[str, object], expected: str
) -> None:
    refused = answer(replace(source, typed_changes=assignment), "typed")
    assert refused.error is EditError
    assert refused.phase == "verb"
    assert refused.message is not None
    assert expected in refused.message
    assert refused.statements == 0


# --------------------------------------------------------------------------- #
# `terminate` against a target with no as-of axis, when the source's evidence  #
# is also unusable. The milestone-verb refusal is the static one and precedes  #
# the evidence question, in both representations: preparation runs before      #
# evidence resolves, so the caller hears which verb the target takes rather    #
# than that the value it was handed proves nothing.                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    (
        Scenario(
            target=ACCOUNT_TARGET, verb="terminate", source="standalone", concurrency="locking"
        ),
        Scenario(
            target=PERSON_TARGET, verb="terminate", source="standalone", concurrency="locking"
        ),
    ),
    ids=str,
)
def test_a_milestone_verb_on_a_non_temporal_target_beats_unusable_evidence(
    scenario: Scenario,
) -> None:
    refusal = _applicability_refusal(scenario)
    assert refusal is not None  # `terminate` closes a history a non-temporal row has none of
    _answers(scenario, refusal)


# --------------------------------------------------------------------------- #
# `delete` against a temporal target. `delete` physically removes rows and     #
# carries no temporal meaning, so a target that milestones its rows spells its #
# removal `terminate` and refuses `delete` at the verb, whichever              #
# representation asked and whatever the source (`python.md` §5) — including    #
# over a row this unit of work itself inserted, where the pair would otherwise #
# cancel and commit no DML at all rather than name the verb.                   #
# --------------------------------------------------------------------------- #
_TEMPORAL_DELETE_SOURCES: tuple[tuple[Source, Concurrency, Representation | None], ...] = (
    ("participating", "optimistic", None),
    ("standalone", "locking", None),
    ("participating", "optimistic", "wire"),
    ("participating", "optimistic", "typed"),
)

_TEMPORAL_DELETE_ROWS: tuple[Scenario, ...] = tuple(
    Scenario(target=target, verb="delete", source=source, concurrency=concurrency, opened_by=opener)
    for target in (BALANCE_TARGET, POSITION_TARGET)
    for source, concurrency, opener in _TEMPORAL_DELETE_SOURCES
) + tuple(
    # Only a Bitemporal target admits a bounded opener, and the exemption the
    # bounded insert records is the same one a plain insert records.
    Scenario(target=POSITION_TARGET, verb="delete", opened_by=opener, opened_until=True)
    for opener in REPRESENTATIONS
)


@pytest.mark.parametrize("scenario", _TEMPORAL_DELETE_ROWS, ids=str)
def test_a_temporal_target_refuses_delete_at_the_verb(scenario: Scenario) -> None:
    refusal = _applicability_refusal(scenario)
    assert refusal is not None  # a milestoning target spells its removal `terminate`
    _answers(scenario, refusal)


# --------------------------------------------------------------------------- #
# The one crossing no caller can spell, and the read that makes it spellable.  #
# --------------------------------------------------------------------------- #
def test_a_wire_verb_cannot_write_a_row_a_typed_insert_still_holds_buffered() -> None:
    scenario = Scenario(target=ACCOUNT_TARGET, verb="update", opened_by="typed")
    assert reachable(scenario, "typed")
    assert not reachable(scenario, "wire")
    assert reachable(replace(scenario, source="reread"), "wire")
    # An insert needs no source, so the same crossing is reachable for it.
    assert reachable(replace(scenario, verb="insert"), "wire")


def test_a_wire_read_of_a_typed_insert_flushes_it_before_the_write() -> None:
    scenario = Scenario(
        target=BLANK_CONTACT_TARGET, verb="update", source="reread", opened_by="typed"
    )
    emitted = outcome(scenario, "wire")
    assert isinstance(emitted, Completed)
    assert [type(call).__name__ for call in emitted.calls] == [
        "BeginCall",
        "WriteCall",
        "ReadCall",
        "WriteCall",
        "CommitCall",
    ]
