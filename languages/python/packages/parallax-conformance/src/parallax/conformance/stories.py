from __future__ import annotations

import contextlib
import datetime as dt
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from parallax.conformance.read_models import Balance
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.story_models import Account, Order, OrderItem, Position, Wallet
from parallax.conformance.vo_models import (
    Address,
    Branch,
    Customer,
    CustomerAddress,
    CustomerGeo,
    CustomerPhone,
    Geo,
    Phone,
    Supplier,
)
from parallax.core.entity import Entity
from parallax.core.object_query import LATEST
from parallax.core.unit_work import Clock
from parallax.snapshot.handle import ExecutionFailure, ScopedDatabase, Transaction

__all__ = ["WRITE_STORIES", "WriteStory", "story_snippet"]

StoryKind = Literal["commit", "abort", "boundary"]


@dataclass(frozen=True, slots=True)
class WriteStory:
    """One executable public-API story mirroring a corpus write case.

    ``run`` returns the TYPED INSTANCES a story's own final observing find
    materialized (`Snapshot[T].results()`, instance-native grading) —
    never a rendered row: the real-Postgres runner (`test_story_run.py`)
    renders them to the physical-column-keyed row form (`instance_row`) at
    the grading seam, the SAME convention the read/graph stories already use.

    ``clock`` is an optional zero-argument
    :class:`~parallax.core.unit_work.Clock` factory: a
    temporal writeSequence story needing successive distinct Transaction-Time
    instants across its own choreography (one corpus writeSequence entry, one
    flushing ``db.transact`` call, one Clock read each) sets it to something
    like ``lambda: ScriptedClock([...])``
    (:class:`~parallax.conformance.scripted_clock.ScriptedClock`) — a FACTORY,
    not a shared instance, so each harness consumer (the fake-port no-drift
    guard, the real-Postgres story runner) drives its own fresh clock rather
    than exhausting a script the other consumer already advanced. ``None``
    connects with no explicit clock at all —
    the system clock (`Database.connect`'s own default).

    ``model`` names the corpus model the story mirrors, which is also how a
    consumer reaches the Domain Model of Entity Classes to connect with
    (:data:`~parallax.conformance.class_models.MODELS`) — a story's own
    observing find materializes typed instances, so it needs the class-backed
    model rather than the ingested corpus descriptor."""

    case_id: str
    title: str
    kind: StoryKind
    model: str
    run: Callable[[ScopedDatabase], list[Entity] | None]
    clock: Callable[[], Clock] | None = None


def story_snippet(story: WriteStory) -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return inspect.getsource(story.run).rstrip("\n")


def insert_then_read_your_own_write(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        tx.insert(Account(id=7, owner="Newton", balance=Decimal("5.00")))
        return list(tx.find(Account.where(Account.id == 7)).results())

    return db.transact(fn)


def aborted_update_is_discarded(db: ScopedDatabase) -> list[Entity]:
    fetched = db.transact(lambda tx: tx.find(Account.where(Account.id == 1))).result()
    edited = fetched.edit(balance=Decimal("999.00"))

    def doomed(tx: Transaction) -> None:
        tx.update(edited)
        raise RuntimeError("changed my mind")

    with contextlib.suppress(ExecutionFailure):
        db.transact(doomed)
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 1))).results())


def fk_ordered_inserts(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert(
            Order(
                id=100,
                name="Hopper",
                sku="X-1",
                qty=1,
                price=Decimal("9.99"),
                active=True,
                ordered_on=dt.date(2024, 7, 1),
            )
        )
        tx.insert(OrderItem(id=200, order_id=100, sku="X-1", quantity=3))

    db.transact(fn)


def callback_value_withheld_on_abort(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()
        tx.update(current.edit(balance=Decimal("175.00")))
        tx.find(Account.where(Account.id == 1))
        raise RuntimeError("abort")

    return db.transact(fn)


def keyed_update_observed_in_transaction(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()
        tx.update(current.edit(balance=Decimal("175.00")))
        return list(tx.find(Account.where(Account.id == 1)).results())

    return db.transact(fn)


def keyed_delete_observed_in_transaction(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 3)).result()
        tx.delete(current)
        return list(tx.find(Account.where(Account.id == 3)).results())

    return db.transact(fn)


def create_then_delete_a_parent_child_pair(db: ScopedDatabase) -> None:
    def create(tx: Transaction) -> None:
        tx.insert(
            Order(
                id=100,
                name="Hopper",
                sku="X-1",
                qty=1,
                price=Decimal("9.99"),
                active=True,
                ordered_on=dt.date(2024, 7, 1),
            )
        )
        tx.insert(OrderItem(id=200, order_id=100, sku="X-1", quantity=3))

    def teardown(tx: Transaction) -> None:
        tx.delete_where(OrderItem.where(OrderItem.id == 200))
        tx.delete_where(Order.where(Order.id == 100))

    db.transact(create)
    db.transact(teardown)


def one_flush_combined_mixed_verb_order(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()
        deleted = tx.find(Account.where(Account.id == 3)).result()
        tx.insert(Account(id=9, owner="Noether", balance=Decimal("5.00")))
        tx.update(current.edit(balance=Decimal("20.00")))
        tx.delete(deleted)
        return list(tx.find(Account.where(Account.balance < Decimal("50.00"))).results())

    return db.transact(fn)


def aborted_insert_never_becomes_durable(db: ScopedDatabase) -> list[Entity]:
    def doomed(tx: Transaction) -> None:
        tx.insert(Account(id=7, owner="Newton", balance=Decimal("5.00")))
        raise RuntimeError("abort")

    with contextlib.suppress(ExecutionFailure):
        db.transact(doomed)
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 7))).results())


