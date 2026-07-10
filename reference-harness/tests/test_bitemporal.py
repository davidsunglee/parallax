"""Unit tests for the Phase 8 full-bitemporal / business-temporal machinery (no
database).

These pin the DB-free invariants of the Phase 8 temporal slice: the bitemporal
DDL (a two-axis temporal entity's physical primary key spans BOTH as-of
fromColumns so the milestone rectangles are admissible), the temporal
classification of the new models (bitemporal vs unitemporal-business), and the
write-step-count consistency of the `*Until` rectangle-split write sequences (the
sum of per-step counts == goldenSql DML count == roundTrips). The full
apply-DML-and-assert-rectangle-state behavior and the both-axis as-of reads are
exercised end-to-end against real Postgres by the compatibility suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from reference_harness.case import discover_cases, load_model
from reference_harness.case_runner import (
    CaseFailure,
    _assert_conflict_input,
    _assert_temporal_union_binds,
    _assert_write_input_columns,
    _assert_write_step_count,
    _has_temporal_gate,
    _read_asof_pins,
)
from reference_harness.ddl_builder import ddl_for

_REPO_ROOT = Path(__file__).resolve().parents[2]
COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _case_id(stem: str) -> str:
    """The per-module id prefix of a case stem (drops the trailing ``-<slug>``)."""
    return re.match(r"(m-[a-z0-9-]+-\d{3})", stem).group(1)


def _position_model():
    return load_model(COMPATIBILITY_ROOT, "models/position.yaml")


def _reservation_model():
    return load_model(COMPATIBILITY_ROOT, "models/reservation.yaml")


_PHASE8_MODULES = ("m-temporal-read", "m-bitemp-write", "m-business-only")


def _phase8_cases():
    """The full-bitemporal + business-temporal single-entity cases (formerly the 08xx
    range): reads/writes on the bitemporal/business models, excluding the audit-only
    reads and the relationship-propagation deep-fetch cases (which also carry a
    temporal flavor but file under `m-navigate`)."""
    return [
        c
        for c in discover_cases(COMPATIBILITY_ROOT)
        if any(c.path.stem.startswith(f"{module}-") for module in _PHASE8_MODULES)
        and ("bitemporal" in c.tags or "business_temporal" in c.tags)
    ]


def test_position_is_bitemporal_with_both_axes() -> None:
    entity = _position_model().root_entity
    assert entity.is_temporal
    assert entity.definition["temporal"] == "bitemporal"
    axes = {dim["axis"] for dim in entity.as_of_attributes}
    assert axes == {"business", "processing"}


def test_reservation_is_unitemporal_business() -> None:
    entity = _reservation_model().root_entity
    assert entity.is_temporal
    assert entity.definition["temporal"] == "unitemporal-business"
    (dimension,) = entity.as_of_attributes
    assert dimension["axis"] == "business"


def test_bitemporal_ddl_primary_key_spans_both_as_of_from_columns() -> None:
    (create,) = ddl_for(_position_model(), "postgres")
    # The business key alone (pos_id) is not unique across rectangles; the
    # physical primary key MUST include BOTH axes' fromColumns (from_z, in_z) so a
    # business-bounded rectangle and its inactivated original coexist.
    assert "primary key (pos_id, from_z, in_z)" in create
    for column in ("from_z", "thru_z", "in_z", "out_z"):
        assert f"{column} timestamptz not null" in create


def test_bitemporal_unique_index_matches_physical_primary_key() -> None:
    entity = _position_model().root_entity
    unique_index = next(
        index for index in entity.definition["indices"] if index["name"] == "position_pk"
    )
    assert unique_index == {
        "name": "position_pk",
        "attributes": ["id", "businessFrom", "processingFrom"],
        "unique": True,
    }


def test_business_only_ddl_primary_key_spans_the_business_from_column() -> None:
    (create,) = ddl_for(_reservation_model(), "postgres")
    assert "primary key (res_id, from_z)" in create


def test_business_only_unique_index_matches_physical_primary_key() -> None:
    entity = _reservation_model().root_entity
    unique_index = next(
        index for index in entity.definition["indices"] if index["name"] == "reservation_pk"
    )
    assert unique_index == {
        "name": "reservation_pk",
        "attributes": ["id", "businessFrom"],
        "unique": True,
    }


def test_bitemporal_history_case_suppresses_both_axes() -> None:
    history_case = next(
        c for c in _phase8_cases() if c.path.stem == "m-temporal-read-016-bitemporal-history"
    )
    business_history = history_case.operation["history"]
    processing_history = business_history["operand"]["history"]
    assert business_history["asOfAttr"] == "Position.businessDate"
    assert processing_history["asOfAttr"] == "Position.processingDate"


def test_until_trio_write_step_counts_are_consistent() -> None:
    write_cases = [c for c in _phase8_cases() if c.is_write_sequence]
    assert write_cases, "no Phase 8 write-sequence cases discovered"
    for case in write_cases:
        # Must not raise: per-step counts sum to the DML count and roundTrips,
        # including the 4-statement updateUntil and 3-statement terminateUntil.
        _assert_write_step_count(case, "postgres")


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
    # The Phase 3 in-slice audit trio all carry ① (rows + at).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-audit-write-001",
        "m-audit-write-002",
        "m-audit-write-003",
    }
    for case in cases:
        # Must not raise: each audit-only ① derives in_z = at / out_z = infinity and
        # the full-row binds that cross-check the authored golden binds.
        _assert_write_input_columns(case, "postgres")


def test_temporal_write_input_at_corruption_is_rejected() -> None:
    case = next(
        c for c in _temporal_write_input_cases() if c.path.stem.startswith("m-audit-write-001")
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
        # Must not raise: the close binds [at, pk, infinity], every chained insert
        # opens at fresh processing [at, infinity), and the business window bounds
        # (businessFrom / until) appear among the chained inserts' business-axis binds.
        _assert_write_input_columns(case, "postgres")


def test_until_write_input_window_corruption_is_rejected() -> None:
    case = next(c for c in _until_write_cases() if c.path.stem.startswith("m-bitemp-write-001"))
    step = next(s for s in case.write_sequence if s.get("until"))
    # Corrupt the business valid-time window end: `until` no longer appears among the
    # chained inserts' business-axis binds, so the `*Until` ① ↔ ② window gate MUST
    # fail (the window bounds are DERIVED from `at`/`until`, never read from golden).
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
        # audit-only close-and-open), the close binds [at, pk, infinity], the chained
        # head / new-tail open at fresh processing [at, infinity), and businessFrom
        # appears among the chained inserts' business-axis binds (until is absent).
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


def test_plain_close_with_trailing_binds_but_no_gate_predicate_is_rejected() -> None:
    # The gated branch is decided by the SQL SHAPE, not the bind arity: a PLAIN
    # (non-gated) close whose golden binds carry spurious trailing values — even ones
    # that happen to match the observed rectangle's (from_z, in_z) — is a shape mismatch
    # (3 placeholders, 5 binds), which the loose branch tolerated as "gated". It MUST now
    # raise rather than reconstruct the open rectangle and pass.
    case = next(
        c for c in _plain_split_write_cases() if c.path.stem.startswith("m-bitemp-write-006")
    )
    # Sanity: as authored the plain split cross-checks cleanly.
    _assert_write_input_columns(case, "postgres")
    opening = next(s for s in case.write_sequence if s["mutation"] == "insert")
    observed_from = opening["rows"][0]["businessFrom"]
    observed_in = opening["at"]
    # The plain close is the second golden statement — confirm it is the NON-gated shape
    # (no `from_z = ?` / `in_z = ?` gate) before corrupting its binds.
    close = case.then["statements"][1]
    assert "from_z" not in close["sql"]["postgres"]
    assert "in_z" not in close["sql"]["postgres"]
    close["binds"] = [*close["binds"], observed_from, observed_in]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _gated_split_case():
    return next(c for c in _until_write_cases() if c.path.stem.startswith("m-bitemp-write-008"))


def test_gated_rectangle_split_close_reconstructs_the_observed_open_rectangle() -> None:
    # The optimistic gated split (`m-bitemp-write-008`) inactivates the observed
    # rectangle with `... and from_z = ? and in_z = ?`; the two trailing gate binds are
    # the observed rectangle's (businessFrom, in_z), DERIVED from the OPENING insert
    # step's row + `at` — distinct from the `updateUntil` window boundary (2024-03-01).
    case = _gated_split_case()
    opening = next(s for s in case.write_sequence if s["mutation"] == "insert")
    open_business_from = opening["rows"][0]["businessFrom"]
    open_at = opening["at"]
    # The golden close is the second statement (after the opening insert): its binds are
    # [at, pk, infinity, observedFromZ, observedInZ].
    close_binds = case.statement_binds(1)
    assert len(close_binds) == 5
    assert str(close_binds[3]) == str(open_business_from)  # observed from_z (not the window)
    assert str(close_binds[4]) == str(open_at)  # observed in_z
    # The whole cross-check holds as authored.
    _assert_write_input_columns(case, "postgres")


def test_gated_rectangle_split_gate_bind_corruption_is_rejected() -> None:
    case = _gated_split_case()
    # Corrupt the golden's observed-from_z gate bind so it no longer matches the
    # reconstructed open rectangle: the gate is cross-checked against the row it
    # inactivates (drawn from the replayed open row), so the ① ↔ ② gate MUST fail.
    case.then["statements"][1]["binds"][3] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_has_temporal_gate_requires_both_discriminators_word_bounded() -> None:
    # Direct seam check on the gated-close shape detector: "gated" requires BOTH the
    # business (`from_z = ?`) AND processing (`in_z = ?`) discriminators, matched
    # word-bounded. A close carrying only ONE (a PARTIAL gate) is NOT a valid gated
    # close; the plain current-row key (`out_z = ?`) alone is likewise not a gate.
    both = (
        "update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ? and in_z = ?"
    )
    only_from = "update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ?"
    only_in = "update position set out_z = ? where pos_id = ? and out_z = ? and in_z = ?"
    plain = "update position set out_z = ? where pos_id = ? and out_z = ?"
    assert _has_temporal_gate(both, "from_z", "in_z")
    assert not _has_temporal_gate(only_from, "from_z", "in_z")
    assert not _has_temporal_gate(only_in, "from_z", "in_z")
    assert not _has_temporal_gate(plain, "from_z", "in_z")


def test_partial_temporal_gate_missing_processing_discriminator_is_rejected() -> None:
    # A PARTIAL gate — only ONE of the two discriminators — must be REJECTED, never
    # tolerated as a valid gated close. Here the close keeps the business predicate
    # (`from_z = ?`) but drops the processing one (`in_z = ?`), swapping in a
    # `thru_z = ?` decoy so it still declares five placeholders (the gated arity) and
    # its authored five gated binds still line up. A detector that loosened to accept a
    # single predicate would treat it as gated, reconstruct the open rectangle, and
    # PASS; the BOTH-required shape check instead reports the close plain, so its five
    # placeholders mismatch the derived three-bind plain shape and MUST raise.
    case = _gated_split_case()
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    authored = close["sql"]["postgres"]
    assert _has_temporal_gate(authored, "from_z", "in_z")  # authored is the gated shape
    partial = authored.replace("in_z = ?", "thru_z = ?")
    assert "in_z = ?" not in partial and "from_z = ?" in partial
    assert not _has_temporal_gate(partial, "from_z", "in_z")  # partial is NOT gated
    close["sql"]["postgres"] = partial  # binds unchanged — still the five gated binds
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_gated_close_with_extra_placeholder_arity_mismatch_is_rejected() -> None:
    # A WELL-FORMED gated close (both discriminators present, correctly detected as
    # gated) must ALSO carry EXACTLY the derived gated arity — five placeholders paired
    # with the five [at, pk, infinity, from_z, in_z] binds. Here the close keeps both
    # gate predicates but gains a spurious SIXTH `thru_z = ?` placeholder while the binds
    # stay at the five-value gated shape. The bind-count backstop (`_assert_write_values`)
    # still sees five == five, so ONLY the placeholder-vs-derived-shape arity check
    # catches the surplus placeholder — which MUST raise rather than tolerate it.
    case = _gated_split_case()
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    authored = close["sql"]["postgres"]
    assert _has_temporal_gate(authored, "from_z", "in_z")
    assert authored.count("?") == 5 and len(close["binds"]) == 5
    close["sql"]["postgres"] = f"{authored} and thru_z = ?"  # sixth placeholder, binds unchanged
    assert _has_temporal_gate(close["sql"]["postgres"], "from_z", "in_z")  # still gated-shaped
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _business_write_cases():
    """Business-temporal-only milestone-chaining write cases
    (`m-business-only-001`-`m-business-only-003`)."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_write_sequence
        and "postgres" in case.golden_dialects
        and any(step.get("businessAt") for step in case.write_sequence)
    ]


