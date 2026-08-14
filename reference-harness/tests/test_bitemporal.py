"""Unit tests for full-bitemporal machinery (no database).

These pin the DB-free invariants of the bitemporal slice: the bitemporal
DDL (a two-axis temporal entity's physical primary key spans BOTH as-of
start columns so the milestone rectangles are admissible), and the
write-step-count consistency of the `*Until` rectangle-split write sequences (the
sum of per-step counts == goldenSql DML count == roundTrips). The full
apply-DML-and-assert-rectangle-state behavior and the both-axis as-of reads are
exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_conflict_input,
    _assert_temporal_only_union_binds,
    _assert_write_input_columns,
    _assert_write_step_count,
    _has_temporal_gate,
    _read_table,
    _read_temporal_selections,
    _write_column_order,
)
from reference_harness.ddl_builder import contributor_types, ddl_for
from reference_harness.storage_layout import derived_primary_key_index

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _case_id(stem: str) -> str:
    """The per-module id prefix of a case stem (drops the trailing ``-<slug>``)."""
    return re.match(r"(m-[a-z0-9-]+-\d{3})", stem).group(1)


def _position_model():
    return load_model(COMPATIBILITY_ROOT, "models/position.yaml")


_PHASE8_MODULES = ("m-temporal-read", "m-bitemp-write")


def _phase8_cases():
    """The full-bitemporal single-entity cases (formerly the 08xx
    range): reads/writes on the bitemporal models, excluding the audit-only
    reads and the relationship-propagation deep-fetch cases (which also carry a
    temporal flavor but file under `m-navigate`)."""
    return [
        c
        for c in discover_cases(COMPATIBILITY_ROOT)
        if any(c.path.stem.startswith(f"{module}-") for module in _PHASE8_MODULES)
        and "bitemporal" in c.tags
    ]


def test_position_is_bitemporal_with_both_axes() -> None:
    entity = _position_model().root_entity
    assert entity.is_temporal
    axes = {dim["dimension"] for dim in entity.temporal_runtime_axes}
    assert axes == {"valid-time", "transaction-time"}


def test_bitemporal_ddl_primary_key_spans_both_as_of_to_columns() -> None:
    (create,) = ddl_for(_position_model(), "postgres")
    # The business key alone (pos_id) is not unique across rectangles; the
    # physical primary key MUST include BOTH axes' end columns (thru_z, out_z) so a
    # valid-time-bounded rectangle and its inactivated original coexist. The ends
    # are also what every close-update and Latest predicate pins.
    assert "primary key (pos_id, thru_z, out_z)" in create
    for column in ("from_z", "thru_z", "in_z", "out_z"):
        assert f"{column} timestamptz not null" in create


def test_bitemporal_ddl_key_is_the_layout_selection_in_dimension_order() -> None:
    # The DDL key is not re-derived: it is the layout's ordered slot selection —
    # every model primary-key slot, then each temporal dimension's end slot in
    # canonical dimension rank (Valid Time before Transaction Time). Both end
    # slots keep their single Temporal-tier position in the complete sequence.
    layout = _position_model().storage_layout.table("position")
    assert layout is not None
    assert [slot.column for slot in layout.physical_primary_key] == ["pos_id", "thru_z", "out_z"]
    assert [slot.tier.value for slot in layout.physical_primary_key] == [
        "identity",
        "temporal",
        "temporal",
    ]
    assert [layout.columns.index(slot) for slot in layout.physical_primary_key] == [0, 4, 6]
    (create,) = ddl_for(_position_model(), "postgres")
    assert (
        f"primary key ({', '.join(slot.column for slot in layout.physical_primary_key)})" in create
    )


def test_bitemporal_derived_index_is_the_physical_primary_key() -> None:
    entity = _position_model().root_entity
    assert derived_primary_key_index(entity.definition) == {
        "name": "position_pk",
        "attributes": ["id", "validEnd", "txEnd"],
        "unique": True,
    }
    assert not any(index["name"] == "position_pk" for index in entity.definition.get("indices", []))


def test_bitemporal_history_case_suppresses_both_axes() -> None:
    history_case = next(
        c for c in _phase8_cases() if c.path.stem == "m-temporal-read-016-bitemporal-history"
    )
    assert history_case.object_query["temporal"] == {
        "transaction-time": {"history": {}},
        "valid-time": {"history": {}},
    }


def test_until_trio_write_step_counts_are_consistent() -> None:
    write_cases = [c for c in _phase8_cases() if c.is_write_sequence]
    assert write_cases, "no Phase 8 write-sequence cases discovered"
    for case in write_cases:
        # Must not raise: per-step counts sum to the DML count and roundTrips,
        # including the 4-statement updateUntil and 3-statement terminateUntil.
        _assert_write_step_count(case, "postgres")


def _selection_body(tag: str, fields: dict[str, str]) -> Any:
    """One Temporal Selection's body: a coordinate for ``asOf``, the window object
    for ``asOfRange``, and the empty object a scan carries."""
    return fields.get("coordinate", fields) if tag == "asOf" else fields


def _temporal_write_input_cases():
    """Audit-only write-sequence cases carrying a temporal neutral write input (①)."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence
        and "postgres" in case.golden_dialects
        and any(
            step.get("rows") and case.model.entity(step["entity"]).is_temporal
            for step in case.write_sequence
        )
    ]


