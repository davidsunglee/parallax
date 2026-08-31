"""Keyed write-verb unit tests for `parallax.snapshot.handle` (spec §5, Docker-free fake ports).

The instance-taking verbs and their neutral `_buffer` seam: the
buffer -> flush -> lower -> execute wiring proof, sparse-update no-op
elimination, the shared `validate_write` model-aware rejection matrix, the typed
KEYED temporal-window family (`update`/`terminate`/`update_until`/
`terminate_until`, and `insert`/`insert_until`), keyed window-order
validation, and the §5 prior-observation license enforced at the developer verb.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import _mixed_strategy_model as mx
import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    CONTACT,
    FIND_SQL_LOCKED,
    FIND_SQL_UNLOCKED,
    FIXED,
    INFINITY_INSTANT,
    INSERT_SQL,
    PAYMENT,
    PERSON,
    SHIPMENT,
    WHERE_POSITION_META,
    WherePosition,
    account_db,
    balance_row,
    db_for,
    grace,
    new_account,
)

from _support import mirrored_models as mm
from _support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance.class_models import MODELS
from parallax.conformance.read_models import CardPayment, Payment, Person
from parallax.conformance.vo_models import CUSTOMER_MODEL, Contact, Customer, Shipment
from parallax.core import LATEST, Attr, DomainModel, Entity, attr
from parallax.core.base import InstantError, PresentDocument
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES
from parallax.core.entity import (
    EntityGraphWriter,
    EntityRowError,
    NodeHandle,
    graph_construction_of,
)
from parallax.core.unit_work import (
    FixedClock,
    ObjectKey,
    OptimisticLockConflictError,
    RetainedObservation,
    StaleWriteError,
    VersionedStateKey,
    VersionObservation,
    WriteInstructionError,
    WriteRejectedError,
    instructions,
)
from parallax.snapshot import InvalidData
from parallax.snapshot.handle import (
    KEYED_WRITE_VALUE_CODES,
    Database,
    KeyedWriteValueError,
    Transaction,
    TransactionTimePinReadOnlyError,
    WriteEvidenceError,
)


# --------------------------------------------------------------------------- #
# Wiring: buffer -> flush -> stream_lowered -> execute_write on the connection.#
# --------------------------------------------------------------------------- #
def test_commit_flushes_the_buffer_through_the_lowering_seam() -> None:
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> str:
        tx.insert(new_account())
        return "done"

    assert account_db(port).transact(fn) == "done"
    assert port.calls == [
        BeginCall(),
        WriteCall(INSERT_SQL, (7, "Newton", 5.00, 1)),
        CommitCall(),
    ]


def test_keyed_insert_through_the_verb_follows_the_entity_layout_slot_order() -> None:
    # The developer verb reaches the SAME lowering seam the conformance engine
    # does, so a table-per-hierarchy concrete's INSERT emits its applicable
    # shared-table slots in canonical Table order — the derived `kind`
    # discriminator at its Discriminator-tier position between the model key and
    # the domain slots, never appended after them and never authored.
    port = ScriptedPort(Transact(Write()))
    db_for(PAYMENT, port).transact(
        lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
            "insert",
            CardPayment.identity,
            {"cardNetwork": "Visa", "id": 10, "amount": Decimal("200.00")},
        )
    )
    assert port.calls == [
        BeginCall(),
        WriteCall(
            POSTGRES.to_driver_sql(
                "insert into payment(id, kind, amount, card_network) values (?, ?, ?, ?)"
            ),
            (10, "card", Decimal("200.00"), "Visa"),
        ),
        CommitCall(),
    ]


def test_update_lowers_to_its_keyed_dml() -> None:
    # m-unit-work-005, migrated to the m-opt-lock observation flow: a keyed
    # update (SET the non-PK members, WHERE the key, version advanced from the
    # observation the source value itself retained). The edited copy is built
    # from a row `tx.find` fetches INSIDE this transaction, which is what an
    # effective-Locking target requires; an effective-Optimistic one may import
    # a standalone source's own observation instead (python.md §5).
    #
    # `Account` declares an explicit version, so the default `optimistic`
    # preference resolves it to the Optimistic strategy: the find takes no
    # shared lock and the update carries the observed-version gate.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.edit(balance=Decimal("175.00")))

    account_db(port).transact(fn)
    assert port.calls == [
        BeginCall(),
        ReadCall(FIND_SQL_UNLOCKED, (1,)),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update account set balance = ?, version = ? where id = ? and version = ?"
            ),
            (175.00, 2, 1, 1),
        ),
        CommitCall(),
    ]


def test_delete_of_an_observed_versioned_row_is_ungated_in_locking_mode() -> None:
    # m-unit-work-006, migrated to the m-opt-lock observation flow: a keyed
    # DELETE of a versioned row requires
    # a PRIOR observation exactly like a keyed update (python.md §5) — the
    # deleted row must be fetched INSIDE this transaction first, under the
    # shared read lock the `locking` preference this test declares produces.
    # The observation licenses the write; under the Locking strategy it renders
    # no gate, exactly as a keyed update does.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.delete(fetched)

    account_db(port).transact(fn, concurrency="locking")
    assert port.calls == [
        BeginCall(),
        ReadCall(FIND_SQL_LOCKED, (3,)),
        WriteCall(POSTGRES.to_driver_sql("delete from account where id = ?"), (3,)),
        CommitCall(),
    ]


def test_delete_of_a_versioned_row_no_read_produced_raises() -> None:
    # A plainly constructed instance carries no Source Hint at all, so it
    # observed no state and the Optimistic strategy has nothing to gate on — the
    # framework never issues an implicit resolving read on behalf of a keyed
    # write, so the delete raises at the verb, before any DML.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        tx.delete(grace())

    with pytest.raises(WriteEvidenceError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-evidence-unavailable"
    assert refusal.value.object_key == ObjectKey(mm.Account.identity, (("id", 3),))
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_versioned_update_shortfall_in_locking_mode_is_a_stale_write() -> None:
    # m-opt-lock's `updatedRows != 1` signal at the production developer
    # surface, under the explicit `locking` preference: the UPDATE is ungated
    # there, so its zero-row shortfall is the non-retriable stale write rather
    # than the retriable optimistic conflict — classification follows the gate,
    # uniformly across update, delete, and close. The whole unit of work still
    # rolls back.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]),
            Write(affected=0),
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.edit(balance=Decimal("175.00")))

    with pytest.raises(StaleWriteError, match="Account"):
        account_db(port).transact(fn, concurrency="locking")
    assert RollbackCall() in port.calls
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 1  # the ungated update, attempted once, then aborted


def test_versioned_update_shortfall_in_optimistic_mode_is_a_lock_conflict() -> None:
    # The gated counterpart of the locking-mode shortfall above, pinning the
    # other direction of the same rule: optimistic mode renders the version
    # gate, so a zero-row shortfall IS a detected lost update and raises the
    # retriable `OptimisticLockConflictError`.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]),
            Write(affected=0),
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.edit(balance=Decimal("175.00")))

    with pytest.raises(OptimisticLockConflictError, match="Account"):
        account_db(port).transact(fn, concurrency="optimistic")
    assert RollbackCall() in port.calls


# --------------------------------------------------------------------------- #
# ONE default transaction over two Entities whose Optimistic Lock Facets       #
# disagree: both strategies, both halves (read lock and write gate), one       #
# commit (m-unit-work "Strategy selection"; m-opt-lock). The read half alone   #
# is `test_transaction_reads.py`'s per-level pair; these two carry it through  #
# the writes those reads license, graded at the port they reach.               #
# --------------------------------------------------------------------------- #
def _mixed_port() -> ScriptedPort:
    return ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "total": Decimal("10.00"), "version": 1}]),
            Read(rows=[{"id": 5, "consignment_id": 1, "carrier": "Hansa"}]),
            Write(times=2),
        )
    )


def _mix_strategies(tx: Transaction) -> None:
    consignment = tx.find(
        mx.Consignment.where(mx.Consignment.id == 1).include(mx.Consignment.legs)
    ).result()
    tx.update(consignment.edit(total=Decimal("20.00")))
    tx.update(consignment.legs[0].edit(carrier="Baltic"))


def test_one_default_transaction_gates_the_versioned_write_and_locks_the_unversioned_read() -> None:
    port = _mixed_port()
    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(_mix_strategies)
    assert port.calls == [
        BeginCall(),
        ReadCall(
            POSTGRES.to_driver_sql(
                "select t0.id, t0.total, t0.version from consignment t0 where t0.id = ?"
            ),
            (1,),
        ),
        ReadCall(
            POSTGRES.to_driver_sql(
                "select t0.id, t0.consignment_id, t0.carrier from consignment_leg t0 "
                "where t0.consignment_id in (?) for share of t0"
            ),
            (1,),
        ),
        WriteCall(
            POSTGRES.to_driver_sql(
                "update consignment set total = ?, version = ? where id = ? and version = ?"
            ),
            (20.00, 2, 1, 1),
        ),
        WriteCall(
            POSTGRES.to_driver_sql("update consignment_leg set carrier = ? where id = ?"),
            ("Baltic", 5),
        ),
        CommitCall(),
    ]


def test_one_preference_produces_both_behaviors_across_two_entities() -> None:
    # One resolved Concurrency Preference, never a per-Entity strategy — and
    # each statement carries what its own Entity's Effective Concurrency
    # Strategy produced, which is where the lock and the gate are readable.
    port = _mixed_port()
    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(_mix_strategies)
    assert [(type(op), op.sql) for op in port.calls if isinstance(op, (ReadCall, WriteCall))] == [
        (
            ReadCall,
            POSTGRES.to_driver_sql(
                "select t0.id, t0.total, t0.version from consignment t0 where t0.id = ?"
            ),
        ),
        (
            ReadCall,
            POSTGRES.to_driver_sql(
                "select t0.id, t0.consignment_id, t0.carrier from consignment_leg t0 "
                "where t0.consignment_id in (?) for share of t0"
            ),
        ),
        (
            WriteCall,
            POSTGRES.to_driver_sql(
                "update consignment set total = ?, version = ? where id = ? and version = ?"
            ),
        ),
        (
            WriteCall,
            POSTGRES.to_driver_sql("update consignment_leg set carrier = ? where id = ?"),
        ),
    ]


# --------------------------------------------------------------------------- #
# Axis-attribute construction optionality + `tx.insert_until`, through the    #
# PUBLIC verbs.                                                               #
# --------------------------------------------------------------------------- #
def test_bitemporal_insert_constructs_cleanly_and_stamps_the_valid_from() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)  # no placeholder axis values
    port = ScriptedPort(Transact(Write()))
    db = db_for(MODELS["branch"], port)

    db.transact(lambda tx: tx.insert(branch, valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC)))
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 1
    sql = write_ops[0].sql
    binds = write_ops[0].binds
    assert sql == POSTGRES.to_driver_sql(
        "insert into branch(br_id, name, from_z, thru_z, in_z, out_z, address) "
        "values (?, ?, ?, ?, ?, ?, ?)"
    )
    assert binds[2:6] == (
        dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "infinity",
        FIXED,
        "infinity",
    )


def test_bitemporal_insert_until_opens_a_single_bounded_rectangle() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = ScriptedPort(Transact(Write()))
    db = db_for(MODELS["branch"], port)

    db.transact(
        lambda tx: tx.insert_until(
            branch,
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )
    )
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 1
    binds = write_ops[0].binds
    assert binds[2:6] == (
        dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        FIXED,
        "infinity",
    )


def test_insert_until_rejects_an_equal_or_reversed_window() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = ScriptedPort(Transact())
    db = db_for(MODELS["branch"], port)
    same_instant = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match="valid_from < until"):
        db.transact(lambda tx: tx.insert_until(branch, valid_from=same_instant, until=same_instant))
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_update_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # An `edit()` with no changes carries forward the SAME (empty)
    # Change Record: the sparse-update no-op rule (spec §3/§5).
    port = ScriptedPort(
        Transact(Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]))
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.edit(balance=Decimal("100.00")))  # net-zero touch

    account_db(port).transact(fn)
    # The read happened; the write never did.
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_UNLOCKED, (1,)), CommitCall()]


def test_row_naming_an_undeclared_member_is_rejected_at_buffer_time() -> None:
    # The instance-graduated verbs build their row from the compiled entity's
    # OWN declared members, so an undeclared member can no longer be smuggled
    # in through `tx.insert`; the member-name honesty gate still protects the
    # lower-level neutral document route directly (`Transaction._buffer`). An
    # otherwise-COMPLETE row isolates this defect from `validate_write` (which
    # runs first, and only ever walks Account's OWN
    # declared members — it never itself notices a stray extra key).
    port = ScriptedPort(Transact())
    with pytest.raises(WriteInstructionError, match="shoe_size"):
        account_db(port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert",
                mm.Account.identity,
                {
                    "id": 1,
                    "owner": "Newton",
                    "balance": Decimal("5.00"),
                    "version": 1,
                    "shoe_size": 9,
                },
            )
        )
    assert WriteCall(INSERT_SQL, (1, 9)) not in port.calls


# --------------------------------------------------------------------------- #
# validate_write (m-value-object write validation                             #
# x m-inheritance concrete-subtype write protocol): the SAME model-aware      #
# validator the prepared-write producers call for the corpus's `when.write`  #
# cases (m-value-object-039..044 / m-inheritance-086..089) — one producer,    #
# several ingresses, pinned per rule at this seam.                            #
# comment): its inheritance payload-shape rules classify a framework-owned    #
# metadata key or a cross-branch field more specifically than the generic     #
# member-name-honesty gate ever could.                                       #
# --------------------------------------------------------------------------- #
def test_engine_and_transaction_buffer_share_the_prepared_write_producer() -> None:
    from parallax.conformance import engine as engine_module
    from parallax.snapshot.handle import _write_inputs as write_inputs_module

    assert engine_module.instructions.prepare_wire_write is instructions.prepare_wire_write  # pyright: ignore[reportPrivateImportUsage]
    assert (
        write_inputs_module.instructions.prepare_typed_write  # pyright: ignore[reportPrivateImportUsage]
        is instructions.prepare_typed_write
    )


def test_buffer_rejects_a_required_attribute_missing_at_any_depth() -> None:
    # m-value-object-039's own payload: `address.street` (depth 1) absent.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert",
                Contact.identity,
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
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(SHIPMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert", Shipment.identity, {"id": 5, "name": "Express"}
            )
        )
    assert exc_info.value.rule == "write-required-value-object-missing"


def test_buffer_rejects_a_value_type_mismatch() -> None:
    # m-value-object-043's own payload: `address.street` bound the number 42.
    # This corpus case's own idiomatic-surface spelling is unreachable through
    # `tx.insert` (Pydantic's own field coercion raises first, constructing
    # `ContactAddress(street=42, ...)` never even completes) — a SANCTIONED
    # exception, so
    # this proof exercises the shared validator directly through the private
    # `_buffer` seam instead, exactly like its two siblings above.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert",
                Contact.identity,
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
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert", CardPayment.identity, {"amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "subtype-write-set-based-unsupported"


def test_buffer_rejects_framework_owned_metadata() -> None:
    # m-inheritance-087's own payload: an authored `tagValue`.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert", CardPayment.identity, {"id": 10, "amount": 200.00, "tagValue": "card"}
            )
        )
    assert exc_info.value.rule == "subtype-write-metadata-field"


def test_buffer_rejects_a_sibling_branch_attribute() -> None:
    # m-inheritance-086's own payload: both CardPayment's and CashPayment's
    # own columns, so no single concrete subtype accepts every field.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert",
                Payment.identity,
                {"id": 10, "amount": 200.00, "cardNetwork": "Visa", "tendered": 25.00},
            )
        )
    assert exc_info.value.rule == "subtype-write-sibling-attribute"


def test_buffer_rejects_an_abstract_write_target() -> None:
    # m-inheritance-088's own payload: a well-formed CardPayment-shaped write
    # aimed at the abstract root `Payment`.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as exc_info:
        db_for(PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
                "insert", Payment.identity, {"id": 10, "amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "abstract-write-target"


def test_sparse_update_does_not_trip_required_attribute_missing_for_an_untouched_field() -> None:
    # The no-drift guard for CURRENTLY-LEGAL writes: a sparse keyed update (an id +
    # balance row omitting the required `owner`) must NOT be rejected — an absent
    # top-level member is untouched, never a violation, on any mutation but
    # `insert`. The row is authored straight at the buffer seam, which is what
    # puts it in front of `validate_write` without an edited copy deriving it.
    # The version advances from the observation the write carries, never a
    # row-carried value (`m-opt-lock`). The `locking` preference keeps the
    # statement ungated, so what the assertion measures is the sparse row.
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx._buffer(  # pyright: ignore[reportPrivateUsage] - unit test drives the transaction's private buffer seam
            "update",
            mm.Account.identity,
            {"id": 1, "balance": Decimal("175.00")},
            claim=RetainedObservation(
                VersionedStateKey(ObjectKey(mm.Account.identity, (("id", 1),)), 1),
                VersionObservation(observed_version=1),
                None,
            ),
        )

    account_db(port).transact(fn, concurrency="locking")
    expected = WriteCall(
        POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
        (175.00, 2, 1),
    )
    assert expected in port.calls


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
# Typed KEYED temporal-window verbs: `update`'s                               #
# own optional bitemporal `valid_from`, `terminate`, `update_until`, and    #
# `terminate_until` — the KEYED siblings of `update_where` / `terminate_where` #
# / `update_until_where` / `terminate_until_where`, sharing the SAME           #
# `_buffer` seam and the SAME `validate_window` gate, so a keyed and a      #
# predicate-selected write over the identical bitemporal correction lower to  #
# the identical rectangle split (`m-bitemp-write-001/002/006/007`'s own       #
# witnessed shape, replayed here through the KEYED verb instead of `_where`). #
# --------------------------------------------------------------------------- #
def test_keyed_update_lowers_a_plain_bitemporal_correction() -> None:
    # m-bitemp-write-006 "plain-update-split", replayed through the KEYED verb:
    # close + head (old) + new tail.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=3)))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update(fetched.edit(value=Decimal("200.00")), valid_from=valid_from)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(writes) == 3  # close + head (old) + new tail


def test_keyed_terminate_lowers_a_plain_bitemporal_termination() -> None:
    # m-bitemp-write-007 "plain-terminate", replayed through the KEYED verb:
    # close + head only (no tail).
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=2)))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.terminate(fetched, valid_from=valid_from)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(writes) == 2  # close + head only


def test_keyed_update_until_lowers_the_rectangle_split() -> None:
    # m-bitemp-write-001 "update-until-rectangle-split", replayed through the
    # KEYED verb: close + head + middle + tail.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=4)))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update_until(
            fetched.edit(value=Decimal("200.00")),
            valid_from=valid_from,
            until=until,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(writes) == 4  # close + head + middle + tail


def test_keyed_update_until_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # The SAME sparse-update no-op rule `update` applies (spec §3/§5): a
    # An `edit()` whose Change Record nets to zero issues no DML at all --
    # but only AFTER its (here, valid) Valid-Time window is validated
    # (window validation runs BEFORE the
    # no-op return, for every window verb, never the reverse -- see the
    # sibling equal-bounds pin immediately below for the corrected
    # precedence made visible).
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        # net-zero touch
        tx.update_until(fetched.edit(value=Decimal("100.00")), valid_from=valid_from, until=until)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_keyed_update_until_with_an_empty_change_set_still_rejects_equal_bounds() -> None:
    # Window validation runs BEFORE
    # the empty-effective-change-set no-op return -- equal bounds reject even
    # when the edited copy's own Change Record nets to zero, per spec §5
    # ("all validated at build"): validating the window only after the no-op
    # return would let an equal/reversed window slip through when the change
    # set is empty.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update_until(  # EQUAL bounds, net-zero touch
            fetched.edit(value=Decimal("100.00")), valid_from=valid_from, until=valid_from
        )

    with pytest.raises(ValueError, match="requires valid_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(isinstance(op, WriteCall) for op in port.calls)  # never reached the no-op check


def test_keyed_update_until_with_a_naive_until_raises_the_proper_value_error() -> None:
    # A naive `until` (no tzinfo) must raise the SAME `ValueError` shape
    # the shared window gate's own `instant_literal` normalization raises
    # for a naive `valid_from` (never a bare `TypeError` leaked by
    # comparing a naive `until` against an already-aware `valid_from`
    # when comparison runs before normalization).
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    naive_until = dt.datetime(2024, 9, 1)  # NAIVE -- no tzinfo

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update_until(
            fetched.edit(value=Decimal("200.00")),
            valid_from=valid_from,
            until=naive_until,
        )

    # `pytest.raises(ValueError, ...)` itself is the pin against a
    # `TypeError` leak: `TypeError` is not a `ValueError`, so an un-normalized comparison
    # would escape uncaught here rather than silently satisfy this block.
    with pytest.raises(ValueError, match="naive datetime"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_a_bound_of_no_datetime_type_carries_the_same_refusal_a_naive_one_does() -> None:
    # A value of no datetime type at all is no `m-core` instant either, and the
    # shared window gate the Typed and Wire verbs run answers it with `m-core`'s own
    # class rather than leaking an `AttributeError` out of instant normalization.
    # Either bound reaches that judgement, so both are stated here as strings.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        with pytest.raises(InstantError, match="no `timestamp`"):
            tx.update_until(
                fetched.edit(value=Decimal("200.00")),
                valid_from=cast("dt.datetime", "2024-06-01"),
                until=cast("dt.datetime", "2024-09-01"),
            )
        with pytest.raises(InstantError, match="no `timestamp`"):
            tx.update_until(
                fetched.edit(value=Decimal("200.00")),
                valid_from=valid_from,
                until=cast("dt.datetime", "2024-09-01"),
            )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_a_keyed_bounded_verb_states_its_window_as_a_pair() -> None:
    # A `*_until` verb's window is a PAIR, and half of one states no window at all
    # — the verb's own `WriteInstructionError`, exactly as its Wire peer answers
    # the identical call. The pair is asked of the MUTATION and before either bound
    # is typed, so the missing half is named rather than reported as a value that
    # is no instant: a non-temporal target admits no `valid_from` to supply, and a
    # bitemporal one whose `until` is absent hears about `until` rather than about
    # the malformed `valid_from` beside it.
    account = ScriptedPort(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}])
        )
    )
    position = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def absent_valid_from(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        with pytest.raises(WriteInstructionError, match="valid_from is absent"):
            tx.update_until(
                fetched.edit(balance=Decimal("20.00")),
                valid_from=cast("dt.datetime", None),
                until=until,
            )

    def absent_until(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        with pytest.raises(WriteInstructionError, match="until is absent"):
            tx.terminate_until(fetched, valid_from=FIXED, until=cast("dt.datetime", None))
        with pytest.raises(WriteInstructionError, match="until is absent"):
            tx.update_until(
                fetched.edit(value=Decimal("200.00")),
                valid_from=cast("dt.datetime", "2024-06-01"),
                until=cast("dt.datetime", None),
            )

    account_db(account).transact(absent_valid_from)
    Database.connect(position, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        absent_until, concurrency="optimistic"
    )
    assert not any(isinstance(op, WriteCall) for op in account.calls)
    assert not any(isinstance(op, WriteCall) for op in position.calls)


def test_keyed_terminate_until_lowers_head_and_tail_only() -> None:
    # m-bitemp-write-002 "terminate-until", replayed through the KEYED verb:
    # close + head + tail (no middle).
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=3)))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.terminate_until(fetched, valid_from=valid_from, until=until)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(writes) == 3  # close + head + tail


def test_keyed_update_on_a_bitemporal_target_without_valid_from_raises() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update(fetched.edit(value=Decimal("200.00")))

    with pytest.raises(ValueError, match="requires valid_from"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_on_a_non_temporal_target_forbids_valid_from() -> None:
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}])
        )
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.terminate(fetched, valid_from=FIXED)

    with pytest.raises(ValueError, match="takes no valid_from"):
        account_db(port).transact(fn)


# --------------------------------------------------------------------------- #
# Window-order validation:                                                    #
# `python.md` §5 "the `*_until` trio additionally requires `until`, with      #
# `valid_from < until` ... all validated at build" — an EQUAL and a        #
# REVERSED window both reject, at the verb call, before any buffering, for    #
# BOTH the KEYED (`update_until`/`terminate_until`) and `_where`              #
# (`update_until_where`/`terminate_until_where`) verb families — the ONE      #
# shared `validate_window` gate (`parallax.snapshot.handle._write_inputs`)    #
# makes all four converge.                                                    #
# --------------------------------------------------------------------------- #
def test_keyed_update_until_rejects_an_equal_window_bound() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.update_until(
            fetched.edit(value=Decimal("200.00")),
            valid_from=valid_from,
            until=valid_from,
        )

    with pytest.raises(ValueError, match="requires valid_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_until_rejects_a_reversed_window_bound() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))
    valid_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)  # BEFORE valid_from — reversed

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.terminate_until(fetched, valid_from=valid_from, until=until)

    with pytest.raises(ValueError, match="requires valid_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )


# --------------------------------------------------------------------------- #
# The §5 prior-observation license for keyed TEMPORAL update/terminate:       #
# the temporal sibling of the versioned                                       #
# `require_observed` rule, enforced at the developer verb.                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
def test_a_temporal_close_of_a_value_no_read_produced_raises_before_any_dml(
    concurrency: str,
) -> None:
    # A keyed temporal close of a milestone nothing observed is a
    # read-before-write programming error under EITHER strategy: under Locking
    # the observing find's shared lock is the ungated close's ONLY protection,
    # and under Optimistic there is no observed `in_z` to gate on. A plainly
    # constructed instance carries no Source Hint, so it proves neither.
    port = ScriptedPort(Transact())
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.terminate(mm.Balance(id=1, acct_num="A-1", value=Decimal("5.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(fn, concurrency=cast("Any", concurrency))
    assert refusal.value.code == "write-evidence-unavailable"
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_a_standalone_temporal_source_is_accepted_without_an_in_transaction_reread() -> None:
    # The ownership inversion, at the temporal verb: the evidence belongs to the
    # VALUE, so a node a plain `db.find` materialized carries the milestone it
    # observed into a later transaction. Under the default preference `Balance`
    # resolves to Optimistic, where the database gate is the authority, so the
    # close binds that retained `in_z` and no reread is issued.
    port = ScriptedPort(
        Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]),
        Transact(Write(times=2)),
    )
    db = db_for(BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    def fn(tx: Transaction) -> None:
        tx.update(node.edit(value=Decimal("9.00")))

    db.transact(fn)
    # One read (the standalone find), then the close and its chained successor —
    # no second read of any kind.
    assert [type(op) for op in port.calls] == [
        ReadCall,
        BeginCall,
        WriteCall,
        WriteCall,
        CommitCall,
    ]
    close, _chained = (call for call in port.calls if isinstance(call, WriteCall))
    assert "in_z = " in close.sql


def test_a_standalone_temporal_source_is_refused_under_an_explicit_locking_preference() -> None:
    # The Locking strategy's license is the shared row lock a read of THIS
    # transaction holds, and a standalone source proves no such lock however
    # authentic its evidence is. The refusal is at the verb, before any DML.
    port = ScriptedPort(
        Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]), Transact()
    )
    db = db_for(BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    def fn(tx: Transaction) -> None:
        tx.update(node.edit(value=Decimal("9.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(fn, concurrency="locking")
    assert refusal.value.code == "write-evidence-unavailable"
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_same_transaction_insert_then_temporal_update_is_licensed() -> None:
    # Read-your-own-writes exemption: this transaction's OWN buffered insert
    # IS the provenance a subsequent keyed write builds on (`m-txtime-write-008`'s
    # same-transaction coalescing shape) — the value is exempt from the
    # provenance refusal, no observation lookup applies, and the planner folds
    # the pair into the single INSERT carrying the updated value.
    port = ScriptedPort(Transact(Write()))
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fresh = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(fresh)
        tx.update(fresh.edit(value=Decimal("2.00")))

    db.transact(fn)
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 1  # coalesced to one INSERT
    assert Decimal("2.00") in write_ops[0].binds


def test_an_update_of_a_value_a_different_object_was_inserted_under_is_refused() -> None:
    # The exemption is keyed by the OBJECT this transaction inserted, not by the
    # verb having been called: a value naming a different primary key was never
    # inserted here, so it still addresses no stored row.
    def fn(tx: Transaction) -> None:
        tx.insert(mm.Balance(id=9, acct_num="Z", value=Decimal("1.00")))
        tx.update(
            mm.Balance(id=10, acct_num="Z", value=Decimal("1.00")).edit(value=Decimal("2.00"))
        )

    with pytest.raises(KeyedWriteValueError) as refusal:
        Database.connect(ScriptedPort(Transact()), BALANCE, clock=FixedClock(FIXED)).transact(fn)
    assert refusal.value.code == "write-value-not-stored"


def test_same_transaction_insert_then_terminate_is_licensed() -> None:
    # Read-your-own-writes exemption: this transaction's OWN buffered insert
    # IS the observation provenance a keyed temporal close needs — no
    # observation lookup applies, and `terminate` derives an identity row alone,
    # so it takes no position on where the value came from.
    port = ScriptedPort(Transact())
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fresh = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(fresh)
        tx.terminate(fresh)

    db.transact(fn)
    # Licensed rather than refused for want of an observation: the flush then
    # cancels the pair, which is the coalescing rule rather than a refusal.
    assert not any(isinstance(op, WriteCall) for op in port.calls)


# The Transaction-Time instant the audit read pins: inside the current
# milestone's own interval, so both reads observe THAT milestone.
_AUDIT_INSTANT = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
def test_a_temporal_update_after_an_audit_read_of_the_same_milestone_commits(
    concurrency: str,
) -> None:
    # The row is read normally, then read again at a past Transaction-Time
    # instant that falls inside the very milestone the first read returned — the
    # ordinary "show me what this looked like then" display or audit step — and
    # the value the FIRST read handed back is then updated. Both reads observed
    # one milestone, so the write commits: the close reaches DML and chains its
    # successor, in either mode. The distinction is that two pins resolving to
    # one milestone are one piece of evidence, not two competing ones — the
    # locking-mode close is licensed by the shared read lock the latest read took
    # on the row it closes, and a second read of that same row cannot revoke it.
    port = ScriptedPort(
        Transact(
            Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))], times=2),
            Write(times=2),
        )
    )
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        current = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.find(mm.Balance.where(mm.Balance.id == 1).as_of(tx_time=_AUDIT_INSTANT)).result()
        tx.update(current.edit(value=Decimal("150.00")))

    db.transact(fn, concurrency=cast("Any", concurrency))
    close, chained = [op for op in port.calls if isinstance(op, WriteCall)]
    assert close.binds[:3] == (FIXED, 1, "infinity")
    assert Decimal("150.00") in chained.binds
    assert port.calls[-1] == CommitCall()


# --------------------------------------------------------------------------- #
# A same-transaction reread of a row a keyed write just settled against: the   #
# classification a hydratable root carries is judged fresh from each read's    #
# own bytes, never served from write-path state — the retained evidence a     #
# keyed write settles against, or the read-your-own-writes flush the reread    #
# itself forces.                                                               #
# --------------------------------------------------------------------------- #
def test_a_reread_after_settling_a_write_against_a_classified_row_still_classifies_it() -> None:
    # Customer 6 stores `address.geo` as the scalar "unknown" where a `one`
    # occurrence is declared — `m-unit-work-028`'s own wrong-kind row. The first
    # read publishes it as a hydratable `InvalidData`, and a keyed update settles
    # against the hydrated root and changes only `name`. The script answers the
    # SAME `geo` bytes to both reads, so a correct reread — forced by the
    # buffered write's read-your-own-writes flush — answers the identical
    # diagnosis rather than one the write repaired, suppressed, or worsened.
    address = {"street": "6 Kastanien Allee", "city": "Berlin", "geo": "unknown"}
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 6, "name": "Rin", "address": PresentDocument(dict(address))}]),
            Write(),
            Read(
                rows=[
                    {
                        "id": 6,
                        "name": "Rin Nakamura",
                        "address": PresentDocument(dict(address)),
                    }
                ]
            ),
        )
    )
    db = db_for(CUSTOMER_MODEL, port)

    def fn(tx: Transaction) -> InvalidData[Customer]:
        first = tx.find(Customer.where(Customer.id == 6)).checked().result()
        assert isinstance(first, InvalidData)
        current = cast("Customer", first.data)
        assert current is not None
        tx.update(current.edit(name="Rin Nakamura"))
        reread = tx.find(Customer.where(Customer.id == 6)).checked().result()
        assert isinstance(reread, InvalidData)
        return reread

    reread = db.transact(fn)
    assert {issue.code for issue in reread.issues} == {"stored-data-one-wrong-kind"}
    assert reread.data is not None
    assert reread.data.name == "Rin Nakamura"
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, ReadCall, CommitCall]
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert write_ops == [
        WriteCall(
            POSTGRES.to_driver_sql("update customer set name = ? where id = ?"), ("Rin Nakamura", 6)
        )
    ]


# --------------------------------------------------------------------------- #
# The finite-Transaction-Time-pin refusal (`m-temporal-read`'s finite-pin      #
# mutation row; `_write_inputs.validate_source_pin`): a view pinned at a       #
# FINITE Transaction-Time instant is read-only — every keyed verb refuses it   #
# at the call, before any buffering, with the neutral                          #
# `transaction-time-pin-read-only` error. A LATEST Transaction-Time pin and a  #
# finite Valid-Time pin stay writable (the Valid-Time case is the retroactive  #
# correction), and an EDITED COPY of a pinned node carries that node's pin, so #
# it is refused exactly as the node itself is.                                 #
# --------------------------------------------------------------------------- #
_TX_PIN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_PIN = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_CORRECTION_FROM = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
_CORRECTION_UNTIL = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)


def _find_pinned_position(tx: Transaction, **as_of: Any) -> Any:
    as_of.setdefault("valid_time", LATEST)
    return tx.find(WherePosition.where(WherePosition.id == 1).as_of(**as_of)).result()


# Every keyed mutation verb, driven with a pinned source node — the dict type
# gives each lambda its contextual parameter typing.
_PINNED_SOURCE_VERBS: dict[str, Callable[[Transaction, Any], None]] = {
    "insert": lambda tx, node: tx.insert(node, valid_from=_CORRECTION_FROM),
    "insert_until": lambda tx, node: tx.insert_until(
        node, valid_from=_CORRECTION_FROM, until=_CORRECTION_UNTIL
    ),
    "update": lambda tx, node: tx.update(node, valid_from=_CORRECTION_FROM),
    "delete": lambda tx, node: tx.delete(node),
    "terminate": lambda tx, node: tx.terminate(node, valid_from=_CORRECTION_FROM),
    "update_until": lambda tx, node: tx.update_until(
        node, valid_from=_CORRECTION_FROM, until=_CORRECTION_UNTIL
    ),
    "terminate_until": lambda tx, node: tx.terminate_until(
        node, valid_from=_CORRECTION_FROM, until=_CORRECTION_UNTIL
    ),
}


@pytest.mark.parametrize("verb_name", sorted(_PINNED_SOURCE_VERBS))
def test_every_keyed_verb_refuses_a_finite_transaction_time_pinned_source(
    verb_name: str,
) -> None:
    verb = _PINNED_SOURCE_VERBS[verb_name]
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))

    def fn(tx: Transaction) -> None:
        node = _find_pinned_position(tx, tx_time=_TX_PIN)
        verb(tx, node)

    with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(isinstance(op, WriteCall) for op in port.calls)  # refused before any buffering


def test_a_latest_transaction_time_pinned_source_stays_writable() -> None:
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        node = _find_pinned_position(tx, tx_time=LATEST)
        tx.terminate(node, valid_from=_CORRECTION_FROM)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert len([op for op in port.calls if isinstance(op, WriteCall)]) == 2  # close + head


def test_a_finite_valid_time_pinned_source_stays_writable() -> None:
    # The writable half of the finite-pin contrast (m-bitemp-write-015): a
    # finite Valid-Time pin is the retroactive correction, never read-only.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()]), Write(times=2)))

    def fn(tx: Transaction) -> None:
        node = _find_pinned_position(tx, valid_time=_VALID_PIN)
        tx.terminate(node, valid_from=_CORRECTION_FROM)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert len([op for op in port.calls if isinstance(op, WriteCall)]) == 2  # close + head


def test_an_edited_copy_of_a_finite_transaction_time_pinned_node_is_refused_too() -> None:
    # An edit preserves everything outside the declared members, the lifecycle
    # state carrying the pin among it, so the copy describes the same read-only
    # view its source does. Deriving a copy is not how a historical milestone
    # becomes writable — nothing is: the Transaction-Time past is never
    # rewritten. Optimistic mode is the mode with no plan-time licensing check
    # of its own, so this is the verb-time refusal answering on its own.
    port = ScriptedPort(Transact(Read(rows=[_position_row_dt()])))

    def fn(tx: Transaction) -> None:
        node = _find_pinned_position(tx, tx_time=_TX_PIN)
        tx.update(node.edit(value=Decimal("200.00")), valid_from=_CORRECTION_FROM)

    with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(isinstance(op, WriteCall) for op in port.calls)  # refused before any buffering


# --------------------------------------------------------------------------- #
# The KEYED verbs' own entity-class guard (`_write_inputs.                     #
# metadata_of_instance`). It needs no fixture but a boundary that runs no      #
# statement, so it lives here with the rest of the keyed-verb region.          #
# --------------------------------------------------------------------------- #
def test_a_keyed_verb_refuses_an_instance_of_an_undeclared_class() -> None:
    # A class this model composed no Entity for is refused as a TypeError rather
    # than failing later on a missing declaration; the raising port proves the
    # guard runs before any I/O.
    class _Elsewhere(Entity, table="elsewhere", namespace="parallax.compatibility"):
        id: Attr[int] = attr(primary_key=True)

    def fn(tx: Transaction) -> None:
        tx.delete(_Elsewhere(id=1))

    with pytest.raises(TypeError, match="_Elsewhere is not an Entity Class of this model"):
        Database.connect(ScriptedPort(Transact()), PERSON, clock=FixedClock(FIXED)).transact(fn)


# Two DISTINCT classes may legitimately declare the same Entity Identity in two
# separate models. Membership is decided by the identity the instance's class
# declares, so a `_TwinLeft` instance handed to a database connected to
# `_TwinRight`'s model resolves — and the guarantee the old object-identity guard
# provided survives in the Entity Row Codec, which refuses the foreign class's
# own member by name before an instruction exists at all.
class _TwinLeft(Entity, table="twin", name="Twin", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    left_only: Attr[str] = attr(max_length=8)


class _TwinRight(Entity, table="twin", name="Twin", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    right_only: Attr[str] = attr(max_length=8)


_TWIN_LEFT = DomainModel(_TwinLeft)
_TWIN_RIGHT = DomainModel(_TwinRight)


def test_a_foreign_twins_members_are_refused_when_the_row_is_derived() -> None:
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        tx.insert(_TwinLeft(id=1, left_only="x"))

    # `full_row` selects what the instance populated and the connected model
    # declares no `leftOnly`, so the substitution is named where it happened —
    # rather than reported downstream as the ABSENCE of the `rightOnly` this
    # model does declare.
    with pytest.raises(EntityRowError) as refusal:
        db_for(_TWIN_RIGHT, port).transact(fn)
    assert refusal.value.code == "entity-row-member-missing"
    assert "'leftOnly'" in refusal.value.message
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_the_keyed_entity_class_guard_still_accepts_its_own_models_instance() -> None:
    port = ScriptedPort(Transact(Read(rows=[{"id": 1, "left_only": "x"}]), Write()))

    def fn(tx: Transaction) -> None:
        tx.delete(tx.find(_TwinLeft.where(_TwinLeft.id == 1)).result())

    db_for(_TWIN_LEFT, port).transact(fn)
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, CommitCall]


# --------------------------------------------------------------------------- #
# The keyed-write value contract (`m-unit-work` "Write value provenance";      #
# `_write_inputs.validate_write_value`): which verbs accept a value is decided #
# by which framework-managed source produced it, and never by whether an       #
# author has since changed it. The four outcomes below are the whole rule —    #
# three refusals partitioning the values a verb can be handed, and the         #
# unchanged stored value that is no refusal at all.                            #
# --------------------------------------------------------------------------- #
def _foreign_lifecycle_account() -> mm.Account:
    """An `Account` carrying lifecycle state this Snapshot did not attach.

    Built rather than read, because the seam under test asks one question and the
    value's members are not part of it: is there managed state, and is it this
    lifecycle's? What a value with a foreign answer is refused for is pinned here;
    that a value ANOTHER framework-managed source actually produced is refused is
    pinned by the corpus (`m-unit-work-019`, arranged through
    `parallax.conformance.another_source`).
    """

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(mm.Account.identity)
        # `Account`'s member row: id, owner, balance, version — and no
        # relationship of its own to carry a position for.
        writer.populate(handle, (1, "Ada", Decimal("100.00"), 1), ())
        return (handle,)

    (node,) = graph_construction_of(ACCOUNT).construct(
        build, state_factory=lambda view, handle: _OtherLifecycleState()
    )
    return cast("mm.Account", node)


class _OtherLifecycleState:
    """The whole of another source's per-node state, as far as this rule is
    concerned: something this Snapshot did not attach."""


def test_update_of_a_value_no_read_produced_names_the_insert_verb() -> None:
    def fn(tx: Transaction) -> None:
        tx.update(new_account().edit(balance=Decimal("9.00")))

    with pytest.raises(KeyedWriteValueError) as refusal:
        Database.connect(ScriptedPort(Transact()), ACCOUNT, clock=FixedClock(FIXED)).transact(fn)
    assert refusal.value.code == "write-value-not-stored"
    assert refusal.value.identity == mm.Account.identity
    assert "tx.insert(...)" in refusal.value.message


def test_insert_of_a_value_this_store_produced_names_the_update_verb() -> None:
    # The refusal names the mistake itself — the row this value denotes is
    # already stored — rather than reporting a required attribute absent on a
    # plainly populated row, which is what deriving the insert's own row first
    # would report.
    port = ScriptedPort(
        Transact(Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]))
    )

    def fn(tx: Transaction) -> None:
        tx.insert(tx.find(mm.Account.where(mm.Account.id == 1)).result())

    with pytest.raises(KeyedWriteValueError) as refusal:
        account_db(port).transact(fn)
    assert refusal.value.code == "write-value-already-stored"
    assert "tx.update(...)" in refusal.value.message
    assert not any(isinstance(op, WriteCall) for op in port.calls)  # refused before any DML


@pytest.mark.parametrize("verb", ["insert", "update"], ids=["insert", "update"])
def test_a_value_carrying_another_sources_state_is_refused_by_both_families(verb: str) -> None:
    # A value's stored counterpart is only the one the writing source itself
    # produced, so neither family accepts another source's value — and the
    # raising port proves the refusal precedes every adapter call.
    foreign = _foreign_lifecycle_account()

    def fn(tx: Transaction) -> None:
        if verb == "insert":
            tx.insert(foreign)
        else:
            tx.update(foreign.edit(balance=Decimal("175.00")))

    with pytest.raises(KeyedWriteValueError) as refusal:
        Database.connect(ScriptedPort(Transact()), ACCOUNT, clock=FixedClock(FIXED)).transact(fn)
    assert refusal.value.code == "write-value-foreign-lifecycle"


class _RekeyedTwin(Entity, table="twin", name="Twin", namespace="parallax.compatibility"):
    id_elsewhere: Attr[int] = attr(primary_key=True)
    right_only: Attr[str] = attr(max_length=8)


def test_a_value_that_keys_no_row_is_still_refused_for_its_provenance() -> None:
    # The refusal precedes row derivation for EVERY value, including one whose
    # own class keys this Entity by another member and can therefore derive no
    # identity row at all. The exemption a buffered insert grants is decided from
    # the object each value names rather than from a row, so this transaction
    # having an insert to compare against cannot turn a provenance refusal into
    # an `EntityRowError` reported on the value's behalf.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        tx.insert(_TwinRight(id=1, right_only="x"))
        tx.update(_RekeyedTwin(id_elsewhere=1, right_only="y").edit(right_only="z"))

    with pytest.raises(KeyedWriteValueError) as refusal:
        db_for(_TWIN_RIGHT, port).transact(fn)
    assert refusal.value.code == "write-value-not-stored"
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


# --------------------------------------------------------------------------- #
# What a framework-managed SOURCE is (ADR 0010): the managed lifecycle, so     #
# every `Database` over one store is one source. The two arrangements below    #
# are one situation — a second handle's read and this handle's own             #
# non-transactional read both hand a write a value the writing unit of work    #
# never observed — so they MUST reach the identical outcome. The same-handle   #
# arrangement is what breaks first if handle identity is ever threaded onto a  #
# materialized node.                                                           #
# --------------------------------------------------------------------------- #
def _person_read_outside_the_writing_transaction(
    port: ScriptedPort, *, second_handle: bool
) -> tuple[Database, Person]:
    """A `Person` a managed read produced, plus the `Database` that will write it.

    ``second_handle`` reads through a DIFFERENT `Database` over the same port;
    otherwise the writing handle reads it itself, non-transactionally.
    """
    writer = db_for(PERSON, port)
    reader = db_for(PERSON, port) if second_handle else writer
    return writer, reader.find(Person.where(Person.id == 1)).result()


@pytest.mark.parametrize("second_handle", [True, False], ids=["second-handle", "same-handle"])
def test_a_read_outside_the_writing_transaction_is_still_this_source(second_handle: bool) -> None:
    port = ScriptedPort(Read(rows=[{"id": 1, "name": "Ada"}]), Transact())
    writer, node = _person_read_outside_the_writing_transaction(port, second_handle=second_handle)

    with pytest.raises(KeyedWriteValueError) as refusal:
        writer.transact(lambda tx: tx.insert(node))
    assert refusal.value.code == "write-value-already-stored"


@pytest.mark.parametrize("second_handle", [True, False], ids=["second-handle", "same-handle"])
def test_an_unversioned_update_of_such_a_value_is_refused_for_its_evidence(
    second_handle: bool,
) -> None:
    # An unversioned Non-Temporal target resolves to the Locking fallback, whose
    # license is the shared row lock a read of THIS transaction holds. Neither
    # arrangement holds one — a second handle's read and this handle's own
    # non-transactional read alike — so the update is refused at the verb,
    # before anything is buffered and before any statement is emitted.
    port = ScriptedPort(Read(rows=[{"id": 1, "name": "Ada"}]), Transact())
    writer, node = _person_read_outside_the_writing_transaction(port, second_handle=second_handle)

    with pytest.raises(WriteEvidenceError) as refusal:
        writer.transact(lambda tx: tx.update(node.edit(name="Grace")))
    assert refusal.value.code == "write-evidence-unavailable"
    assert refusal.value.object_key.primary_key == (("id", 1),)
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_an_unversioned_update_of_a_participating_read_is_addressed_by_its_key() -> None:
    # The licensing read moved inside the writing transaction: the participating
    # find takes the Locking fallback's shared row lock, and the update it
    # licenses is planned and emitted, addressed by its key alone and gated by
    # nothing.
    port = ScriptedPort(Transact(Read(rows=[{"id": 1, "name": "Ada"}]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.find(Person.where(Person.id == 1)).result()
        tx.update(node.edit(name="Grace"))

    db_for(PERSON, port).transact(fn)
    assert port.calls[-2:] == [
        WriteCall(POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Grace", 1)),
        CommitCall(),
    ]


def test_update_of_an_unedited_node_buffers_nothing() -> None:
    # The rule the change tracking exists for: writing every value a find
    # returned and editing only some of them is correct code. The unedited one
    # is neither a refusal nor a write.
    port = ScriptedPort(
        Transact(Read(rows=[{"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}]))
    )

    def fn(tx: Transaction) -> None:
        tx.update(tx.find(mm.Account.where(mm.Account.id == 1)).result())

    account_db(port).transact(fn)
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_UNLOCKED, (1,)), CommitCall()]


def test_a_terminate_takes_no_position_on_a_values_provenance() -> None:
    # `delete` / `terminate` / `terminateUntil` derive an identity row alone, so
    # the PROVENANCE refusal does not apply to them — what refuses this one is
    # the evidence rule, which finds no observed state behind the value.
    port = ScriptedPort(Transact())

    def fn(tx: Transaction) -> None:
        tx.terminate(mm.Balance(id=9, acct_num="Z", value=Decimal("1.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        db_for(BALANCE, port).transact(fn)
    assert refusal.value.code == "write-evidence-unavailable"


def test_the_keyed_write_value_code_set_is_closed_against_an_unlisted_code() -> None:
    assert {
        "write-value-not-stored",
        "write-value-already-stored",
        "write-value-foreign-lifecycle",
    } == KEYED_WRITE_VALUE_CODES
    with pytest.raises(ValueError, match="not a keyed write value code"):
        KeyedWriteValueError(
            code="write-value-nosuch", message="invented", identity=mm.Account.identity
        )