def aborted_delete_leaves_the_row_standing(db: ScopedDatabase) -> list[Entity]:
    def doomed(tx: Transaction) -> None:
        current = tx.find(Account.where(Account.id == 3)).result()
        tx.delete(current)
        tx.find(Account.where(Account.id == 3))
        raise RuntimeError("abort")

    with contextlib.suppress(ExecutionFailure):
        db.transact(doomed)
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 3))).results())


def transaction_time_only_insert_opens_a_current_milestone(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    db.transact(fn)


def transaction_time_only_terminate_closes_the_current_milestone(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def close(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.terminate(current)

    db.transact(insert)
    db.transact(close)


def transaction_time_only_chain_update_via_a_sparse_copy(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.update(current.edit(value=Decimal("150.00")))

    db.transact(insert)
    db.transact(update)


def transaction_time_only_chain_update_carries_every_new_attribute(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.update(current.edit(acct_num="B", value=Decimal("250.00")))

    db.transact(insert)
    db.transact(update)


def transaction_time_only_chain_update_from_existing_history(db: ScopedDatabase) -> None:
    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.update(current.edit(value=Decimal("175.00")))

    db.transact(update)


def versioned_update_advances_the_version_ungated_in_locking_mode(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        current = tx.find(Account.where(Account.id == 2)).result()
        tx.update(current.edit(balance=Decimal("500.00")))

    db.transact(fn, concurrency="locking")


def wallet_predicate_delete_is_readless(db: ScopedDatabase) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        tx.delete_where(Wallet.where(Wallet.balance < Decimal("200.00")))
        return list(tx.find(Wallet.where(Wallet.balance < Decimal("200.00"))).results())

    return db.transact(fn)


def bitemporal_insert_until_opens_one_bounded_rectangle(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert_until(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)


def bitemporal_plain_update_splits_head_and_new_tail(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def correct(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1).as_of(valid_time=LATEST)).result()
        tx.update(
            current.edit(value=Decimal("200.00")),
            valid_from=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(correct)


def bitemporal_plain_insert_opens_a_fully_current_rectangle(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)


def bitemporal_update_until_splits_head_middle_tail(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def split(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1).as_of(valid_time=LATEST)).result()
        tx.update_until(
            current.edit(value=Decimal("200.00")),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(split)


def a_close_settles_against_the_milestone_its_own_find_observed(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        head = tx.find(
            Position.where(Position.id == 1).as_of(
                valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.find(
            Position.where(Position.id == 1).as_of(
                valid_time=dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.update(
            head.edit(value=Decimal("150.00")),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )

    db.transact(fn, concurrency="optimistic")


def supplier_transaction_time_only_chain_update_carries_the_document(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Supplier(
                id=1,
                name="Nordic Foods",
                address=Address(
                    street="1 Old Street",
                    city="Oslo",
                    geo=Geo(country="NO"),
                    phones=(Phone(type="home", number="555-0100"),),
                ),
            )
        )

    def update(tx: Transaction) -> None:
        current = tx.find(Supplier.where(Supplier.id == 1)).result()
        tx.update(
            current.edit(
                address=Address(
                    street="2 New Avenue",
                    city="Bergen",
                    geo=Geo(country="NO"),
                    phones=(
                        Phone(type="work", number="555-0200"),
                        Phone(type="home", number="555-0201"),
                    ),
                )
            )
        )

    db.transact(insert)
    db.transact(update)


def branch_bitemporal_rectangle_split_carries_the_document(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Branch(
                id=1,
                name="Central Branch",
                address=Address(
                    street="10 Old Road",
                    city="Helsinki",
                    geo=Geo(country="FI"),
                    phones=(Phone(type="main", number="555-1000"),),
                ),
            ),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def split(tx: Transaction) -> None:
        current = tx.find(Branch.where(Branch.id == 1).as_of(valid_time=LATEST)).result()
        tx.update_until(
            current.edit(
                address=Address(
                    street="30 New Road",
                    city="Tampere",
                    geo=Geo(country="FI"),
                    phones=(
                        Phone(type="main", number="555-3000"),
                        Phone(type="fax", number="555-3001"),
                    ),
                )
            ),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(split)


def customer_insert_carries_the_whole_address_document(db: ScopedDatabase) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert(
            Customer(
                id=100,
                name="Solveig",
                address=CustomerAddress(
                    street="12 Aurora Ave",
                    city="Tromso",
                    geo=CustomerGeo(country="NO"),
                    phones=(
                        CustomerPhone(type="home", number="555-0001"),
                        CustomerPhone(type="work", number="555-0002"),
                    ),
                ),
            )
        )

    db.transact(fn)


def customer_update_replaces_the_whole_address_document(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Customer(
                id=200,
                name="Ingrid",
                address=CustomerAddress(
                    street="3 Old Road",
                    city="Bergen",
                    geo=CustomerGeo(country="NO"),
                    phones=(CustomerPhone(type="home", number="555-1111"),),
                ),
            )
        )

    def replace(tx: Transaction) -> None:
        current = tx.find(Customer.where(Customer.id == 200)).result()
        tx.update(
            current.edit(
                address=CustomerAddress(
                    street="9 New Way",
                    city="Stavanger",
                    phones=(CustomerPhone(type="work", number="555-2222"),),
                )
            )
        )

    db.transact(insert)
    db.transact(replace)


def customer_update_nulls_the_address_document_out(db: ScopedDatabase) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Customer(
                id=300,
                name="Bjorn",
                address=CustomerAddress(
                    street="7 Fjord Vei", city="Alesund", geo=CustomerGeo(country="NO")
                ),
            )
        )

    def null_out(tx: Transaction) -> None:
        current = tx.find(Customer.where(Customer.id == 300)).result()
        tx.update(current.edit(address=None))

    db.transact(insert)
    db.transact(null_out)


def _txtime_write_001_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 1, 1, tzinfo=dt.UTC)])


def _txtime_write_002_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)]
    )


def _txtime_write_003_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 8, 1, tzinfo=dt.UTC)]
    )


def _txtime_write_005_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 9, 1, tzinfo=dt.UTC)])


def _bitemp_write_003_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 1, 1, tzinfo=dt.UTC)])


