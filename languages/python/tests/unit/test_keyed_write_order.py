"""The Keyed Write Validation Order, characterized across both representations.

Every keyed verb runs one order, and that order is what a caller observes as
refusal precedence (`python.md` §5 "The Keyed Write Validation Order is one
order"). This suite drives each row through the Typed verbs and through
``tx.wire``'s against a scripted port and asserts that both answer it the same
way — every statement and boundary the transaction ran, or the class, code,
message, and phase of the refusal it raised — so the order is pinned once rather
than once per representation.

A shape only one representation can express carries one assertion instead of a
comparison, beside the row that proves the other representation cannot express
it. A malformed change document, an undeclared member, and an illegal assignment
are Wire-only because ``edit()`` judges a Typed assignment before ``tx.update()``
receives a value, and the Typed rows here assert that pre-emption rather than
leaving it unstated.

Two shapes are pinned per representation instead of compared, because the two
representations answer them differently: `terminate` against a target with no
as-of axis whose evidence is also unusable, and `delete` against a Bitemporal
target.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest
from _keyed_write_drivers import (
    ACCOUNT_TARGET,
    BLANK_CONTACT_TARGET,
    CONCURRENCIES,
    CONTACT_TARGET,
    DOCUMENT_TARGETS,
    PERSON_TARGET,
    POSITION_TARGET,
    REPRESENTATIONS,
    TARGETS,
    VERBS,
    Change,
    Completed,
    Outcome,
    Refused,
    Representation,
    Scenario,
    Source,
    Target,
    Verb,
    Window,
    outcome,
    reachable,
)

from _support.db_port import BeginCall, CommitCall
from parallax.core.entity import EditError

# The Typed `delete` verb reaches no window gate and the Wire one does, so a
# Bitemporal `delete` refuses differently by representation. The
# `test_a_bitemporal_delete_...` rows state each answer directly.
_BITEMPORAL_DELETE: frozenset[tuple[str, str]] = frozenset({("position", "delete")})

# `terminate` against a target with no as-of axis, when the source's evidence is
# also unusable: the milestone-verb refusal and the evidence refusal are both
# available, and the representations choose differently. The dual-defect row
# `test_a_milestone_verb_on_a_non_temporal_target_...` states each answer.
_MILESTONE_ON_NON_TEMPORAL: frozenset[tuple[str, str]] = frozenset(
    {("account", "terminate"), ("person", "terminate")}
)

_SOURCE_VERBS: tuple[Verb, ...] = (
    "update",
    "update_until",
    "delete",
    "terminate",
    "terminate_until",
)
_BOUNDED_VERBS: tuple[Verb, ...] = ("insert_until", "update_until", "terminate_until")
_ALL_TARGETS: tuple[Target, ...] = TARGETS + DOCUMENT_TARGETS


def _agrees(scenario: Scenario) -> None:
    """Assert both representations answer ``scenario`` identically."""
    assert outcome(scenario, "typed") == outcome(scenario, "wire")


def _crossings_agree(scenario: Scenario, crossings: int) -> None:
    """Assert every reachable opener/writer crossing of ``scenario`` answers alike.

    ``crossings`` is how many of the four the scenario's source admits, so a row
    states the reachability it relies on rather than silently covering fewer.
    """
    answers: dict[str, Outcome] = {
        f"{opener}-insert/{writer}-write": outcome(replace(scenario, opened_by=opener), writer)
        for opener in REPRESENTATIONS
        for writer in REPRESENTATIONS
        if reachable(replace(scenario, opened_by=opener), writer)
    }
    assert len(answers) == crossings, tuple(answers)
    first = next(iter(answers.values()))
    assert all(answer == first for answer in answers.values()), answers


def _grid(
    targets: tuple[Target, ...] = TARGETS,
    verbs: tuple[Verb, ...] = VERBS,
    *,
    exempt: frozenset[tuple[str, str]] = frozenset(),
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
        if (target.name, verb) not in exempt
    )


# --------------------------------------------------------------------------- #
# The valid grid: every verb against every temporality and every gate source,  #
# under both Concurrency Preferences. An invalid verb/temporality pair is a    #
# refusal row rather than an omission.                                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario", _grid(targets=_ALL_TARGETS, exempt=_BITEMPORAL_DELETE), ids=str
)
def test_one_verb_over_a_participating_source_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# The change axis. A net-zero chain and an untouched copy are the two ways a   #
# keyed update names members and changes nothing; both must reduce to the same #
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
def test_a_change_set_that_changes_nothing_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# The source axis: a standalone read, whose evidence a participating read's    #
# shared lock would have supplied. Under `locking` it licenses nothing, so the #
# row is the evidence refusal; under `optimistic` a versioned or temporal      #
# source supplies its own gate and the row is the ordinary write.              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    _grid(
        verbs=_SOURCE_VERBS,
        exempt=_BITEMPORAL_DELETE | _MILESTONE_ON_NON_TEMPORAL,
        source="standalone",
    ),
    ids=str,
)
def test_a_standalone_source_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# A finite Transaction-Time pin is read-only, and the refusal precedes         #
# everything the model or the change set decides.                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    tuple(Scenario(target=POSITION_TARGET, verb=verb, source="pinned") for verb in VERBS),
    ids=str,
)
def test_a_pinned_source_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


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
def test_a_reversed_window_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# The provenance axis. One buffered-insert ledger serves both representations, #
# so a write over a row THIS unit of work opened answers the same way whoever  #
# opened it. Three of the four crossings write the source the insert itself    #
# yielded; the fourth needs a read to produce a Wire source from a Typed       #
# insert, and that read force-flushes, which is a different scenario rather    #
# than the same one spelled differently (see `reachable`).                     #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, change=change)
        for target in _ALL_TARGETS
        for verb in _SOURCE_VERBS
        for change in ("ordinary", "net_zero")
        if (target.name, verb) not in _BITEMPORAL_DELETE
    ),
    ids=str,
)
def test_a_same_transaction_insert_licenses_the_write_whoever_opened_it(
    scenario: Scenario,
) -> None:
    _crossings_agree(scenario, crossings=3)


# --------------------------------------------------------------------------- #
# The same provenance, reached through a read of the row the insert opened.    #
# The read force-flushes, so the pair no longer coalesces — and this is the    #
# only route by which a Wire verb writes a row a TYPED insert opened, so it is #
# where all four crossings exist.                                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, change=change, source="reread")
        for target in _ALL_TARGETS
        for verb in _SOURCE_VERBS
        for change in ("ordinary", "net_zero")
        if (target.name, verb) not in _BITEMPORAL_DELETE
    ),
    ids=str,
)
def test_a_write_over_a_reread_insert_answers_one_way_whoever_opened_it(
    scenario: Scenario,
) -> None:
    _crossings_agree(scenario, crossings=4)


# --------------------------------------------------------------------------- #
# Two defects at once: which one the caller hears.                            #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    (
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            source="pinned",
            window="reversed",
            label="pin-beats-window",
        ),
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
def test_two_defects_answer_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# Two defects at once over a source this unit of work inserted, crossed over   #
# every opener the source admits: whichever representation opened the row, the #
# window refusal and the net-zero no-op land in the same order.                #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("scenario", "crossings"),
    (
        (
            Scenario(
                target=POSITION_TARGET,
                verb="update_until",
                window="reversed",
                label="window-beats-the-insert-exemption",
            ),
            3,
        ),
        (
            Scenario(
                target=POSITION_TARGET,
                verb="update_until",
                window="reversed",
                opened_until=True,
                label="window-beats-a-bounded-insert-exemption",
            ),
            3,
        ),
        (
            Scenario(
                target=POSITION_TARGET,
                verb="update_until",
                window="reversed",
                change="net_zero",
                label="window-beats-a-net-zero-insert-source",
            ),
            3,
        ),
        (
            Scenario(
                target=ACCOUNT_TARGET,
                verb="update",
                change="net_zero",
                label="a-net-zero-write-of-an-inserted-row",
            ),
            3,
        ),
        (
            Scenario(
                target=POSITION_TARGET,
                verb="update_until",
                window="reversed",
                source="reread",
                label="window-beats-a-reread-insert-source",
            ),
            4,
        ),
        (
            Scenario(
                target=ACCOUNT_TARGET,
                verb="update",
                change="net_zero",
                source="reread",
                label="a-net-zero-write-of-a-reread-inserted-row",
            ),
            4,
        ),
    ),
    ids=lambda value: str(value),
)
def test_two_defects_over_an_inserted_source_answer_one_way(
    scenario: Scenario, crossings: int
) -> None:
    _crossings_agree(scenario, crossings=crossings)


# --------------------------------------------------------------------------- #
# The Wire-only half of the dual-defect set: a document a Typed caller cannot  #
# author. Each row states the one expectation, and the Typed rows below state  #
# where that same authoring is refused instead.                               #
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
)


@pytest.mark.parametrize(("scenario", "expected"), _MALFORMED, ids=lambda value: str(value))
def test_malformed_wire_input_earns_a_static_refusal(scenario: Scenario, expected: str) -> None:
    refused = outcome(scenario, "wire")
    assert isinstance(refused, Refused)
    assert refused.error == "WriteInstructionError"
    assert refused.phase == "verb"
    assert expected in refused.message


@pytest.mark.parametrize(
    ("assignment", "expected"),
    (
        ({"nope": 1}, "edit-unknown-member"),
        ({"version": 9}, "edit-framework-owned"),
        ({"id": 2}, "edit-primary-key"),
    ),
    ids=("undeclared-member", "framework-owned-member", "primary-key-member"),
)
def test_the_typed_lane_refuses_that_authoring_before_a_verb_receives_it(
    assignment: Mapping[str, object], expected: str
) -> None:
    source = ACCOUNT_TARGET.fresh()
    with pytest.raises(EditError) as raised:
        source.edit(**assignment)
    assert expected in str(raised.value)


# --------------------------------------------------------------------------- #
# `terminate` against a target with no as-of axis, when the source's evidence  #
# is also unusable. The milestone-verb refusal is the static one and precedes  #
# the evidence question, which is the answer the Wire lane gives; the Typed    #
# lane resolves evidence first and gives the evidence refusal instead.         #
# --------------------------------------------------------------------------- #
_MILESTONE_ROWS: tuple[Scenario, ...] = (
    Scenario(target=ACCOUNT_TARGET, verb="terminate", source="standalone", concurrency="locking"),
    Scenario(target=PERSON_TARGET, verb="terminate", source="standalone", concurrency="locking"),
)

_TYPED_PREPARES_LAST = pytest.mark.xfail(
    reason=(
        "the Typed verbs resolve evidence before they prepare, so this row hears "
        "`write-evidence-unavailable` instead of the milestone-verb refusal until "
        "the shared keyed-write ingress lands"
    )
)


@pytest.mark.parametrize(
    "representation",
    (
        "wire",
        pytest.param("typed", marks=_TYPED_PREPARES_LAST),
    ),
)
@pytest.mark.parametrize("scenario", _MILESTONE_ROWS, ids=str)
def test_a_milestone_verb_on_a_non_temporal_target_beats_unusable_evidence(
    scenario: Scenario, representation: Representation
) -> None:
    refused = outcome(scenario, representation)
    assert isinstance(refused, Refused)
    assert refused.error == "WriteInstructionError"
    assert refused.phase == "verb"
    assert "milestone verb never applies to a non-temporal entity" in refused.message


# --------------------------------------------------------------------------- #
# `delete` against a Bitemporal target. The Typed verb reaches neither         #
# `declaring_of` nor the window gate, so it buffers an instruction the flush   #
# then refuses, resolves unusable evidence first where there is any, or — over #
# a row this unit of work inserted — cancels that insert and emits nothing;    #
# the Wire verb runs the window gate and refuses at the call. Each answer is   #
# stated on its own, because the specification names neither of the two as the #
# correct one.                                                                 #
# --------------------------------------------------------------------------- #
def test_a_bitemporal_delete_is_refused_at_the_flush_on_the_typed_lane() -> None:
    refused = outcome(Scenario(target=POSITION_TARGET, verb="delete"), "typed")
    assert isinstance(refused, Refused)
    assert refused.error == "TemporalPlanningError"
    assert refused.phase == "flush"
    assert refused.message == "'delete' is not a Bitemporal milestone mutation"


def test_a_bitemporal_delete_of_a_standalone_source_hears_the_evidence_refusal_typed() -> None:
    scenario = Scenario(
        target=POSITION_TARGET, verb="delete", source="standalone", concurrency="locking"
    )
    refused = outcome(scenario, "typed")
    assert isinstance(refused, Refused)
    assert refused.error == "WriteEvidenceError"
    assert refused.code == "write-evidence-unavailable"
    assert refused.phase == "verb"


def test_a_bitemporal_delete_of_an_inserted_row_cancels_it_on_the_typed_lane() -> None:
    emitted = outcome(Scenario(target=POSITION_TARGET, verb="delete", opened_by="wire"), "typed")
    assert emitted == Completed((BeginCall(), CommitCall()))


def test_a_bitemporal_delete_is_refused_at_the_verb_on_the_wire_lane() -> None:
    for scenario in (
        Scenario(target=POSITION_TARGET, verb="delete"),
        Scenario(target=POSITION_TARGET, verb="delete", source="standalone", concurrency="locking"),
        Scenario(target=POSITION_TARGET, verb="delete", opened_by="wire"),
    ):
        refused = outcome(scenario, "wire")
        assert isinstance(refused, Refused)
        assert refused.error == "WriteInstructionError"
        assert refused.phase == "verb"
        assert "a bitemporal 'delete' requires valid_from" in refused.message


# --------------------------------------------------------------------------- #
# The one crossing no caller can spell, and the read that makes it spellable.  #
# --------------------------------------------------------------------------- #
def test_a_wire_verb_cannot_write_a_row_a_typed_insert_still_holds_buffered() -> None:
    scenario = Scenario(target=ACCOUNT_TARGET, verb="update", opened_by="typed")
    assert reachable(scenario, "typed")
    assert not reachable(scenario, "wire")
    assert reachable(replace(scenario, source="reread"), "wire")


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
