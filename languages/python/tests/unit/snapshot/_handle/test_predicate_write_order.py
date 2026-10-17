"""The predicate-write order, stated once and asserted of both representations.

Every ``_where`` verb, Typed or Wire, enters one ingress: lifecycle re-entry,
then the stated start, then the representation's own capture of its selection
and assignments, then the one preparation that judges the target, the verb, the
window, the predicate, the family, and each assignment in that order, and only
then the buffering that routes a write readless or materializing. What a row
fixes is the ANSWER that order gives — the refusal's class, code, message, the
point it landed at, and the DML emitted — beside the whole port chronology, so a
refusal that read or flushed anything, and an admitted write that read where its
target is readless, are different answers rather than agreeing ones.

Each row states one expectation per representation that can express it and
asserts it of each in turn; nothing here compares one representation to the
other. A fault only one representation has a spelling for — an unfinished Typed
path — is a Typed row alone, and a shape fault each representation spells its
own way states each one's own refusal.

Detailed assignment-order, document-shape, and lifecycle re-entry rules stay
with their owners: core preparation's suite, ``test_wire_writes.py``, and the
execution-lifecycle re-entry suite.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import pytest

from parallax.core import QueryDefinitionError, inheritance
from parallax.core.base import InstantError
from parallax.core.predicate import CanonicalDocumentError, ModelRejectedError
from parallax.core.unit_work import WriteInstructionError
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    ReadCall,
    RollbackCall,
    WriteCall,
)
from tests.unit.snapshot._handle._write_order_drivers import (
    ACCOUNT_SELECTION,
    BALANCE_SELECTION,
    CARD_PAYMENT_SELECTION,
    PERSON_SELECTION,
    POSITION_SELECTION,
    REPRESENTATIONS,
    UNDECLARED_SELECTION,
    Answer,
    PredicateWriteScenario,
    Representation,
    answered,
    outcome,
    reachable,
)

type _Chronology = tuple[type[PortCall], ...]


@dataclass(frozen=True, slots=True)
class _Expected:
    """One representation's answer and the kinds of every port call behind it."""

    answer: Answer
    calls: _Chronology


def _wrote(*between: type[PortCall]) -> _Expected:
    """An admitted write whose transaction ran ``between`` inside its boundary."""
    statements = sum(1 for call in between if call is WriteCall)
    return _Expected(Answer(None, None, None, None, statements), (BeginCall, *between, CommitCall))


def _refused(error: type[Exception], message: str, *, code: str | None = None) -> _Expected:
    """A refusal the VERB raised before the database was asked for anything."""
    return _Expected(Answer(error, code, message, "verb", 0), (BeginCall, RollbackCall))


def _both(expected: _Expected) -> Mapping[Representation, _Expected]:
    return dict.fromkeys(REPRESENTATIONS, expected)


@dataclass(frozen=True, slots=True)
class _Row:
    scenario: PredicateWriteScenario
    expected: Mapping[Representation, _Expected]

    def __str__(self) -> str:
        return str(self.scenario)


def _assert_row(row: _Row) -> None:
    """Assert every representation that can issue ``row``'s scenario answers
    with the expectation stated for it, and that one is stated for each."""
    scenario = row.scenario
    assert set(row.expected) == {
        representation for representation in REPRESENTATIONS if reachable(scenario, representation)
    }
    for representation, expected in row.expected.items():
        result = outcome(scenario, representation)
        observed = _Expected(answered(result), tuple(type(call) for call in result.calls))
        assert observed == expected, representation


_START_REFUSAL: Final = "valid_from=None states no start; omit valid_from rather than stating None"
_POSITION_REQUIRES_START: Final = (
    "WherePosition: a bitemporal 'amend' requires valid_from (the mutation's own Valid-Time "
    "instant)"
)
_POSITION_INVERTED: Final = (
    "'parallax.compatibility.WherePosition.id': decoded lower bound 10 is greater than decoded "
    "upper bound 1, so the range is empty"
)
_NAIVE: Final = "a naive datetime is not a valid `timestamp`; attach a tzinfo"
_UNSPELLABLE: Final = (
    "datetime.datetime(1, 1, 1, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(seconds=50400)))"
    " is not a valid `timestamp`: no UTC datetime names its instant — an aware value at the "
    "representational edge, or a tzinfo answering no usable offset"
)
_FAMILY_REFUSAL: Final = (
    "CardPayment: a predicate-selected (set-based) write on an inheritance-family entity is "
    "unsupported (subtype-write-set-based-unsupported) — per-object writes are keyed "
    "(m-inheritance 'Per-object writes are keyed; set-based inheritance writes are out of scope')"
)
_UNKNOWN_NODE: Final = "unknown predicate node 'nonsense'"


