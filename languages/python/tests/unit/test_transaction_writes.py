"""Keyed write-verb unit tests for `parallax.snapshot.handle` (spec §5, Docker-free fake ports).

The instance-taking D-16 verbs and their neutral `_buffer` seam: the
buffer -> flush -> lower -> execute wiring proof, sparse-update no-op
elimination, the shared `validate_write` model-aware rejection matrix, the typed
KEYED temporal-window family (`update`/`terminate`/`update_until`/
`terminate_until`, and D-31's `insert`/`insert_until`), keyed window-order
validation, and the §5 prior-observation license enforced at the developer verb.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import (
    BALANCE,
    CONTACT,
    FIND_SQL,
    FIXED,
    INFINITY_INSTANT,
    INSERT_SQL,
    PAYMENT,
    PERSON_MIRROR_META,
    SHIPMENT,
    WHERE_POSITION_META,
    NoIoPort,
    RecordingPort,
    WherePosition,
    account_db,
    balance_row,
    db_for,
    grace,
    new_account,
)

import mirrored_models as mm
from parallax.conformance import models
from parallax.core import Entity, opt_lock
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import (
    FixedClock,
    WriteInstructionError,
    WriteRejectedError,
    validate_write,
)
from parallax.snapshot.handle import Database, Transaction

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Wiring: buffer -> flush -> lower_write -> execute_write on the connection.   #
# --------------------------------------------------------------------------- #
def test_commit_flushes_the_buffer_through_the_lowering_seam() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> str:
        tx.insert(new_account())
        return "done"

    assert account_db(port).transact(fn) == "done"
    assert port.ops == [
        ("begin",),
        ("write", INSERT_SQL, (7, "Newton", 5.00, 1)),
        ("commit",),
    ]


def test_update_lowers_to_its_keyed_dml() -> None:
    # m-unit-work-005, migrated to the m-opt-lock observation flow (COR-3
    # Phase 8 increment 3): a keyed update (SET the non-PK members, WHERE the
    # key, version advanced from THIS unit of work's own recorded
    # observation). The edited copy is built from a row `tx.find` fetches
    # INSIDE this transaction — a versioned update requires a prior
    # observation; an edited copy fetched outside the writing transaction
    # cannot be updated directly (python.md §5).
    port = RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.model_copy(update={"balance": Decimal("175.00")}))

    account_db(port).transact(fn)
    assert port.ops == [
        ("begin",),
        ("read", FIND_SQL, (1,)),
        (
            "write",
            POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
            (175.00, 2, 1),
        ),
        ("commit",),
    ]


def test_delete_of_an_observed_versioned_row_gates_on_the_observed_version() -> None:
    # m-unit-work-006, migrated to the m-opt-lock observation flow (COR-3
    # Phase 8 review remediation): a keyed DELETE of a versioned row requires
    # a PRIOR observation exactly like a keyed update (python.md §5) — the
    # deleted row must be fetched INSIDE this transaction first, and the
    # lowered DELETE binds that observed version.
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.delete(fetched)

    account_db(port).transact(fn)
    assert port.ops == [
        ("begin",),
        ("read", FIND_SQL, (3,)),
        (
            "write",
            POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"),
            (3, 1),
        ),
        ("commit",),
    ]


def test_delete_of_a_versioned_row_never_observed_raises() -> None:
    # An edited/deleted instance built OUTSIDE the writing transaction (never
    # fetched via THIS unit of work's own `tx.find`) carries no observation —
    # the framework never issues an implicit resolving read on behalf of a
    # keyed write, so the delete raises before any DML, exactly as an
    # unobserved keyed update does.
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete(grace())

    with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
        account_db(port).transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_versioned_update_conflict_aborts_the_whole_unit_of_work() -> None:
    # m-opt-lock's `updatedRows != 1` conflict signal, at the production
    # developer surface: the gated UPDATE's port-reported affected count (0,
    # simulating a concurrent writer) disagrees with the flush plan's
    # exactly-one expectation, so `OptimisticLockConflictError` raises and the
    # whole unit of work rolls back.
    port = RecordingPort(
        rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}], write_affected=0
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.model_copy(update={"balance": Decimal("175.00")}))

    with pytest.raises(opt_lock.OptimisticLockConflictError, match="Account"):
        account_db(port).transact(fn)
    assert ("rollback",) in port.ops
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1  # the gated update, attempted once, then aborted


# --------------------------------------------------------------------------- #
# D-31 (COR-3 Phase 8 increment 7 completion round): axis-attribute           #
# construction optionality + `tx.insert_until`, through the PUBLIC verbs.     #
# --------------------------------------------------------------------------- #
def test_bitemporal_insert_constructs_cleanly_and_stamps_the_business_from() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)  # no placeholder axis values
    port = RecordingPort()
    db = db_for(models.load_models()["branch"], port)

    db.transact(lambda tx: tx.insert(branch, business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC)))
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    sql = write_ops[0][1]
    binds = cast("tuple[object, ...]", write_ops[0][2])
    assert sql == POSTGRES.to_driver_sql(
        "insert into branch(br_id, name, from_z, thru_z, in_z, out_z, address) "
        "values (?, ?, ?, ?, ?, ?, ?)"
    )
    assert binds[2:6] == (
        "2024-01-01T00:00:00+00:00",
        "infinity",
        "2024-06-01T00:00:00+00:00",
        "infinity",
    )


def test_bitemporal_insert_until_opens_a_single_bounded_rectangle() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = RecordingPort()
    db = db_for(models.load_models()["branch"], port)

    db.transact(
        lambda tx: tx.insert_until(
            branch,
            business_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )
    )
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    binds = cast("tuple[object, ...]", write_ops[0][2])
    assert binds[2:6] == (
        "2024-03-01T00:00:00+00:00",
        "2024-09-01T00:00:00+00:00",
        "2024-06-01T00:00:00+00:00",
        "infinity",
    )


def test_insert_until_rejects_an_equal_or_reversed_window() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = RecordingPort()
    db = db_for(models.load_models()["branch"], port)
    same_instant = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match="business_from < until"):
        db.transact(
            lambda tx: tx.insert_until(branch, business_from=same_instant, until=same_instant)
        )
    assert not any(op[0] == "write" for op in port.ops)


def test_update_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # A `model_copy()` with no `update=` carries forward the SAME (empty)
    # Change Record: the sparse-update no-op rule (spec §3/§5).
    port = RecordingPort()
    fetched = mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=1)
    edited = fetched.model_copy(update={"balance": Decimal("100.00")})  # net-zero touch

    def fn(tx: Transaction) -> None:
        tx.update(edited)

    account_db(port).transact(fn)
    assert port.ops == [("begin",), ("commit",)]  # no write round trip at all


def test_row_naming_an_undeclared_member_is_rejected_at_buffer_time() -> None:
    # The instance-graduated verbs build their row from the compiled entity's
    # OWN declared members, so an undeclared member can no longer be smuggled
    # in through `tx.insert`; the member-name honesty gate still protects the
    # lower-level neutral document route directly (`Transaction._buffer`). An
    # otherwise-COMPLETE row isolates this defect from `validate_write` (which
    # runs first, COR-3 Phase 8 increment 2, and only ever walks Account's OWN
    # declared members — it never itself notices a stray extra key).
    port = RecordingPort()
    with pytest.raises(WriteInstructionError, match="shoe_size"):
        account_db(port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Account",
                {"id": 1, "owner": "Newton", "balance": 5.00, "version": 1, "shoe_size": 9},
            )
        )
    assert ("write", INSERT_SQL, (1, 9)) not in port.ops


# --------------------------------------------------------------------------- #
# validate_write (COR-3 Phase 8 increment 2, m-value-object write validation  #
# x m-inheritance concrete-subtype write protocol): the SAME model-aware      #
# validator the conformance engine's rejected lane calls for the corpus's     #
# `when.write` cases (m-value-object-039..044 / m-inheritance-086..089) — one #
# validator, two callers (design 37 "Patterns to follow"), pinned per rule at #
# this seam. It runs BEFORE `validate_instruction` (see `_buffer`'s own       #
# comment): its inheritance payload-shape rules classify a framework-owned    #
# metadata key or a cross-branch field more specifically than the generic     #
# member-name-honesty gate ever could.                                       #
# --------------------------------------------------------------------------- #
def test_engine_and_transaction_buffer_share_the_identical_write_validator() -> None:
    # Neither caller forks its own copy of the shared validator, so a rule
    # dropped from the ONE implementation fails both lanes identically.
    from parallax.conformance import engine as engine_module
    from parallax.snapshot.handle import _transaction as transaction_module

    assert engine_module.validate_write is validate_write  # pyright: ignore[reportPrivateImportUsage]
    assert transaction_module.validate_write is validate_write  # pyright: ignore[reportPrivateImportUsage]


def test_buffer_rejects_a_required_attribute_missing_at_any_depth() -> None:
    # m-value-object-039's own payload: `address.street` (depth 1) absent.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Contact",
                {
                    "id": 1,
                    "name": "Acme",
                    "address": {
                        "city": "Oslo",
                        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
                    },
                },
            )
        )
    assert exc_info.value.rule == "write-required-attribute-missing"


def test_buffer_rejects_a_required_value_object_missing() -> None:
    # m-value-object-044's own payload: the required top-level `destination`
    # value object is entirely absent.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(SHIPMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "Shipment", {"id": 5, "name": "Express"}
            )
        )
    assert exc_info.value.rule == "write-required-value-object-missing"


def test_buffer_rejects_a_value_type_mismatch() -> None:
    # m-value-object-043's own payload: `address.street` bound the number 42.
    # This corpus case's own idiomatic-surface spelling is unreachable through
    # `tx.insert` (Pydantic's own field coercion raises first, constructing
    # `ContactAddress(street=42, ...)` never even completes) — a SANCTIONED
    # exception, ledger D-32 (S5, COR-3 Phase 8 increment 7 remediation), so
    # this proof exercises the shared validator directly through the private
    # `_buffer` seam instead, exactly like its two siblings above.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Contact",
                {
                    "id": 5,
                    "name": "Echo",
                    "address": {
                        "street": 42,
                        "city": "Oslo",
                        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
                    },
                },
            )
        )
    assert exc_info.value.rule == "write-value-type-mismatch"


def test_buffer_rejects_a_keyless_inheritance_write() -> None:
    # m-inheritance-089's own payload: no primary-key attribute at all.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "CardPayment", {"amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "subtype-write-set-based-unsupported"


def test_buffer_rejects_framework_owned_metadata() -> None:
    # m-inheritance-087's own payload: an authored `tagValue`.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "CardPayment", {"id": 10, "amount": 200.00, "tagValue": "card"}
            )
        )
    assert exc_info.value.rule == "subtype-write-metadata-field"


def test_buffer_rejects_a_sibling_branch_attribute() -> None:
    # m-inheritance-086's own payload: both CardPayment's and CashPayment's
    # own columns, so no single concrete subtype accepts every field.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Payment",
                {"id": 10, "amount": 200.00, "cardNetwork": "Visa", "tendered": 25.00},
            )
        )
    assert exc_info.value.rule == "subtype-write-sibling-attribute"


def test_buffer_rejects_an_abstract_write_target() -> None:
    # m-inheritance-088's own payload: a well-formed CardPayment-shaped write
    # aimed at the abstract root `Payment`.
    port = RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "Payment", {"id": 10, "amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "abstract-write-target"


def test_sparse_update_does_not_trip_required_attribute_missing_for_an_untouched_field() -> None:
    # The no-drift guard for CURRENTLY-LEGAL writes: a sparse keyed update (an id +
    # balance row omitting the required `owner`) must NOT be rejected — an absent
    # top-level member is untouched, never a violation, on any mutation but
    # `insert`. The version advances from this unit of work's own recorded
    # observation (`tx.find`), never a row-carried value (`m-opt-lock`).
    port = RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx._buffer(  # pyright: ignore[reportPrivateUsage]
            "update", "Account", {"id": 1, "balance": 175.00}
        )

    account_db(port).transact(fn)
    expected = (
        "write",
        POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
        (175.00, 2, 1),
    )
    assert expected in port.ops


def _position_row_dt() -> Row:
    """The KEYED-verb tests' own row fixture: real ``datetime`` values (never
    the bare ISO strings :func:`_position_row` uses) — a KEYED verb's own
    first read runs through the ordinary developer-facing ``tx.find`` (wrap
    into a real node, milestone-edge computation, `parallax.snapshot.handle`),
    unlike a ``_where`` verb's internal resolving read, which never wraps."""
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("100.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY_INSTANT,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY_INSTANT,
    }