def test_business_write_input_holds_for_authored_cases() -> None:
    cases = _business_write_cases()
    # The business-only insert / update-chaining / terminate trio all carry ①
    # (rows + businessAt).
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-business-only-001",
        "m-business-only-002",
        "m-business-only-003",
    }
    for case in cases:
        # Must not raise: each business-only ① derives from_z = businessAt /
        # thru_z = infinity and the full-row binds that cross-check the golden binds
        # (the same close-and-chain shape as the audit-only axis, driven by business
        # date rather than transaction instant).
        _assert_write_input_columns(case, "postgres")


def test_business_write_input_business_at_corruption_is_rejected() -> None:
    case = next(c for c in _business_write_cases() if c.path.stem.startswith("m-business-only-003"))
    step = next(s for s in case.write_sequence if s.get("businessAt"))
    # Corrupt the business instant: the DERIVED from_z bind no longer matches the
    # golden from_z bind, so the business-temporal ① ↔ ② gate MUST fail (from_z is
    # derived from `businessAt`, never read from the golden).
    step["businessAt"] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def _bitemporal_conflict_close_cases():
    """Bitemporal conflict-close cases (`m-bitemp-write-004` / `m-bitemp-write-005`):
    a business + processing axis."""
    return [
        case
        for case in discover_cases(COMPATIBILITY_ROOT)
        if case.is_conflict
        and any(
            dim.get("axis") == "business"
            for entity in case.model.entities
            for dim in entity.as_of_attributes
        )
    ]