def test_temporal_write_input_holds_for_authored_cases() -> None:
    cases = _temporal_write_input_cases()
    # The in-slice audit trio all carry ① (rows + at).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-txtime-write-001",
        "m-txtime-write-002",
        "m-txtime-write-003",
    }
    for case in cases:
        # Must not raise: each audit-only ① derives in_z = at / out_z = infinity and
        # the full-row binds that cross-check the authored golden binds.
        _assert_write_input_columns(case, "postgres")


def test_temporal_write_input_at_corruption_is_rejected() -> None:
    case = copy.deepcopy(
        next(
            c for c in _temporal_write_input_cases() if c.path.stem.startswith("m-txtime-write-001")
        )
    )
    step = next(s for s in case.write_sequence if s.get("rows"))
    # Corrupt the transaction instant: the DERIVED in_z bind no longer matches the
    # golden in_z bind, so the ① ↔ ② temporal gate MUST fail (in_z is derived from
    # `at`, never read from the golden).
    step["at"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _until_write_cases():
    """Full-bitemporal `*Until` rectangle-split write-sequence cases
    (`m-bitemp-write-001`-`m-bitemp-write-003`)."""
    return [
        case
        for case in _phase8_cases()
        if case.is_write_sequence
        and any(
            step.get("mutation") in ("insertUntil", "updateUntil", "terminateUntil")
            for step in case.write_sequence
        )
    ]


def test_until_write_input_holds_for_authored_cases() -> None:
    cases = _until_write_cases()
    # The `*Until` trio all carry the valid-time window ① (rows + at + until).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-001",
        "m-bitemp-write-002",
        "m-bitemp-write-003",
    }
    for case in cases:
        # Must not raise: the close binds [at, pk, observedThruZ, infinity], every
        # chained insert opens at fresh Transaction Time [at, infinity), and the chained
        # Valid-Time windows are exactly the head / middle / tail the window
        # [validFrom, until) splits the reconstructed rectangle into.
        _assert_write_input_columns(case, "postgres")


def test_until_write_input_window_corruption_is_rejected() -> None:
    case = copy.deepcopy(
        next(c for c in _until_write_cases() if c.path.stem.startswith("m-bitemp-write-001"))
    )
    step = next(s for s in case.write_sequence if s.get("until"))
    # Corrupt the Valid-Time window end: the derived middle / tail windows no longer
    # match the chained inserts' Valid-Time binds, so the `*Until` ① ↔ ② window gate
    # MUST fail (the windows are DERIVED from `until`, never read from the golden).
    step["until"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _plain_split_write_cases():
    """Plain (UNBOUNDED) bitemporal rectangle-split write-sequence cases: an
    everyday `update` / `terminate` on the two-axis Position (`m-bitemp-write-006` /
    `m-bitemp-write-007`), the degenerate rectangle split with no `until`."""
    return [
        case
        for case in _phase8_cases()
        if case.is_write_sequence
        and any(step.get("mutation") in ("update", "terminate") for step in case.write_sequence)
    ]


def test_plain_split_write_input_holds_for_authored_cases() -> None:
    cases = _plain_split_write_cases()
    # The plain unbounded update/terminate pair carry ① (rows + at, NO until).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-006",
        "m-bitemp-write-007",
    }
    for case in cases:
        # Must not raise: routed through the rectangle-split cross-check (not the
        # audit-only close-and-open), the close binds [at, pk, observedThruZ, infinity],
        # the chained head / new-tail open at fresh Transaction Time [at, infinity), and
        # their Valid-Time windows meet at validFrom and run to the reconstructed
        # rectangle's own end (until is absent).
        _assert_write_input_columns(case, "postgres")


