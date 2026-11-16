"""Unit tests for the native key-sequence oracle (m-case-format *Reservation
statements*).

The oracle derives every reservation's first key, every keyless row's key, and
each allocator's final position from the declared ``key-sequence`` settings
alone, and asserts them against the golden binds and the real database. These
tests pin the derivation and every failure path.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from reference_harness._case_execution import CaseExecution
from reference_harness.case import discover_cases
from reference_harness.case_assertions import CaseFailure
from reference_harness.case_runner import (
    _assert_native_positions,
    _assert_reservation,
    _assert_write_input_columns,
    _native_allocation,
)
from reference_harness.ddl_builder import ddl_for
from reference_harness.pk_gen import NativeSequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _pkgen_case(stem_prefix: str):
    return next(
        c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith(stem_prefix)
    )


def _reserving_cases() -> list:
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence and case.reservations
    ]


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
def test_every_reserving_case_binds_the_keys_its_declarations_derive(dialect: str) -> None:
    cases = _reserving_cases()
    assert {case.path.stem[:12] for case in cases} >= {"m-pk-gen-004", "m-pk-gen-023"}
    for case in cases:
        _assert_write_input_columns(case, dialect)


# --- native key sequences (m-pk-gen-020) ----------------------------------------


def test_a_native_block_steps_by_the_stride_and_stops_at_the_key_range() -> None:
    sequence = NativeSequence("ids", "int32", batch_size=4, initial_value=1, increment_size=10)
    assert sequence.step == 40
    assert sequence.block_start(2) == 81
    assert sequence.block(81, "postgres") == [81, 91, 101, 111]
    assert sequence.block(2**31 - 25, "mariadb") == [2**31 - 25, 2**31 - 15, 2**31 - 5]
    wide = NativeSequence("ids", "int64", batch_size=1, initial_value=1, increment_size=1)
    assert wide.key_range("postgres") == (-(2**63), 2**63 - 1)
    assert wide.key_range("mariadb") == (-(2**63) + 1, 2**63 - 2)


def test_the_harness_provisions_each_native_sequence_where_its_binding_places_it() -> None:
    case = _pkgen_case("m-pk-gen-020")
    assert ddl_for(case.setup_model, case.setup_placement("postgres"))[-1] == (
        "create sequence px.pass_ids as bigint increment by 30 "
        f"minvalue {-(2**63)} maxvalue {2**63 - 1} start with 100 no cycle"
    )
    assert ddl_for(case.setup_model, case.setup_placement("mariadb"))[-1] == (
        "create sequence px.pass_ids as bigint increment by 30 "
        f"minvalue {-(2**63) + 1} maxvalue {2**63 - 2} start with 100 nocache nocycle"
    )


def test_keyless_rows_take_the_keys_their_steps_reservations_reserve() -> None:
    case = _pkgen_case("m-pk-gen-020")
    allocation = _native_allocation(case, "postgres")
    assert allocation.first_keys == {0: 100}
    assert allocation.step_keys == {0: [100, 110]}
    assert allocation.next_blocks == {"pass_ids": 130}
    _assert_write_input_columns(case, "postgres")


def test_a_keyless_insert_binding_another_key_is_rejected() -> None:
    case = copy.deepcopy(_pkgen_case("m-pk-gen-020"))
    case.then["statements"][1]["binds"]["postgres"][0] = [100, 120]
    with pytest.raises(CaseFailure, match="110 != golden bind 120"):
        _assert_write_input_columns(case, "postgres")


@pytest.mark.parametrize(
    ("statements", "message"),
    [
        (lambda entries: entries[1:], r"authors 0 reservation\(s\) for 2 keyless row\(s\)"),
        (lambda entries: [entries[0], *entries], r"authors 2 reservation\(s\) for 2 keyless"),
        (lambda entries: [entries[1], entries[0]], "after the sequence's last write"),
    ],
)
def test_reservations_a_steps_keyless_rows_do_not_need_are_rejected(
    statements: Any, message: str
) -> None:
    case = copy.deepcopy(_pkgen_case("m-pk-gen-020"))
    case.then["statements"] = statements(case.then["statements"])
    with pytest.raises(CaseFailure, match=message):
        _native_allocation(case, "postgres")


def test_a_reservation_after_its_steps_first_write_is_rejected() -> None:
    case = copy.deepcopy(_pkgen_case("m-pk-gen-020"))
    case.when["writeSequence"][0]["statements"] = 2
    reservation, insert = case.then["statements"]
    case.then["statements"] = [insert, reservation, copy.deepcopy(insert)]
    with pytest.raises(CaseFailure, match="after writeSequence step 0 already wrote"):
        _native_allocation(case, "postgres")


class _AnsweringDb:
    """Answers every query with one row holding *value*, recording what it ran."""

    def __init__(self, dialect: str, value: int) -> None:
        self.dialect = dialect
        self.value = value
        self.queries: list[tuple[str, tuple[Any, ...]]] = []

    def query(self, sql: str, binds: Any = ()) -> list[dict[str, Any]]:
        self.queries.append((sql, tuple(binds)))
        return [{"first_key": self.value}]


@pytest.mark.parametrize(("answer", "passes"), [(100, True), (130, False)])
def test_a_reservation_must_answer_the_declared_blocks_first_key(answer: int, passes: bool) -> None:
    case = _pkgen_case("m-pk-gen-020")
    execution = CaseExecution(case, _AnsweringDb("postgres", answer))
    if passes:
        _assert_reservation(case, execution, 0, "select 1", [], 100)
    else:
        with pytest.raises(CaseFailure, match=r"answered first key\(s\) \[130\]"):
            _assert_reservation(case, execution, 0, "select 1", [], 100)


@pytest.mark.parametrize("dialect", ["postgres", "mariadb"])
@pytest.mark.parametrize(("answer", "passes"), [(130, True), (120, False)])
def test_a_reserved_sequence_must_stand_at_the_declared_next_block(
    dialect: str, answer: int, passes: bool
) -> None:
    case = _pkgen_case("m-pk-gen-020")
    db = _AnsweringDb(dialect, answer)
    if passes:
        _assert_native_positions(case, db)
    else:
        with pytest.raises(CaseFailure, match=r"next answers \[120\]"):
            _assert_native_positions(case, db)
    assert len(db.queries) == 1


@pytest.mark.parametrize(
    ("prefix", "first_keys", "step_keys", "next_blocks"),
    [
        ("m-pk-gen-009", {0: 1, 1: 4}, {0: [1, 2, 3, 4]}, {"pass_seq": 7}),
        ("m-pk-gen-012", {0: 100, 2: 120}, {0: [100, 110], 1: [120, 130]}, {"voucher_seq": 140}),
        ("m-pk-gen-021", {0: 1}, {0: [1]}, {"badge_seq": 2}),
        (
            "m-pk-gen-023",
            {0: 1, 2: 101, 4: 201},
            {0: [1], 1: [101], 2: [201]},
            {"fleetIds": 301},
        ),
    ],
    ids=["refill-within-a-step", "a-block-per-step", "supplied-keys-spend-none", "one-stream"],
)
def test_the_declarations_derive_each_reservation_and_key(
    prefix: str, first_keys: dict, step_keys: dict, next_blocks: dict
) -> None:
    allocation = _native_allocation(_pkgen_case(prefix), "postgres")
    assert allocation.first_keys == first_keys
    assert allocation.step_keys == step_keys
    assert allocation.next_blocks == next_blocks


@pytest.mark.parametrize(("dialect", "integer"), [("postgres", "integer"), ("mariadb", "int")])
def test_an_int32_allocator_is_provisioned_within_the_int32_range(
    dialect: str, integer: str
) -> None:
    case = _pkgen_case("m-pk-gen-022")
    no_cycle = "no cycle" if dialect == "postgres" else "nocache nocycle"
    assert (
        f"create sequence px.wristband_seq as {integer} increment by 3 "
        f"minvalue {-(2**31)} maxvalue {2**31 - 1} start with {2**31 - 2} {no_cycle}"
    ) in ddl_for(case.setup_model, case.setup_placement(dialect))
    allocation = _native_allocation(case, dialect)
    assert allocation.step_keys == {0: [2**31 - 2, 2**31 - 1]}
    assert allocation.next_blocks == {"wristband_seq": 2**31 + 1}


def test_a_family_allocator_is_provisioned_where_its_binding_places_it() -> None:
    case = _pkgen_case("m-pk-gen-023")
    assert ddl_for(case.setup_model, case.setup_placement("postgres"))[-1].startswith(
        "create sequence px_keys.fleet_ids as bigint increment by 100 "
    )


def test_a_clipped_block_binding_a_key_past_the_range_is_rejected() -> None:
    case = copy.deepcopy(_pkgen_case("m-pk-gen-022"))
    case.when["writeSequence"][0]["rows"].append({"gate": "north"})
    with pytest.raises(CaseFailure, match="reservation"):
        _native_allocation(case, "postgres")


class _ExhaustedDb:
    """Refuses every query with *code*, as a sequence past its bound does."""

    def __init__(self, dialect: str, code: str | int) -> None:
        self.dialect = dialect
        self.code = code

    def query(self, sql: str, binds: Any = ()) -> list[dict[str, Any]]:
        raise RuntimeError(sql)

    def native_error_code(self, exc: Exception) -> str | int:
        return self.code


@pytest.mark.parametrize(("dialect", "code"), [("postgres", "2200H"), ("mariadb", 4084)])
def test_an_exhausted_sequence_must_refuse_its_next_reservation_natively(
    dialect: str, code: str | int
) -> None:
    case = _pkgen_case("m-pk-gen-022")
    _assert_native_positions(case, _ExhaustedDb(dialect, code))
    with pytest.raises(CaseFailure, match="exhaustion code"):
        _assert_native_positions(case, _ExhaustedDb(dialect, "42501"))
    with pytest.raises(CaseFailure, match="leave it exhausted"):
        _assert_native_positions(case, _AnsweringDb(dialect, 2**31 + 1))


def test_a_sequence_short_of_exhaustion_must_answer_rather_than_fail() -> None:
    with pytest.raises(CaseFailure, match="the declaration-derived block 130"):
        _assert_native_positions(_pkgen_case("m-pk-gen-020"), _ExhaustedDb("postgres", "2200H"))