# --------------------------------------------------------------------------- #
# Typed KEYED temporal-window verbs (COR-3 Phase 8 increment 7): `update`'s    #
# own optional bitemporal `business_from`, `terminate`, `update_until`, and    #
# `terminate_until` — the KEYED siblings of `update_where` / `terminate_where` #
# / `update_until_where` / `terminate_until_where`, sharing the SAME           #
# `_buffer` seam and the SAME `validate_business_from` gate, so a keyed and a  #
# predicate-selected write over the identical bitemporal correction lower to  #
# the identical rectangle split (`m-bitemp-write-001/002/006/007`'s own       #
# witnessed shape, replayed here through the KEYED verb instead of `_where`). #
# --------------------------------------------------------------------------- #
def test_keyed_update_lowers_a_plain_bitemporal_correction() -> None:
    # m-bitemp-write-006 "plain-update-split", replayed through the KEYED verb:
    # close + head (old) + new tail.
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update(
            fetched.model_copy(update={"value": Decimal("200.00")}), business_from=business_from
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head (old) + new tail


def test_keyed_terminate_lowers_a_plain_bitemporal_termination() -> None:
    # m-bitemp-write-007 "plain-terminate", replayed through the KEYED verb:
    # close + head only (no tail).
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate(fetched, business_from=business_from)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only


def test_keyed_update_until_lowers_the_rectangle_split() -> None:
    # m-bitemp-write-001 "update-until-rectangle-split", replayed through the
    # KEYED verb: close + head + middle + tail.
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail


def test_keyed_update_until_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # The SAME sparse-update no-op rule `update` applies (spec §3/§5): a
    # `model_copy()` whose Change Record nets to zero issues no DML at all --
    # but only AFTER its (here, valid) business window is validated (R2,
    # COR-3 Phase 7 increment 7 round-2: window validation runs BEFORE the
    # no-op return, for every window verb, never the reverse -- see the
    # sibling equal-bounds pin immediately below for the corrected
    # precedence made visible).
    port = RecordingPort()
    fetched = WherePosition(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        business_to=INFINITY_INSTANT,
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=INFINITY_INSTANT,
    )
    edited = fetched.model_copy(update={"value": Decimal("100.00")})  # net-zero touch
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until(edited, business_from=business_from, until=until)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_keyed_update_until_with_an_empty_change_set_still_rejects_equal_bounds() -> None:
    # R2 (COR-3 Phase 7 increment 7 round-2): window validation runs BEFORE
    # the empty-effective-change-set no-op return -- equal bounds reject even
    # when the edited copy's own Change Record nets to zero. The prior round
    # deliberately kept the no-op-first ordering, matching what it believed
    # was the existing test's documented precedence (the sibling test above,
    # pre-fix); the reviewer ruled that precedence WRONG per spec §5 ("all
    # validated at build") -- this is the corrected behavior.
    port = RecordingPort()
    fetched = WherePosition(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        business_to=INFINITY_INSTANT,
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=INFINITY_INSTANT,
    )
    edited = fetched.model_copy(update={"value": Decimal("100.00")})  # net-zero touch
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until(edited, business_from=business_from, until=business_from)  # EQUAL bounds

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the no-op check


def test_keyed_update_until_with_a_naive_until_raises_the_proper_value_error() -> None:
    # R2: a naive `until` (no tzinfo) must raise the SAME `ValueError` shape
    # `validate_business_from`'s own `instant_literal` normalization raises
    # for a naive `business_from` (never a bare `TypeError` leaked by
    # comparing a naive `until` against an already-aware `business_from`,
    # the pre-fix defect: comparison ran before normalization).
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    naive_until = dt.datetime(2024, 9, 1)  # NAIVE -- no tzinfo

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=naive_until,
        )

    # `pytest.raises(ValueError, ...)` itself is the pin against the pre-fix
    # leak: `TypeError` is not a `ValueError`, so an un-normalized comparison
    # would escape uncaught here rather than silently satisfy this block.
    with pytest.raises(ValueError, match="naive datetime"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_until_lowers_head_and_tail_only() -> None:
    # m-bitemp-write-002 "terminate-until", replayed through the KEYED verb:
    # close + head + tail (no middle).
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate_until(fetched, business_from=business_from, until=until)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head + tail


def test_keyed_update_on_a_bitemporal_target_without_business_from_raises() -> None:
    port = RecordingPort(rows=[_position_row_dt()])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update(fetched.model_copy(update={"value": Decimal("200.00")}))

    with pytest.raises(ValueError, match="requires business_from"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_on_a_non_temporal_target_forbids_business_from() -> None:
    port = RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.terminate(fetched, business_from=FIXED)

    with pytest.raises(ValueError, match="takes no business_from"):
        account_db(port).transact(fn)


# --------------------------------------------------------------------------- #
# Window-order validation (S4, COR-3 Phase 8 increment 7 remediation):        #
# `python.md` §5 "the `*_until` trio additionally requires `until`, with      #
# `business_from < until` ... all validated at build" — an EQUAL and a        #
# REVERSED window both reject, at the verb call, before any buffering, for    #
# BOTH the KEYED (`update_until`/`terminate_until`) and `_where`              #
# (`update_until_where`/`terminate_until_where`) verb families — the ONE      #
# shared `validate_until` validator (`parallax.snapshot.handle`) makes all    #
# four converge.                                                              #
# --------------------------------------------------------------------------- #
def test_keyed_update_until_rejects_an_equal_window_bound() -> None:
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=business_from,
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_until_rejects_a_reversed_window_bound() -> None:
    port = RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)  # BEFORE business_from — reversed

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate_until(fetched, business_from=business_from, until=until)

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


# --------------------------------------------------------------------------- #
# The §5 prior-observation license for keyed TEMPORAL update/terminate        #
# (checkpoint-4 Spec finding 1): the temporal sibling of the versioned        #
# `require_observed` rule, enforced at the developer verb.                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
def test_unobserved_temporal_terminate_raises_before_any_dml(concurrency: str) -> None:
    # A keyed temporal close of a milestone this unit of work never observed
    # is a read-before-write programming error in EITHER mode: in locking
    # mode the observing find's shared lock is the ungated close's ONLY
    # protection; in optimistic mode there is no observed `in_z` to gate on.
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.terminate(mm.Balance(id=1, acct_num="A-1", value=Decimal("5.00")))

    with pytest.raises(opt_lock.UnobservedMilestoneError, match="transaction-scoped find"):
        db.transact(fn, concurrency=cast("Any", concurrency))
    assert not any(op[0] == "write" for op in port.ops)


def test_unobserved_temporal_update_from_a_cross_transaction_copy_raises() -> None:
    # Provenance alone is not a license: a copy edited from a node ANOTHER
    # scope's read materialized (a plain `db.find`, no unit of work) reaches
    # `tx.update` with no transaction-scoped observation — the §5 rule names
    # "the milestone THIS unit of work observed", so it raises (the
    # stale-web-edit recipe's in-transaction re-fetch is the sanctioned
    # spelling for transported coordinates).
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    def fn(tx: Transaction) -> None:
        tx.update(node.model_copy(update={"value": Decimal("9.00")}))

    with pytest.raises(opt_lock.UnobservedMilestoneError, match="transaction-scoped find"):
        db.transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_same_transaction_insert_then_temporal_update_is_licensed() -> None:
    # Read-your-own-writes exemption: this transaction's OWN buffered insert
    # IS the provenance (`m-audit-write-008`'s same-transaction coalescing
    # shape) — no observation lookup applies, and the planner folds the pair
    # into the single INSERT carrying the updated value.
    port = RecordingPort()
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fresh = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(fresh)
        tx.update(fresh.model_copy(update={"value": Decimal("2.00")}))

    db.transact(fn)
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1  # coalesced to one INSERT
    assert Decimal("2.00") in cast("tuple[object, ...]", write_ops[0][2])


# --------------------------------------------------------------------------- #
# The KEYED verbs' own entity-class guard (`_write_inputs.                     #
# entity_record_of_instance`). Placed beside the `NoIoPort` harness above,     #
# which is the only fixture it needs — it travelled here with the rest of the  #
# keyed-verb region in COR-42 Phase 5, the same way Phase 4's replacement      #
# observation tests travelled with the reads region.                           #
# --------------------------------------------------------------------------- #
def test_a_keyed_verb_refuses_an_instance_of_an_uncompiled_class() -> None:
    # `Entity` (the frontend BASE) is never itself compiled into a metamodel
    # record — `EntityMeta.__new__` short-circuits for a class with no
    # Parallax-entity base — so an instance of it is a registered-class lookup
    # miss while still satisfying every caller's `EntityBase` annotation. The
    # keyed verbs must name that as a TypeError rather than fail later on a
    # `None` record; the raising port proves the guard runs before any I/O.
    def fn(tx: Transaction) -> None:
        tx.delete(Entity())

    with pytest.raises(TypeError, match="Entity is not a registered Parallax entity class"):
        Database.connect(NoIoPort(), PERSON_MIRROR_META, clock=FixedClock(FIXED)).transact(fn)