def test_plain_two_way_split_and_plain_terminate_statement_shapes() -> None:
    # The plain-update split is inactivate + head (old) + new tail (new) — a TWO-way
    # split (no middle, no old-tail): the `update` step is 3 statements, 4 with the
    # opening insert.
    split = next(
        c for c in _plain_split_write_cases() if c.path.stem.startswith("m-bitemp-write-006")
    )
    update_step = next(s for s in split.write_sequence if s["mutation"] == "update")
    assert update_step["statements"] == 3
    assert len(split.golden_statements("postgres")) == 4
    _assert_write_step_count(split, "postgres")

    # The plain terminate is inactivate + head (old) only — no tail: the `terminate`
    # step is 2 statements, 3 with the opening insert.
    terminate = next(
        c for c in _plain_split_write_cases() if c.path.stem.startswith("m-bitemp-write-007")
    )
    terminate_step = next(s for s in terminate.write_sequence if s["mutation"] == "terminate")
    assert terminate_step["statements"] == 2
    assert len(terminate.golden_statements("postgres")) == 3
    _assert_write_step_count(terminate, "postgres")


def test_ungated_close_with_a_trailing_bind_but_no_gate_predicate_is_rejected() -> None:
    # The gated branch is decided by the SQL SHAPE, not the bind arity: an UNGATED close
    # whose golden binds carry a spurious trailing value — even one that matches the
    # observed rectangle's in_z exactly — is a shape mismatch (4 placeholders, 5 binds),
    # which a branch keyed on bind length would tolerate as "gated". It MUST raise.
    case = copy.deepcopy(
        next(c for c in _plain_split_write_cases() if c.path.stem.startswith("m-bitemp-write-007"))
    )
    # Sanity: as authored the plain split cross-checks cleanly.
    _assert_write_input_columns(case, "postgres")
    observed_in = next(s for s in case.write_sequence if s["mutation"] == "insert")["at"]
    # The close is the second golden statement — confirm it renders the address alone,
    # with no `in_z = ?` gate, before corrupting its binds.
    close = case.then["statements"][1]
    assert "thru_z = ?" in close["sql"]["postgres"]
    assert "in_z = ?" not in close["sql"]["postgres"]
    close["binds"] = [*close["binds"], observed_in]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _gated_split_case():
    return next(c for c in _until_write_cases() if c.path.stem.startswith("m-bitemp-write-008"))


def test_gated_rectangle_split_close_reconstructs_the_observed_rectangle() -> None:
    # The optimistic gated split (`m-bitemp-write-008`) ADDRESSES the observed rectangle
    # by its own Valid-Time end then the invariant Transaction-Time infinity, and GATES
    # on its in_z last. Neither the address's thru_z nor the gate's in_z is in the
    # closing step's ① row: both are DERIVED from the OPENING insert step, whose
    # rectangle runs to the open Valid-Time bound and starts at 2024-01-01 — distinct
    # from the `updateUntil` window boundaries and from the close instant.
    case = _gated_split_case()
    opening = next(s for s in case.write_sequence if s["mutation"] == "insert")
    split = next(s for s in case.write_sequence if s["mutation"] == "updateUntil")
    # The golden close is the second statement (after the opening insert): its binds are
    # [at, pk, observedThruZ, infinity, observedTxStart].
    close_binds = case.statement_binds(1)
    assert len(close_binds) == 5
    assert str(close_binds[2]) == "infinity"  # the observed rectangle's own Valid-Time end
    assert str(close_binds[2]) not in (str(split["validFrom"]), str(split["until"]))
    assert str(close_binds[3]) == "infinity"  # the invariant Transaction-Time end
    assert str(close_binds[4]) == str(opening["at"])  # the observed in_z, gated LAST
    assert str(close_binds[4]) != str(split["at"])
    # The whole cross-check holds as authored.
    _assert_write_input_columns(case, "postgres")


def test_gated_rectangle_split_gate_bind_corruption_is_rejected() -> None:
    case = copy.deepcopy(_gated_split_case())
    # Corrupt the golden's observed-in_z gate bind so it no longer matches the
    # reconstructed rectangle: the gate is cross-checked against the row it inactivates
    # (drawn from the replayed history), so the ① ↔ ② gate MUST fail.
    case.then["statements"][1]["binds"][4] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_gated_rectangle_split_address_bind_corruption_is_rejected() -> None:
    case = copy.deepcopy(_gated_split_case())
    # Corrupt the golden's addressed Valid-Time end — the coordinate the pre-ADR-0046
    # shape never bound at all. It is reconstructed from the same replayed rectangle as
    # the gate, so an address that names no stored rectangle MUST fail.
    case.then["statements"][1]["binds"][2] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_has_temporal_gate_requires_the_transaction_start_word_bounded() -> None:
    # Direct seam check on the gated-close shape detector. Address and gate are separate
    # (ADR 0046): every close renders `thru_z = ? and out_z = ?`, so ONLY the trailing
    # Transaction-Time start (`in_z = ?`) marks a close gated. Matching is word-bounded,
    # so neither the address's own `out_z = ?` nor a Valid-Time `from_z = ?` decoy — the
    # coordinate the retired shape gated on — is ever read as the gate.
    address_only = "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?"
    gated = f"{address_only} and in_z = ?"
    valid_start_decoy = f"{address_only} and from_z = ?"
    assert _has_temporal_gate(gated, "in_z")
    assert not _has_temporal_gate(address_only, "in_z")
    assert not _has_temporal_gate(valid_start_decoy, "in_z")
    assert not _has_temporal_gate(gated, "min_z")  # a longer column is not a substring match