def test_bitemporal_conflict_close_input_holds_for_authored_cases() -> None:
    cases = _bitemporal_conflict_close_cases()
    assert {_case_id(case.path.stem) for case in cases} >= {
        "m-bitemp-write-004",
        "m-bitemp-write-005",
    }
    for case in cases:
        # Must not raise: the close ① derives [at, pk, infinity, businessFrom,
        # observedInZ] — the metamodel names the from_z discriminator column, ①
        # supplies its VALUE (businessFrom), which the metamodel cannot know.
        _assert_conflict_input(case, "postgres")


def test_bitemporal_conflict_close_business_from_corruption_is_rejected() -> None:
    case = next(
        c
        for c in _bitemporal_conflict_close_cases()
        if c.path.stem.startswith("m-bitemp-write-004")
    )
    # Corrupt the business discriminator VALUE: the DERIVED from_z gate bind no longer
    # matches the golden bind, so the bitemporal close ① ↔ ② gate MUST fail.
    case.when["write"]["businessFrom"] = "1999-12-31T00:00:00+00:00"
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


# --- Phase 8 temporal inheritance composition (m-inheritance x m-audit/m-bitemp/m-sql) ---
#
# A temporal inheritance participant composes the milestone-chaining writes / as-of reads
# with the strategy's routing + tag guard. Under table-per-hierarchy every EXISTING-ROW
# temporal statement (an audit close, a bitemporal inactivation) carries the tag GUARD
# right after the pk; chained inserts set the tag COLUMN. Under table-per-concrete-subtype
# every statement targets the subtype's own table with no tag. A temporal TPCS abstract
# `union all` read carries the injected as-of predicate PER BRANCH (business-first, repeated
# in alphabetical branch order). The temporal families are NEW (instrument / rate /
# reading / quote); the existing families stay non-temporal.