def _bitemp_write_001_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 2, 15, tzinfo=dt.UTC)]
    )


def _bitemp_write_006_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 7, 1, tzinfo=dt.UTC)]
    )


def _bitemp_write_009_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 1, 1, tzinfo=dt.UTC)])


def _unit_work_015_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 10, 1, tzinfo=dt.UTC)])


def _value_object_032_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)]
    )


def _value_object_033_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 2, 15, tzinfo=dt.UTC)]
    )


WRITE_STORIES: Final[tuple[WriteStory, ...]] = (
    WriteStory(
        "m-unit-work-001",
        "Insert, then read your own write",
        "commit",
        "account",
        insert_then_read_your_own_write,
    ),
    WriteStory(
        "m-unit-work-002",
        "An aborted update is discarded",
        "abort",
        "account",
        aborted_update_is_discarded,
    ),
    WriteStory(
        "m-unit-work-003",
        "Foreign-key-ordered inserts in one transaction",
        "commit",
        "orders",
        fk_ordered_inserts,
    ),
    WriteStory(
        "m-unit-work-004",
        "The callback value is withheld on abort",
        "boundary",
        "account",
        callback_value_withheld_on_abort,
    ),
    WriteStory(
        "m-unit-work-005",
        "Keyed update, observed in-transaction",
        "commit",
        "account",
        keyed_update_observed_in_transaction,
    ),
    WriteStory(
        "m-unit-work-006",
        "Keyed delete, observed in-transaction",
        "commit",
        "account",
        keyed_delete_observed_in_transaction,
    ),
    WriteStory(
        "m-unit-work-007",
        "Create, then later delete, a parent/child pair",
        "commit",
        "orders",
        create_then_delete_a_parent_child_pair,
    ),
    WriteStory(
        "m-unit-work-009",
        "One flush, combined mixed-verb order",
        "commit",
        "account",
        one_flush_combined_mixed_verb_order,
    ),
    WriteStory(
        "m-unit-work-011",
        "An aborted insert never becomes durable",
        "abort",
        "account",
        aborted_insert_never_becomes_durable,
    ),
    WriteStory(
        "m-unit-work-012",
        "An aborted delete leaves the row standing",
        "abort",
        "account",
        aborted_delete_leaves_the_row_standing,
    ),
    WriteStory(
        "m-txtime-write-001",
        "Transaction-Time-Only insert opens a current milestone",
        "commit",
        "balance",
        transaction_time_only_insert_opens_a_current_milestone,
        clock=_txtime_write_001_clock,
    ),
    WriteStory(
        "m-txtime-write-002",
        "Transaction-Time-Only chain update via a sparse edited copy",
        "commit",
        "balance",
        transaction_time_only_chain_update_via_a_sparse_copy,
        clock=_txtime_write_002_clock,
    ),
    WriteStory(
        "m-txtime-write-003",
        "Transaction-Time-Only terminate closes the current milestone",
        "commit",
        "balance",
        transaction_time_only_terminate_closes_the_current_milestone,
        clock=_txtime_write_003_clock,
    ),
    WriteStory(
        "m-txtime-write-004",
        "Transaction-Time-Only chain update carries every new attribute",
        "commit",
        "balance",
        transaction_time_only_chain_update_carries_every_new_attribute,
        clock=_txtime_write_002_clock,
    ),
    WriteStory(
        "m-txtime-write-005",
        "Transaction-Time-Only chain update starting from existing history",
        "commit",
        "balance",
        transaction_time_only_chain_update_from_existing_history,
        clock=_txtime_write_005_clock,
    ),
    WriteStory(
        "m-opt-lock-002",
        "Versioned update advances the version ungated in locking mode",
        "commit",
        "account",
        versioned_update_advances_the_version_ungated_in_locking_mode,
    ),
    WriteStory(
        "m-batch-write-005",
        "A predicate-selected delete over an unversioned entity is readless",
        "commit",
        "wallet",
        wallet_predicate_delete_is_readless,
    ),
    WriteStory(
        "m-bitemp-write-001",
        "Bitemporal update-until splits head/middle/tail",
        "commit",
        "position",
        bitemporal_update_until_splits_head_middle_tail,
        clock=_bitemp_write_001_clock,
    ),
    WriteStory(
        "m-bitemp-write-003",
        "Bitemporal insert-until opens one bounded rectangle",
        "commit",
        "position",
        bitemporal_insert_until_opens_one_bounded_rectangle,
        clock=_bitemp_write_003_clock,
    ),
    WriteStory(
        "m-bitemp-write-006",
        "Bitemporal plain update splits head and new tail",
        "commit",
        "position",
        bitemporal_plain_update_splits_head_and_new_tail,
        clock=_bitemp_write_006_clock,
    ),
    WriteStory(
        "m-bitemp-write-009",
        "Bitemporal plain insert opens a fully-current rectangle",
        "commit",
        "position",
        bitemporal_plain_insert_opens_a_fully_current_rectangle,
        clock=_bitemp_write_009_clock,
    ),
    WriteStory(
        "m-unit-work-015",
        "A close settles against the milestone its own find observed",
        "commit",
        "position",
        a_close_settles_against_the_milestone_its_own_find_observed,
        clock=_unit_work_015_clock,
    ),
    WriteStory(
        "m-value-object-032",
        "Supplier Transaction-Time-Only chain update carries the address document",
        "commit",
        "supplier",
        supplier_transaction_time_only_chain_update_carries_the_document,
        clock=_value_object_032_clock,
    ),
    WriteStory(
        "m-value-object-033",
        "Branch bitemporal rectangle split carries the address document",
        "commit",
        "branch",
        branch_bitemporal_rectangle_split_carries_the_document,
        clock=_value_object_033_clock,
    ),
    WriteStory(
        "m-value-object-025",
        "Customer insert carries the whole address document atomically",
        "commit",
        "customer",
        customer_insert_carries_the_whole_address_document,
    ),
    WriteStory(
        "m-value-object-026",
        "Customer update replaces the whole address document",
        "commit",
        "customer",
        customer_update_replaces_the_whole_address_document,
    ),
    WriteStory(
        "m-value-object-027",
        "Customer update nulls the address document out",
        "commit",
        "customer",
        customer_update_nulls_the_address_document_out,
    ),
)