def _not_mutation_compatible(entity: str) -> _Expected:
    return _refused(
        QueryDefinitionError,
        f"query-not-mutation-compatible: {entity}: a set-based write target carries nothing but "
        "a predicate, and this query carries limit",
        code="query-not-mutation-compatible",
    )


def _shape_refusals(entity: str) -> Mapping[Representation, _Expected]:
    """Each representation's own shape refusal: a Typed query carrying a
    result-shaping clause, and a Wire predicate node no algebra spells."""
    return {
        "typed": _not_mutation_compatible(entity),
        "wire": _refused(CanonicalDocumentError, _UNKNOWN_NODE),
    }


def _bounded_pair(verb: str, missing: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"WherePosition: a bounded '{verb}' states its window as a pair, and {missing} is absent "
        "— an unbounded write omits until rather than stating none",
    )


def _reversed(verb: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"WherePosition: '{verb}' requires valid_from < until — got "
        "valid_from=datetime.datetime(2024, 7, 1, 0, 0, tzinfo=datetime.timezone.utc), "
        "until=datetime.datetime(2024, 4, 1, 0, 0, tzinfo=datetime.timezone.utc)",
    )


def _temporal_delete(entity: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"Temporal objects like {entity!r} do not support 'delete_where', which physically "
        "removes rows. Use 'terminate_where' instead.",
    )


def _no_valid_time(entity: str, profile: str, verb: str, keyword: str) -> _Expected:
    return _refused(
        WriteInstructionError,
        f"{entity}: a {profile} '{verb}' takes no {keyword} ('{entity}' declares no Valid-Time "
        "dimension to bound)",
    )


# --------------------------------------------------------------------------- #
# An admitted write reaches the buffering its target routes it to: readless    #
# for an unversioned Non-Temporal target, one resolving read for a versioned   #
# or temporal one, under every public dispatch path.                           #
# --------------------------------------------------------------------------- #
_READLESS: Final = _wrote(WriteCall)
_MATERIALIZED_IN_PLACE: Final = _wrote(ReadCall, WriteCall)
_MATERIALIZED_SUCCESSOR: Final = _wrote(ReadCall, WriteCall, WriteCall)

_ADMITTED: Final[tuple[_Row, ...]] = (
    _Row(PredicateWriteScenario(PERSON_SELECTION, "amend"), _both(_READLESS)),
    _Row(PredicateWriteScenario(PERSON_SELECTION, "delete"), _both(_READLESS)),
    _Row(PredicateWriteScenario(ACCOUNT_SELECTION, "amend"), _both(_MATERIALIZED_IN_PLACE)),
    _Row(
        PredicateWriteScenario(ACCOUNT_SELECTION, "amend", concurrency="locking"),
        _both(_MATERIALIZED_IN_PLACE),
    ),
    _Row(PredicateWriteScenario(ACCOUNT_SELECTION, "delete"), _both(_MATERIALIZED_IN_PLACE)),
    _Row(PredicateWriteScenario(BALANCE_SELECTION, "amend"), _both(_MATERIALIZED_SUCCESSOR)),
    _Row(PredicateWriteScenario(BALANCE_SELECTION, "terminate"), _both(_MATERIALIZED_IN_PLACE)),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="stated"),
        _both(_MATERIALIZED_SUCCESSOR),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="stated", until="stated"),
        _both(_MATERIALIZED_SUCCESSOR),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION,
            "amend",
            valid_from="stated",
            until="stated",
            concurrency="locking",
        ),
        _both(_MATERIALIZED_SUCCESSOR),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "terminate", valid_from="stated"),
        _both(_MATERIALIZED_SUCCESSOR),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "terminate", valid_from="stated", until="stated"
        ),
        _both(_MATERIALIZED_SUCCESSOR),
    ),
)


@pytest.mark.parametrize("row", _ADMITTED, ids=str)
def test_an_admitted_predicate_write_is_buffered_as_its_target_routes_it(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# The stated start is judged first: a stated `valid_from=None` is refused      #
# ahead of every fault the representation, the target, or the window carries. #
# --------------------------------------------------------------------------- #
_STATED_NONE_START: Final[tuple[_Row, ...]] = (
    # A target that takes no `valid_from` at all still hears the stated None.
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "amend", valid_from="none"),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="none", selection="unshaped"
        ),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="none", selection="unbound"),
        {"typed": _refused(WriteInstructionError, _START_REFUSAL)},
    ),
    _Row(
        PredicateWriteScenario(UNDECLARED_SELECTION, "terminate", valid_from="none"),
        _both(_refused(WriteInstructionError, _START_REFUSAL)),
    ),
)