def _inheritance_case(prefix: str):
    return next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.path.stem.startswith(prefix))


def test_temporal_axes_are_inherited_by_concrete_subtypes() -> None:
    # The bitemporal axes declared on the abstract root are inherited by the concrete
    # subtype (the inheritance-aware harness flattens them in), so the concrete is temporal
    # and its shared-table DDL carries the milestone key PLUS the framework-owned tag column.
    model = load_model(COMPATIBILITY_ROOT, "models/instrument.yaml")
    bond = model.entity("Bond")
    assert bond.is_temporal
    assert {dim["axis"] for dim in bond.as_of_attributes} == {"business", "processing"}
    (create,) = ddl_for(model, "postgres")  # one shared `instrument` table
    assert "primary key (id, from_z, in_z)" in create
    assert "kind" in create  # the framework-owned tag column, synthesized for the DDL

    # The table-per-concrete-subtype counterpart: each concrete owns its table, inherits the
    # axes, and carries the milestone key with NO tag column.
    rate = load_model(COMPATIBILITY_ROOT, "models/rate.yaml")
    deposit = rate.entity("DepositRate")
    assert deposit.is_temporal
    deposit_ddl = next(s for s in ddl_for(rate, "postgres") if "deposit_rate" in s)
    assert "primary key (id, from_z, in_z)" in deposit_ddl
    assert "kind" not in deposit_ddl


def test_tph_audit_terminate_close_is_tag_guarded() -> None:
    # m-inheritance-090: the audit-only close carries the tag guard among the identity
    # predicates — right after the pk, before the current-row out_z predicate.
    case = _inheritance_case("m-inheritance-090")
    close = case.golden_statements("postgres")[1]
    assert close == "update reading set out_z = ? where id = ? and kind = ? and out_z = ?"
    assert case.statement_binds(1)[1:3] == [1, "meter"]  # pk then the derived tagValue
    _assert_write_input_columns(case, "postgres")


