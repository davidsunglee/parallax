"""The Keyed Write Validation Order, characterized across both representations.

Every keyed verb runs one order, and that order is what a caller observes as
refusal precedence (`python.md` §5 "The Keyed Write Validation Order is one
order"). This suite drives each row through the Typed verbs and through
``tx.wire``'s against a scripted port and asserts that both answer it the same
way — the DML emitted, or the refusal class, code, and message — so the order is
pinned once rather than once per representation.

Rows only one representation can reach carry one assertion instead of a
comparison. A malformed change document, an undeclared member, and an illegal
assignment are all Wire-only: a Typed caller cannot express them, because
``edit()`` judges an assignment before ``tx.update()`` ever receives a value.

Two rows are recorded rather than compared, each below the axis it belongs to,
because the two representations answer them differently today.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest
from _keyed_write_drivers import (
    ACCOUNT_TARGET,
    CONCURRENCIES,
    PERSON_TARGET,
    POSITION_TARGET,
    TARGETS,
    VERBS,
    Buffered,
    Refused,
    Representation,
    Scenario,
    Target,
    Verb,
    outcome,
    reachable,
)

# `delete` against a Bitemporal target: the Typed verb alone skips window
# validation, so the two representations refuse it differently. Recorded as it
# stands by `test_a_bitemporal_delete_...` below rather than compared here.
_BITEMPORAL_DELETE: frozenset[tuple[str, str]] = frozenset({("position", "delete")})

# `terminate` against a target with no as-of axis, when the source's evidence is
# also unusable: the research-bounded divergence, owned by the dual-defect row
# `test_a_milestone_verb_on_a_non_temporal_target_...` below.
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


def _agrees(scenario: Scenario) -> None:
    """Assert both representations answer ``scenario`` identically."""
    assert outcome(scenario, "typed") == outcome(scenario, "wire")


def _grid(
    targets: tuple[Target, ...] = TARGETS,
    verbs: tuple[Verb, ...] = VERBS,
    *,
    exempt: frozenset[tuple[str, str]] = frozenset(),
    **axes: object,
) -> tuple[Scenario, ...]:
    return tuple(
        Scenario(target=target, verb=verb, concurrency=concurrency, **axes)  # pyright: ignore[reportArgumentType]
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
@pytest.mark.parametrize("scenario", _grid(exempt=_BITEMPORAL_DELETE), ids=str)
def test_one_verb_over_a_participating_source_answers_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# --------------------------------------------------------------------------- #
# The change axis. A net-zero chain and an untouched copy are the two ways a   #
# keyed update names members and changes nothing; both must reduce to the same #
# no-op the Wire lane reaches by comparing against what its source published,  #
# which is what licenses one comparison rule behind both representations.      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario",
    _grid(verbs=("update", "update_until"), change="net_zero")
    + _grid(verbs=("update", "update_until"), change="untouched"),
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
# opened it: a Typed insert then a Typed write, a Wire insert then a Wire      #
# write, and a Wire insert then a Typed write. The fourth crossing cannot be   #
# spelled (see `reachable`).                                                  #
# --------------------------------------------------------------------------- #
_CROSSINGS: tuple[tuple[Representation, Representation], ...] = (
    ("typed", "typed"),
    ("wire", "wire"),
    ("wire", "typed"),
)


@pytest.mark.parametrize(
    "scenario",
    tuple(
        Scenario(target=target, verb=verb, change=change, opened_by="typed")
        for target in TARGETS
        for verb in _SOURCE_VERBS
        for change in ("ordinary", "net_zero")
        if (target.name, verb) not in _BITEMPORAL_DELETE
    ),
    ids=str,
)
def test_a_same_transaction_insert_licenses_the_write_whoever_opened_it(
    scenario: Scenario,
) -> None:
    answers = {
        f"{opened}-insert/{writer}-write": outcome(
            Scenario(
                target=scenario.target,
                verb=scenario.verb,
                change=scenario.change,
                opened_by=opened,
            ),
            writer,
        )
        for opened, writer in _CROSSINGS
    }
    assert len(set(answers.values())) == 1, answers


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
            target=POSITION_TARGET,
            verb="update_until",
            opened_by="wire",
            window="reversed",
            label="window-beats-the-insert-exemption",
        ),
        Scenario(
            target=POSITION_TARGET,
            verb="update_until",
            opened_by="wire",
            window="reversed",
            change="net_zero",
            label="window-beats-a-net-zero-insert-source",
        ),
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            opened_by="wire",
            change="net_zero",
            label="a-net-zero-write-of-an-inserted-row",
        ),
        Scenario(
            target=ACCOUNT_TARGET,
            verb="update",
            source="standalone",
            concurrency="locking",
            change="net_zero",
            label="a-net-zero-write-needs-no-evidence",
        ),
    ),
    ids=str,
)
def test_two_defects_answer_one_way(scenario: Scenario) -> None:
    _agrees(scenario)


# The Wire-only half of the dual-defect set: every shape here is a document a
# Typed caller cannot author, so each row states one expectation rather than
# comparing two.
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
    assert expected in refused.message


# --------------------------------------------------------------------------- #
# `terminate` against a target with no as-of axis, when the source's evidence  #
# is also unusable. The milestone-verb refusal is the static one and precedes  #
# the evidence question, which is what the Wire lane answers today; the Typed  #
# lane resolves evidence first and is expected to fail until the shared        #
# ingress lands.                                                              #
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
    assert "milestone verb never applies to a non-temporal entity" in refused.message


# --------------------------------------------------------------------------- #
# `delete` against a Bitemporal target. The Typed verb reaches neither         #
# `declaring_of` nor the window gate, so it buffers an instruction the flush   #
# then refuses, or — over a row this unit of work inserted — cancels that       #
# insert and emits nothing; the Wire verb runs the window gate and refuses at  #
# the call. Recorded as it stands: which answer is correct is a specification  #
# decision this characterization opened and does not take.                    #
# --------------------------------------------------------------------------- #
def test_a_bitemporal_delete_is_refused_at_the_flush_on_the_typed_lane() -> None:
    refused = outcome(Scenario(target=POSITION_TARGET, verb="delete"), "typed")
    assert isinstance(refused, Refused)
    assert refused.error == "TemporalPlanningError"
    assert refused.message == "'delete' is not a Bitemporal milestone mutation"


def test_a_bitemporal_delete_of_an_inserted_row_cancels_it_on_the_typed_lane() -> None:
    emitted = outcome(Scenario(target=POSITION_TARGET, verb="delete", opened_by="wire"), "typed")
    assert emitted == Buffered(())


def test_a_bitemporal_delete_is_refused_at_the_verb_on_the_wire_lane() -> None:
    for scenario in (
        Scenario(target=POSITION_TARGET, verb="delete"),
        Scenario(target=POSITION_TARGET, verb="delete", opened_by="wire"),
    ):
        refused = outcome(scenario, "wire")
        assert isinstance(refused, Refused)
        assert refused.error == "WriteInstructionError"
        assert "a bitemporal 'delete' requires valid_from" in refused.message


# --------------------------------------------------------------------------- #
# The one crossing no caller can spell.                                       #
# --------------------------------------------------------------------------- #
def test_a_wire_verb_cannot_write_a_row_a_typed_insert_opened() -> None:
    scenario = Scenario(target=ACCOUNT_TARGET, verb="update", opened_by="typed")
    assert reachable(scenario, "typed")
    assert not reachable(scenario, "wire")