@pytest.mark.parametrize("row", _STATED_NONE_START, ids=str)
def test_a_stated_none_start_is_refused_before_anything_else_is_judged(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# Each representation captures its own selection before the model is asked    #
# anything: its shape fault outranks an undeclared Entity, a window fault, and #
# an assignment fault alike.                                                   #
# --------------------------------------------------------------------------- #
_REPRESENTATION_SHAPE: Final[tuple[_Row, ...]] = (
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "delete", selection="unshaped"),
        _shape_refusals("Person"),
    ),
    _Row(
        PredicateWriteScenario(UNDECLARED_SELECTION, "delete", selection="unshaped"),
        _shape_refusals("Account"),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", selection="unshaped"),
        _shape_refusals("WherePosition"),
    ),
    _Row(
        PredicateWriteScenario(
            PERSON_SELECTION, "amend", selection="unshaped", assignments="undeclared"
        ),
        _shape_refusals("Person"),
    ),
    _Row(
        PredicateWriteScenario(UNDECLARED_SELECTION, "delete"),
        _both(
            _refused(
                WriteInstructionError,
                "the connected model declares no entity 'parallax.compatibility.Account' for "
                "this write",
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _REPRESENTATION_SHAPE, ids=str)
def test_a_selections_own_shape_is_judged_before_the_model_is_consulted(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# The target's own rules: a temporal target spells removal `terminate_where`,  #
# a Non-Temporal one has no history to terminate, and each profile admits only #
# the window its As-Of Axes can bound — with a stated `until`, `None`          #
# included, selecting the bounded verb and an omitted one the unbounded verb.  #
# --------------------------------------------------------------------------- #
_TARGET_RULES: Final[tuple[_Row, ...]] = (
    _Row(PredicateWriteScenario(BALANCE_SELECTION, "delete"), _both(_temporal_delete("Balance"))),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "delete"),
        _both(_temporal_delete("WherePosition")),
    ),
    _Row(
        PredicateWriteScenario(ACCOUNT_SELECTION, "terminate"),
        _both(
            _refused(
                WriteInstructionError,
                "Non-temporal objects like 'Account' do not support 'terminate_where', which "
                "closes a row's history instead of removing it. Use 'delete_where' instead.",
            )
        ),
    ),
    _Row(
        PredicateWriteScenario(ACCOUNT_SELECTION, "amend", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    # A bound the target cannot take is heard before the start it cannot take either.
    _Row(
        PredicateWriteScenario(ACCOUNT_SELECTION, "amend", valid_from="stated", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "amendUntil", "until")),
    ),
    _Row(
        PredicateWriteScenario(ACCOUNT_SELECTION, "terminate", until="stated"),
        _both(_no_valid_time("Account", "non-temporal", "terminateUntil", "until")),
    ),
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "amend", valid_from="stated"),
        _both(_no_valid_time("Person", "non-temporal", "amend", "valid_from")),
    ),
    _Row(
        PredicateWriteScenario(BALANCE_SELECTION, "terminate", valid_from="stated"),
        _both(_no_valid_time("Balance", "Transaction-Time-Only", "terminate", "valid_from")),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend"),
        _both(_refused(WriteInstructionError, _POSITION_REQUIRES_START)),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", until="stated"),
        _both(_bounded_pair("amendUntil", "valid_from")),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="stated", until="none"),
        _both(_bounded_pair("amendUntil", "until")),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "terminate", valid_from="stated", until="none"),
        _both(_bounded_pair("terminateUntil", "until")),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="stated", until="reversed"),
        _both(_reversed("amendUntil")),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "terminate", valid_from="stated", until="reversed"
        ),
        _both(_reversed("terminateUntil")),
    ),
    # A bound that is no writable instant keeps `m-core`'s own classification.
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="naive"),
        _both(_refused(InstantError, _NAIVE)),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="unspellable"),
        _both(_refused(InstantError, _UNSPELLABLE)),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "terminate", valid_from="stated", until="naive"),
        _both(_refused(InstantError, _NAIVE)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "terminate", valid_from="stated", until="unspellable"
        ),
        _both(_refused(InstantError, _UNSPELLABLE)),
    ),
)