def test_tph_bitemporal_inactivation_is_tag_guarded() -> None:
    # m-inheritance-094: the bitemporal inactivation carries the tag guard right after the
    # pk; the chained head insert sets the tag column from the subtype's tagValue.
    case = _inheritance_case("m-inheritance-094")
    inactivate = case.golden_statements("postgres")[1]
    assert inactivate == "update instrument set out_z = ? where id = ? and kind = ? and out_z = ?"
    assert case.statement_binds(1)[1:3] == [1, "bond"]
    _assert_write_input_columns(case, "postgres")


def test_tph_temporal_close_missing_tag_guard_is_rejected() -> None:
    # Dropping the `and kind = ?` guard from a table-per-hierarchy temporal close leaves the
    # subtype's milestones indistinguishable in the shared table — it MUST fail.
    case = _inheritance_case("m-inheritance-090")
    _assert_write_input_columns(case, "postgres")  # sanity: valid as authored
    close = case.then["statements"][1]
    close["sql"]["postgres"] = "update reading set out_z = ? where id = ? and out_z = ?"
    close["binds"] = ["2024-08-01T00:00:00+00:00", 1, "infinity"]
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tph_temporal_close_wrong_tag_bind_is_rejected() -> None:
    # The temporal close's tag bind is pinned to the model's tagValue; a wrong value MUST
    # fail (the tag is framework-derived, never authored).
    case = _inheritance_case("m-inheritance-090")
    case.then["statements"][1]["binds"][2] = "cash"
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_terminate_routes_to_own_table_no_tag() -> None:
    # m-inheritance-095: the bitemporal inactivation targets the concrete deposit_rate table
    # with NO tag guard (contrast the table-per-hierarchy inactivation above).
    case = _inheritance_case("m-inheritance-095")
    inactivate = case.golden_statements("postgres")[1]
    assert inactivate == "update deposit_rate set out_z = ? where id = ? and out_z = ?"
    assert "kind" not in inactivate
    _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_close_routed_to_wrong_table_is_rejected() -> None:
    # A table-per-concrete-subtype temporal close MUST target the subtype's own table;
    # routing it elsewhere MUST fail the routing oracle.
    case = _inheritance_case("m-inheritance-091")
    _assert_write_input_columns(case, "postgres")  # sanity
    case.then["statements"][1]["sql"]["postgres"] = (
        "update wrong_table set out_z = ? where id = ? and out_z = ?"
    )
    with pytest.raises(CaseFailure):
        _assert_write_input_columns(case, "postgres")


def test_tpcs_temporal_union_read_per_branch_asof_binds() -> None:
    # m-inheritance-093: the temporal abstract `union all` read carries the per-branch as-of
    # binds — business-first [b, b, infinity], repeated in alphabetical branch order. The
    # oracle recomputes them from the read's pin, independent of the authored golden.
    case = _inheritance_case("m-inheritance-093")
    assert _read_asof_pins(case) == {"business": "2024-06-01T00:00:00+00:00"}
    _assert_temporal_union_binds(case, "postgres")  # must not raise
    _assert_temporal_union_binds(case, "mariadb")  # the shared binds hold per dialect


def test_tpcs_temporal_union_read_corrupt_branch_asof_bind_is_rejected() -> None:
    # Corrupting the SECOND branch's business-from as-of bind (index 3) breaks the recomputed
    # per-branch propagation, so the oracle MUST fail.
    case = _inheritance_case("m-inheritance-093")
    case.then["statements"][0]["binds"][3] = "1999-12-31T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        _assert_temporal_union_binds(case, "postgres")


def test_tpcs_temporal_union_read_dropped_branch_binds_is_rejected() -> None:
    # Dropping the second branch's as-of binds entirely fails the per-branch arity (two
    # branches x three as-of binds each).
    case = _inheritance_case("m-inheritance-093")
    case.then["statements"][0]["binds"] = case.then["statements"][0]["binds"][:3]
    with pytest.raises(CaseFailure):
        _assert_temporal_union_binds(case, "postgres")


def test_non_temporal_tpcs_union_read_asof_oracle_is_noop() -> None:
    # The per-branch as-of oracle is a no-op on a NON-temporal TPCS abstract union read
    # (the existing document family), so it never touches the Phase 3-6 union cases.
    case = _inheritance_case("m-inheritance-050")
    _assert_temporal_union_binds(case, "postgres")  # must not raise (returns early)