def test_has_temporal_gate_requires_the_gate_predicate_to_be_TRAILING() -> None:
    # The gate binds LAST, no exception (`m-opt-lock`), so a close that renders
    # `in_z = ?` anywhere but at the end is malformed — the observed start woven into
    # the address rather than appended after it. A detector that searched the whole
    # statement would accept that shape as a well-formed gated close and grade its five
    # binds against the five-value gated derivation, silently blessing the wrong
    # predicate order. Anchoring reports it UNGATED instead, whose four-bind derivation
    # its five placeholders cannot satisfy.
    woven = (
        "update position set out_z = ? where pos_id = ? and in_z = ? and thru_z = ? and out_z = ?"
    )
    assert not _has_temporal_gate(woven, "in_z")
    trailing = (
        "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ? and in_z = ?"
    )
    assert _has_temporal_gate(trailing, "in_z")


def test_close_weaving_the_gate_into_the_address_is_rejected() -> None:
    # The corpus-level consequence of the anchored detector: `m-bitemp-write-008`'s
    # gated close, re-spelled with its `and in_z = ?` moved ahead of the address's own
    # upper bounds. Placeholders and binds still both number five, so only the
    # gate-is-trailing rule separates it from the authored shape — it MUST raise.
    case = copy.deepcopy(_gated_split_case())
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    authored = close["sql"]["postgres"]
    woven = authored.replace(
        " and thru_z = ? and out_z = ? and in_z = ?",
        " and in_z = ? and thru_z = ? and out_z = ?",
    )
    assert woven != authored
    assert woven.count("?") == authored.count("?") == 5 == len(close["binds"])
    close["sql"]["postgres"] = woven
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_close_gating_on_the_valid_time_start_instead_of_in_z_is_rejected() -> None:
    # The retired shape gated a bitemporal close on the observed Valid-Time START
    # (`from_z = ?`); under ADR 0046 that coordinate is bound nowhere — the address
    # carries the Valid-Time END and the gate carries in_z alone. A close that swaps the
    # gate for a `from_z = ?` decoy still declares five placeholders and lines up with
    # its five authored gated binds, so a detector that accepted any trailing temporal
    # discriminator would treat it as gated and PASS. Requiring in_z specifically instead
    # reports the close ungated, and its five placeholders mismatch the derived four-bind
    # ungated shape, so it MUST raise.
    case = copy.deepcopy(_gated_split_case())
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    authored = close["sql"]["postgres"]
    assert _has_temporal_gate(authored, "in_z")  # authored is the gated shape
    decoy = authored.replace("and in_z = ?", "and from_z = ?")
    assert not _has_temporal_gate(decoy, "in_z")  # the decoy is NOT gated
    close["sql"]["postgres"] = decoy  # binds unchanged — still the five gated binds
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_gated_close_with_extra_placeholder_arity_mismatch_is_rejected() -> None:
    # A WELL-FORMED gated close (correctly detected as gated) must ALSO carry EXACTLY
    # the derived gated arity — five placeholders paired with the five
    # [at, pk, thru_z, out_z, in_z] binds. Here the close keeps its TRAILING gate but
    # gains a spurious SIXTH `from_z = ?` placeholder ahead of it, while the binds stay
    # at the five-value gated shape. The bind-count backstop (`_assert_write_values`)
    # still sees five == five, so ONLY the placeholder-vs-derived-shape arity check
    # catches the surplus placeholder — which MUST raise rather than tolerate it.
    case = copy.deepcopy(_gated_split_case())
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    authored = close["sql"]["postgres"]
    assert _has_temporal_gate(authored, "in_z")
    assert authored.count("?") == 5 and len(close["binds"]) == 5
    # The surplus predicate rides BEFORE the gate, so the gate still binds last.
    close["sql"]["postgres"] = authored.replace(" and in_z = ?", " and from_z = ? and in_z = ?")
    assert close["sql"]["postgres"].count("?") == 6
    assert _has_temporal_gate(close["sql"]["postgres"], "in_z")  # still gated-shaped
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _bitemporal_conflict_close_cases():
    """Bitemporal conflict-close cases (`m-bitemp-write-004` / `-005` / `-017` /
    `-018`): a Valid-Time + Transaction-Time dimension."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_conflict
        and any(
            dim.get("dimension") == "valid-time"
            for entity in case.model.entities
            for dim in entity.temporal_runtime_axes
        )
    ]


def test_bitemporal_conflict_close_input_holds_for_authored_cases() -> None:
    cases = _bitemporal_conflict_close_cases()
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-004",
        "m-bitemp-write-005",
        "m-bitemp-write-017",
        "m-bitemp-write-018",
    }
    for case in cases:
        # Must not raise: the close ① derives [at, pk, validEnd, infinity,
        # (observedTxStart under optimistic)] — the metamodel names the thru_z address
        # column, ① supplies its VALUE, which the metamodel cannot know.
        _assert_conflict_input(case, "postgres")


def _conflict_close_case(stem_prefix: str):
    cases = _bitemporal_conflict_close_cases()
    return next(case for case in cases if case.path.stem.startswith(stem_prefix))


def test_bitemporal_conflict_close_addresses_a_finite_valid_end() -> None:
    # m-bitemp-write-017 / -018 are the corpus' only witnesses for the FINITE arm of the
    # address: fixture rows R2 and R3 share pk, in_z, and the open out_z, so thru_z is
    # the sole discriminator between them. -017 addresses R2's finite end and -004 the
    # open one under the same mode, instant, and gate, so the two goldens differ by
    # exactly that bind — a close binding a constant infinity on both axes would pass
    # -004 and miss R2 entirely.
    bounded = _conflict_close_case("m-bitemp-write-017")
    unbounded = _conflict_close_case("m-bitemp-write-004")
    assert bounded.when["write"]["validEnd"] == "2024-06-01T00:00:00+00:00"
    assert unbounded.when["write"]["validEnd"] == "infinity"
    assert bounded.golden_statements("postgres") == unbounded.golden_statements("postgres")
    differing = [
        index
        for index, (left, right) in enumerate(
            zip(bounded.statement_binds(0), unbounded.statement_binds(0), strict=True)
        )
        if str(left) != str(right)
    ]
    assert differing == [2]  # the addressed thru_z, between the pk and the invariant out_z
    _assert_conflict_input(bounded, "postgres")


def test_bitemporal_conflict_close_valid_end_corruption_is_rejected() -> None:
    case = copy.deepcopy(_conflict_close_case("m-bitemp-write-017"))
    # Corrupt the addressed Valid-Time end VALUE: ①'s address bound no longer matches the
    # golden bind, so the bitemporal close ① ↔ ② cross-check MUST fail.
    case.when["write"]["validEnd"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_bitemporal_conflict_close_naming_a_second_coordinate_is_rejected() -> None:
    # A close writes no domain value and names exactly the address bound the metamodel
    # cannot supply. An ① carrying anything else — here the Valid-Time START the retired
    # gate shape bound — MUST be rejected rather than silently ordered into the binds.
    case = copy.deepcopy(_conflict_close_case("m-bitemp-write-004"))
    case.when["write"]["validStart"] = "2024-06-01T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_locking_bitemporal_conflict_close_renders_the_address_and_no_gate() -> None:
    # m-bitemp-write-018 is -017's locking sibling: the m-read-lock shared read lock,
    # not an observation, is what makes the write correct, so the golden renders the
    # SAME address and no `in_z = ?` gate, and the case authors no observedTxStart.
    locking = _conflict_close_case("m-bitemp-write-018")
    optimistic = _conflict_close_case("m-bitemp-write-017")
    (gated_statement,) = optimistic.golden_statements("postgres")
    assert locking.golden_statements("postgres") == [gated_statement.removesuffix(" and in_z = ?")]
    assert locking.observed_tx_start is None
    assert locking.statement_binds(0) == optimistic.statement_binds(0)[:-1]
    _assert_conflict_input(locking, "postgres")


def test_locking_bitemporal_conflict_close_rendering_a_gate_is_rejected() -> None:
    # Gating is concurrency-driven, never data-driven: a locking-mode close that renders
    # the observed-in_z gate anyway MUST be rejected, even though its binds line up.
    case = copy.deepcopy(_conflict_close_case("m-bitemp-write-018"))
    _assert_conflict_input(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][0]
    close["sql"]["postgres"] = f"{close['sql']['postgres']} and in_z = ?"
    close["binds"] = [*close["binds"], "2024-04-01T00:00:00+00:00"]
    with pytest.raises(CaseFailure):
        _assert_conflict_input(case, "postgres")


def test_rectangle_split_has_inactivate_plus_three_inserts() -> None:
    update_until = next(
        c for c in _phase8_cases() if "update-until" in c.tags and c.is_write_sequence
    )
    # The updateUntil step is 4 statements: 1 inactivate UPDATE + head/middle/tail
    # inserts. With the leading insert that opens the original, 5 statements total.
    step = next(s for s in update_until.write_sequence if s["mutation"] == "updateUntil")
    assert step["statements"] == 4
    assert len(update_until.golden_statements("postgres")) == 5


# --- temporal inheritance composition -----------------------------------------
#
# A temporal inheritance participant composes milestone-chaining writes and temporal reads
# with the strategy's routing + tag guard. Under table-per-hierarchy every EXISTING-ROW
# temporal statement (an audit close, a bitemporal inactivation) carries the tag GUARD
# right after the pk; chained inserts set the tag COLUMN. Under table-per-concrete-subtype
# every statement targets the subtype's own table with no tag. The temporal-only TPCS
# abstract `union all` witness carries temporal-selection binds PER BRANCH
# (Valid-Time-first, with no bind for history). Complete predicate, projection, and
# result-directive bind vectors remain owned by canonical goldens and execution checks.
# The temporal families are NEW (instrument / rate / reading / quote); the existing
# families stay non-temporal.


def _inheritance_case(prefix: str):
    return next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith(prefix))


def test_temporal_axes_are_inherited_by_concrete_subtypes() -> None:
    # The bitemporal axes declared on the abstract root are inherited by the concrete
    # subtype (the inheritance-aware harness flattens them in), so the concrete is temporal
    # and its shared-table DDL carries the milestone key PLUS the framework-owned tag column.
    model = load_model(COMPATIBILITY_ROOT, "models/instrument.yaml")
    bond = model.entity("Bond")
    assert bond.is_temporal
    assert {dim["dimension"] for dim in bond.temporal_runtime_axes} == {
        "valid-time",
        "transaction-time",
    }
    (create,) = ddl_for(model, "postgres")  # one shared `instrument` table
    assert "primary key (id, thru_z, out_z)" in create
    assert "kind" in create  # the framework-owned tag column, synthesized for the DDL

    # The table-per-concrete-subtype counterpart: each concrete owns its table, inherits the
    # axes, and carries the milestone key with NO tag column.
    rate = load_model(COMPATIBILITY_ROOT, "models/rate.yaml")
    deposit = rate.entity("DepositRate")
    assert deposit.is_temporal
    deposit_ddl = next(s for s in ddl_for(rate, "postgres") if "deposit_rate" in s)
    assert "primary key (id, thru_z, out_z)" in deposit_ddl
    assert "kind" not in deposit_ddl


def test_tph_txtime_terminate_close_is_tag_guarded() -> None:
    # m-inheritance-090: the audit-only close carries the tag guard among the identity
    # predicates — right after the pk, before the current-row out_z predicate.
    case = _inheritance_case("m-inheritance-090")
    close = case.golden_statements("postgres")[1]
    assert close == "update reading set out_z = ? where id = ? and kind = ? and out_z = ?"
    assert case.statement_binds(1)[1:3] == [1, "meter"]  # pk then the derived tagValue
    _assert_write_input_columns(case, "postgres")


def test_tph_bitemporal_inactivation_is_tag_guarded() -> None:
    # m-inheritance-094: the bitemporal inactivation carries the tag guard right after the
    # pk and BEFORE the per-axis upper bounds that address the rectangle; the chained head
    # insert sets the tag column from the subtype's tagValue.
    case = _inheritance_case("m-inheritance-094")
    inactivate = case.golden_statements("postgres")[1]
    assert inactivate == (
        "update instrument set out_z = ? where id = ? and kind = ? and thru_z = ? and out_z = ?"
    )
    assert case.statement_binds(1)[1:3] == [1, "bond"]
    _assert_write_input_columns(case, "postgres")


def test_tph_bitemporal_milestones_write_the_layout_slot_sequence() -> None:
    # m-inheritance-094: both the opening rectangle and the chained head write Bond's
    # applicable slots of the shared `instrument` table in one canonical sequence —
    # identity, discriminator, the root-owned then subtype-owned domain slots, and
    # finally the four temporal bounds. The sibling Stock's `ticker` slot is not
    # applicable to a Bond row and never enters the write shape, while the
    # inactivating close between them SETS only the Transaction-Time end column and
    # reads both axes' ends to address its rectangle.
    case = _inheritance_case("m-inheritance-094")
    order = _write_column_order(case, case.model.entity("Bond"))
    assert order == ("id", "kind", "price", "coupon", "from_z", "thru_z", "in_z", "out_z")
    opening, close, head = case.golden_statements("postgres")
    columns = ", ".join(order)
    assert opening.startswith(f"insert into instrument({columns}) values")
    assert head.startswith(f"insert into instrument({columns}) values")
    assert close == (
        "update instrument set out_z = ? where id = ? and kind = ? and thru_z = ? and out_z = ?"
    )
    # Every chained INSERT opens at the transaction instant with an open upper bound.
    in_z, out_z = order.index("in_z"), order.index("out_z")
    for index in (0, 2):
        binds = case.statement_binds(index)
        assert binds[in_z] == case.write_sequence[0 if index == 0 else 1]["at"]
        assert binds[out_z] == "infinity"


class _RecordingReadProvider:
    """A DB-free provider recording each read it is asked to run."""

    dialect = "postgres"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.queries.append(sql)
        return []


def test_bitemporal_observation_projects_the_temporal_slots_last() -> None:
    # The committed-rectangle read-back follows the Table Layout's canonical tier
    # order, so both dimensions' bounds trail every domain slot even though the
    # physical primary key selects the two ends from the identity and temporal
    # tiers alike.
    case = _inheritance_case("m-inheritance-094")
    layout = case.model.storage_layout.table("instrument")
    assert layout is not None
    provider = _RecordingReadProvider()
    _read_table(cast("Any", provider), layout, contributor_types(case.model))
    assert provider.queries == [
        "select t0.id, t0.kind, t0.price, t0.coupon, t0.ticker, "
        "t0.from_z, t0.thru_z, t0.in_z, t0.out_z from instrument t0"
    ]
    assert [slot.column for slot in layout.physical_primary_key] == ["id", "thru_z", "out_z"]


def test_bitemporal_committed_rows_cover_every_shared_table_slot() -> None:
    # The committed rectangles are graded over the shared Table Layout's COMPLETE slot
    # sequence, so a Bond row still records the sibling-only `ticker` column as null
    # rather than omitting it.
    case = _inheritance_case("m-inheritance-094")
    layout = case.model.storage_layout.table("instrument")
    assert layout is not None
    columns = {slot.column for slot in layout.columns}
    assert "ticker" in columns
    for row in case.expected_table_state["instrument"]:
        assert set(row) == columns
        assert row["ticker"] is None


def test_tpcs_bitemporal_milestones_write_each_concrete_table_layout() -> None:
    # m-inheritance-095: a table-per-concrete-subtype concrete writes its OWN table's
    # complete ancestry-derived sequence with no discriminator slot, and its committed
    # rows cover exactly that table's slots.
    case = _inheritance_case("m-inheritance-095")
    order = _write_column_order(case, case.model.entity("DepositRate"))
    assert order == ("id", "amount", "grade", "from_z", "thru_z", "in_z", "out_z")
    opening = case.golden_statements("postgres")[0]
    assert opening.startswith(f"insert into deposit_rate({', '.join(order)}) values")
    for row in case.expected_table_state["deposit_rate"]:
        assert set(row) == set(order)


def test_tph_temporal_close_missing_tag_guard_is_rejected() -> None:
    # Dropping the `and kind = ?` guard from a table-per-hierarchy temporal close leaves the
    # subtype's milestones indistinguishable in the shared table — it MUST fail.
    case = copy.deepcopy(_inheritance_case("m-inheritance-090"))
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    close["sql"]["postgres"] = "update reading set out_z = ? where id = ? and out_z = ?"
    close["binds"] = ["2024-08-01T00:00:00+00:00", 1, "infinity"]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tph_temporal_close_wrong_tag_bind_is_rejected() -> None:
    # The temporal close's tag bind is pinned to the model's tagValue; a wrong value MUST
    # fail (the tag is framework-derived, never authored).
    case = copy.deepcopy(_inheritance_case("m-inheritance-090"))
    case.then["statements"][1]["binds"][2] = "cash"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_terminate_routes_to_own_table_no_tag() -> None:
    # m-inheritance-095: the bitemporal inactivation targets the concrete deposit_rate table
    # with NO tag guard (contrast the table-per-hierarchy inactivation above).
    case = _inheritance_case("m-inheritance-095")
    inactivate = case.golden_statements("postgres")[1]
    assert inactivate == (
        "update deposit_rate set out_z = ? where id = ? and thru_z = ? and out_z = ?"
    )
    assert "kind" not in inactivate
    _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_close_routed_to_wrong_table_is_rejected() -> None:
    # A table-per-concrete-subtype temporal close MUST target the subtype's own table;
    # routing it elsewhere MUST fail the routing oracle.
    case = copy.deepcopy(_inheritance_case("m-inheritance-091"))
    _assert_write_input_columns(case, "postgres")  # sanity
    case.then["statements"][1]["sql"]["postgres"] = (
        "update wrong_table set out_z = ? where id = ? and out_z = ?"
    )
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_union_read_per_branch_temporal_selection_binds() -> None:
    # m-inheritance-093: the temporal abstract `union all` read carries the per-branch
    # selection binds — Valid-Time-first [b, b, infinity], repeated in alphabetical
    # branch order. The oracle derives them from the complete canonical selections.
    case = _inheritance_case("m-inheritance-093")
    assert set(_read_temporal_selections(case)) == {"valid-time", "transaction-time"}
    _assert_temporal_only_union_binds(case, "postgres")  # must not raise
    _assert_temporal_only_union_binds(case, "mariadb")  # the shared binds hold per dialect


@pytest.mark.parametrize(
    ("valid_tag", "valid_fields", "valid_binds"),
    [
        (
            "asOf",
            {"coordinate": "2024-03-01T00:00:00+00:00"},
            ["2024-03-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00"],
        ),
        (
            "asOfRange",
            {
                "start": "2024-03-01T00:00:00+00:00",
                "end": "2024-04-01T00:00:00+00:00",
            },
            ["2024-04-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00"],
        ),
        ("history", {}, []),
    ],
)
@pytest.mark.parametrize(
    ("tx_tag", "tx_fields", "tx_binds"),
    [
        (
            "asOf",
            {"coordinate": "2024-02-01T00:00:00+00:00"},
            ["2024-02-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00"],
        ),
        (
            "asOfRange",
            {
                "start": "2024-02-01T00:00:00+00:00",
                "end": "2024-05-01T00:00:00+00:00",
            },
            ["2024-05-01T00:00:00+00:00", "2024-02-01T00:00:00+00:00"],
        ),
        ("history", {}, []),
    ],
)
def test_tpcs_temporal_only_union_variants_compose(
    valid_tag: str,
    valid_fields: dict[str, str],
    valid_binds: list[str],
    tx_tag: str,
    tx_fields: dict[str, str],
    tx_binds: list[str],
) -> None:
    case = copy.deepcopy(_inheritance_case("m-inheritance-093"))
    case.object_query["temporal"] = {
        "transaction-time": {tx_tag: _selection_body(tx_tag, tx_fields)},
        "valid-time": {valid_tag: _selection_body(valid_tag, valid_fields)},
    }
    per_branch = [*valid_binds, *tx_binds]
    case.then["statements"][0]["binds"] = [*per_branch, *per_branch]

    assert set(_read_temporal_selections(case)) == {"valid-time", "transaction-time"}
    _assert_temporal_only_union_binds(case, "postgres")


def test_tpcs_temporal_union_oracle_does_not_derive_user_predicate_binds() -> None:
    case = copy.deepcopy(_inheritance_case("m-inheritance-093"))
    case.object_query["predicate"] = {
        "eq": {"attr": "parallax.compatibility.Rate.amount", "value": 2.5}
    }
    case.then["statements"][0]["binds"] = []

    _assert_temporal_only_union_binds(case, "postgres")


def test_tpcs_temporal_union_oracle_does_not_derive_result_shaping_binds() -> None:
    case = copy.deepcopy(_inheritance_case("m-inheritance-093"))
    case.object_query["limit"] = 1
    case.then["statements"][0]["binds"] = []

    _assert_temporal_only_union_binds(case, "postgres")


def test_tpcs_temporal_union_read_corrupt_temporal_selection_bind_is_rejected() -> None:
    # Corrupting the second branch's Valid-Time-start selection bind breaks the
    # independently derived per-branch vector, so the oracle MUST fail.
    case = copy.deepcopy(_inheritance_case("m-inheritance-093"))
    case.then["statements"][0]["binds"][3] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_temporal_only_union_binds(case, "postgres")


def test_tpcs_temporal_union_read_dropped_branch_binds_is_rejected() -> None:
    # Dropping the second branch's temporal-selection binds fails the per-branch arity.
    case = copy.deepcopy(_inheritance_case("m-inheritance-093"))
    case.then["statements"][0]["binds"] = case.then["statements"][0]["binds"][:3]
    with pytest.raises(CaseFailure):
        _assert_temporal_only_union_binds(case, "postgres")


def test_non_temporal_tpcs_union_read_temporal_bind_oracle_is_noop() -> None:
    # The temporal bind oracle is a no-op on a NON-temporal TPCS abstract union read.
    case = _inheritance_case("m-inheritance-050")
    _assert_temporal_only_union_binds(case, "postgres")  # must not raise (returns early)