@pytest.mark.parametrize("row", _TARGET_RULES, ids=str)
def test_the_target_admits_the_verb_and_window_before_anything_it_selects(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# Then the selection the model binds, then the family, then the assignments:  #
# a window fault outranks a predicate the model refuses, Typed binding         #
# precedes the family refusal, and the family refusal precedes any assignment. #
# --------------------------------------------------------------------------- #
_SELECTION_ORDER: Final[tuple[_Row, ...]] = (
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", selection="inverted"),
        _both(_refused(WriteInstructionError, _POSITION_REQUIRES_START)),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", selection="unbound"),
        {"typed": _refused(WriteInstructionError, _POSITION_REQUIRES_START)},
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="naive", selection="inverted"
        ),
        _both(_refused(InstantError, _NAIVE)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="unspellable", selection="inverted"
        ),
        _both(_refused(InstantError, _UNSPELLABLE)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="stated", until="naive", selection="inverted"
        ),
        _both(_refused(InstantError, _NAIVE)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION,
            "amend",
            valid_from="stated",
            until="unspellable",
            selection="inverted",
        ),
        _both(_refused(InstantError, _UNSPELLABLE)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="stated", selection="inverted"
        ),
        _both(_refused(ModelRejectedError, _POSITION_INVERTED)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="stated", until="stated", selection="inverted"
        ),
        _both(_refused(ModelRejectedError, _POSITION_INVERTED)),
    ),
    _Row(
        PredicateWriteScenario(
            PERSON_SELECTION, "amend", selection="inverted", assignments="undeclared"
        ),
        _both(
            _refused(
                ModelRejectedError,
                "'parallax.compatibility.Person.id': decoded lower bound 10 is greater than "
                "decoded upper bound 1, so the range is empty",
            )
        ),
    ),
    _Row(
        PredicateWriteScenario(CARD_PAYMENT_SELECTION, "amend", selection="unbound"),
        {
            "typed": _refused(
                QueryDefinitionError,
                "query-path-invalid: parallax.compatibility.CardPayment.missing: CardPayment "
                "declares no member 'missing'",
                code="query-path-invalid",
            )
        },
    ),
    _Row(
        PredicateWriteScenario(CARD_PAYMENT_SELECTION, "amend"),
        _both(_refused(inheritance.InheritanceError, _FAMILY_REFUSAL)),
    ),
    _Row(
        PredicateWriteScenario(CARD_PAYMENT_SELECTION, "amend", assignments="undeclared"),
        _both(_refused(inheritance.InheritanceError, _FAMILY_REFUSAL)),
    ),
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "amend", assignments="undeclared"),
        {
            "typed": _refused(
                WriteInstructionError,
                "Person: assignment 'parallax.compatibility.Account.owner' does not name a "
                "declared member of parallax.compatibility.Person",
            ),
            "wire": _refused(
                WriteInstructionError,
                "Person: assignment 'parallax.compatibility.Person.undeclared' does not name a "
                "declared member of parallax.compatibility.Person",
            ),
        },
    ),
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "amend", assignments="none"),
        _both(
            _refused(
                WriteInstructionError,
                "Person: a predicate-selected 'amend' requires at least one assignment",
            )
        ),
    ),
)


@pytest.mark.parametrize("row", _SELECTION_ORDER, ids=str)
def test_the_selection_then_the_family_then_the_assignments_are_judged(row: _Row) -> None:
    _assert_row(row)


# --------------------------------------------------------------------------- #
# A materializing write's resolving read force-flushes what is pending, so an  #
# admitted one flushes an earlier insert ahead of its read, and a refused one  #
# is refused before that read: it reaches the database for nothing at all.    #
# --------------------------------------------------------------------------- #
_PENDING: Final[tuple[_Row, ...]] = (
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="stated", pending=True),
        _both(_wrote(WriteCall, ReadCall, WriteCall, WriteCall)),
    ),
    _Row(
        PredicateWriteScenario(PERSON_SELECTION, "amend", pending=True),
        _both(_wrote(WriteCall, WriteCall)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="stated", selection="inverted", pending=True
        ),
        _both(_refused(ModelRejectedError, _POSITION_INVERTED)),
    ),
    _Row(
        PredicateWriteScenario(
            POSITION_SELECTION, "amend", valid_from="stated", until="none", pending=True
        ),
        _both(_bounded_pair("amendUntil", "until")),
    ),
    _Row(
        PredicateWriteScenario(POSITION_SELECTION, "amend", valid_from="naive", pending=True),
        _both(_refused(InstantError, _NAIVE)),
    ),
)


@pytest.mark.parametrize("row", _PENDING, ids=str)
def test_a_refused_predicate_write_flushes_no_pending_write(row: _Row) -> None:
    _assert_row(row)
