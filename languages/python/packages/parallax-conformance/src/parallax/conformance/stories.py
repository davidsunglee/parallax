"""``parallax.conformance.stories`` — executable API-suite write stories.

Each story is ONE executable function over the **public** developer surface
(`parallax.snapshot.connect` → ``db.transact``), mirroring one corpus case, and
is the single source three consumers share (python.md §"API Conformance Suite" /
IMPLEMENTING.md "Continuous API Conformance Lane"):

- the Usage Guide renders each story's own source (`story_snippet`), so the
  documented spelling IS the executed spelling and cannot drift;
- the real-database suite (`tests/api_conformance/test_story_run.py`) executes each
  story through the shipped ``parallax-snapshot`` extension and
  ``parallax-postgres`` adapter against real Postgres, grading the case's
  expected rows / table state / abort outcome;
- the fake-port write no-drift guard (`tests/api_conformance/test_write_no_drift.py`)
  drives the same functions against a recording port as the supplementary
  wire-golden proof (commit stories emit the golden DML; abort stories emit
  nothing for the discarded buffer).

The story functions deliberately carry no docstrings: their bodies are the guide
snippets. They use the D-16 **graduated, full** transaction verbs (COR-3 Phase 7
increment 6a): ``tx.insert(instance)`` (the Create Payload), ``tx.update(copy)``
(an edited copy carrying a Change Record — ``model_copy(update={...})``),
``tx.delete(node_or_instance)``, and ``tx.find(statement)`` returning
``Snapshot[T]``. The `m-opt-lock` observation-gating rule (COR-3 Phase 8
increment 3 for UPDATE, extended to DELETE by a Phase-8 mid-phase review
remediation and a confirmation-pass residual — `python.md` §5 "a keyed update
or delete of a versioned row this unit of work never observed raises in
either mode"): a versioned keyed update/delete REQUIRES the edited copy's /
deleted node's provenance to derive from a `tx.find` this SAME transaction ran
(the framework never issues an implicit resolving read on a keyed write), so
every story writing a versioned row fetches it first —
`keyed_update_observed_in_transaction`, `keyed_delete_observed_in_transaction`,
`one_flush_combined_mixed_verb_order` (both legs), and
`aborted_delete_leaves_the_row_standing` (whose force-flushed delete, forced
onto the wire before the deliberate abort exactly like
`callback_value_withheld_on_abort`'s own force-flush-then-abort pattern, is
gated exactly like any other keyed delete) each add that observing fetch. The
core amendment bundle (COR-3 Phase 8) closed the matching corpus gap:
`m-unit-work-005/006/009/012` now author the SAME observing find(s) before
their versioned keyed write(s), so every story here grades byte-exact against
its own mirrored case (`test_write_no_drift.py`) as the plain graded idiom —
no story is guide-only. The one `tx.delete` story that never observes,
`create_then_delete_a_parent_child_pair`, targets a non-versioned entity
(Order/OrderItem) never re-observed anywhere in that transaction's own
choreography — no observation is required there.

**Instance-native grading** (D-23, COR-3 Phase 8 increment 7 completion round):
a story returning rows returns the TYPED INSTANCES a `Snapshot[T]` itself
already materializes (`.results()`), never a rendered row dict — the row
rendering (`instance_row`, physical-column-keyed) happens at the GRADING seam
(`test_story_run.py`), the same convention the read/graph stories already use.
The retired `_as_rows`/`canonical_row` rendering carried a LATENT camelCase
drift risk invisible on the 10 `m-unit-work` stories (Account's canonical and
physical column names happen to coincide) that would have surfaced the moment
a story used an entity whose names diverge (`Balance.acctNum`/`acct_num`,
`Position.valid_start`, …) — exactly the temporal stories
below.

**Temporal stories** (D-29/D-30/D-31, COR-3 Phase 8 increment 7 completion
round) construct axis-governed attributes CLEANLY (never a placeholder
milestone value, D-31's construction optionality) and drive successive
distinct Transaction-Time instants via a scripted clock (`clock=`,
:class:`~parallax.conformance.scripted_clock.ScriptedClock`) — one corpus
writeSequence entry, one flushing `db.transact` call, one scripted instant,
in entry order (the engine's own demarcation, DQ4). A "chain-update via a
sparse edited copy" story (`audit_only_chain_update_via_a_sparse_copy`, the
Supplier value-object sibling) drives the D-30 fix for real: the edited copy
touches only the field it changes, and the framework merges the observed
payload onto it so the chained row still carries every untouched field.
"""

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
    CUSTOMER_REGISTRY,
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
from parallax.core.entity import Entity, EntityRegistry
from parallax.core.unit_work import Clock
from parallax.snapshot.handle import Database, Transaction

__all__ = ["WRITE_STORIES", "WriteStory", "story_snippet"]

# How a story concludes, which is also how each consumer grades it: a `commit`
# story returns its final observation; an `abort` story suppresses its own
# deliberate failure and returns the follow-up observation proving the discard;
# a `boundary` story lets the failure propagate (the withheld-value contract).
StoryKind = Literal["commit", "abort", "boundary"]


@dataclass(frozen=True, slots=True)
class WriteStory:
    """One executable public-API story mirroring a corpus write case.

    ``run`` returns the TYPED INSTANCES a story's own final observing find
    materialized (`Snapshot[T].results()`, instance-native grading, D-23) —
    never a rendered row: the real-Postgres runner (`test_story_run.py`)
    renders them to the physical-column-keyed row form (`instance_row`) at
    the grading seam, the SAME convention the read/graph stories already use.

    ``clock`` (D-29, COR-3 Phase 8 increment 7 completion round) is an
    OPTIONAL zero-argument :class:`~parallax.core.unit_work.Clock` factory: a
    temporal writeSequence story needing successive distinct processing
    instants across its own choreography (one corpus writeSequence entry, one
    flushing ``db.transact`` call, one Clock read each) sets it to something
    like ``lambda: ScriptedClock([...])``
    (:class:`~parallax.conformance.scripted_clock.ScriptedClock`) — a FACTORY,
    not a shared instance, so each harness consumer (the fake-port no-drift
    guard, the real-Postgres story runner) drives its own fresh clock rather
    than exhausting a script the other consumer already advanced. ``None``
    (every pre-D-29 story, unchanged) connects with no explicit clock at all —
    the system clock (`Database.connect`'s own default).

    ``registry`` (D-33, Phase-9 ledger sweep) is the OPTIONAL
    :class:`~parallax.core.entity.base.EntityRegistry` a story's own entity
    classes are compiled under, needed only when that differs from the
    process default (ledger D-20's fix: the Customer/Location/Depot mirror
    lives in its OWN `vo_models.CUSTOMER_REGISTRY`, exactly like the graph
    stories' `_reset_for_registry` precedent in `test_story_run.py`) —
    `None` (every other story, unchanged) connects through the ingested
    corpus descriptor, the process-default-registry `resolve_entity_class`
    seam finds every other story's classes through."""

    case_id: str
    title: str
    kind: StoryKind
    model: str
    run: Callable[[Database], list[Entity] | None]
    clock: Callable[[], Clock] | None = None
    registry: EntityRegistry | None = None


def story_snippet(story: WriteStory) -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return inspect.getsource(story.run).rstrip("\n")


# --------------------------------------------------------------------------- #
# m-unit-work: the 10 non-temporal Account/Order(Item) stories.               #
# --------------------------------------------------------------------------- #
def insert_then_read_your_own_write(db: Database) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        tx.insert(Account(id=7, owner="Newton", balance=Decimal("5.00"), version=1))
        return list(tx.find(Account.where(Account.id == 7)).results())

    return db.transact(fn)  # the dependent find observes the flushed insert


def aborted_update_is_discarded(db: Database) -> list[Entity]:
    fetched = db.transact(lambda tx: tx.find(Account.where(Account.id == 1))).result()
    edited = fetched.model_copy(update={"balance": Decimal("999.00")})

    def doomed(tx: Transaction) -> None:
        tx.update(edited)
        raise RuntimeError("changed my mind")  # abort: the buffered update is discarded

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The same find re-resolves and observes the ORIGINAL balance, not 999.00.
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 1))).results())


def fk_ordered_inserts(db: Database) -> None:
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

    db.transact(fn)  # the flush inserts the parent before the child


def callback_value_withheld_on_abort(db: Database) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()  # observe the row
        tx.update(current.model_copy(update={"balance": Decimal("175.00")}))
        tx.find(Account.where(Account.id == 1))  # forces the flush
        raise RuntimeError("abort")  # even the force-flushed write is rolled back

    return db.transact(fn)  # raises — no value is returned as though durable


def keyed_update_observed_in_transaction(db: Database) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()  # observe the version
        tx.update(current.model_copy(update={"balance": Decimal("175.00")}))
        return list(tx.find(Account.where(Account.id == 1)).results())

    return db.transact(fn)


def keyed_delete_observed_in_transaction(db: Database) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 3)).result()  # observe the version
        tx.delete(current)
        return list(tx.find(Account.where(Account.id == 3)).results())

    return db.transact(fn)  # [] — the dependent find observes the deletion


def create_then_delete_a_parent_child_pair(db: Database) -> None:
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
        tx.delete(OrderItem(id=200, order_id=100, sku="X-1", quantity=3))  # child first
        tx.delete(
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

    db.transact(create)
    db.transact(teardown)


def one_flush_combined_mixed_verb_order(db: Database) -> list[Entity]:
    def fn(tx: Transaction) -> list[Entity]:
        current = tx.find(Account.where(Account.id == 1)).result()  # observe the version
        deleted = tx.find(Account.where(Account.id == 3)).result()  # observe the version
        tx.insert(Account(id=9, owner="Noether", balance=Decimal("5.00"), version=1))
        tx.update(current.model_copy(update={"balance": Decimal("20.00")}))
        tx.delete(deleted)
        return list(tx.find(Account.where(Account.balance < 50.00)).results())

    return db.transact(fn)  # observe, then one flush: insert, update, delete — then the find


def aborted_insert_never_becomes_durable(db: Database) -> list[Entity]:
    def doomed(tx: Transaction) -> None:
        tx.insert(Account(id=7, owner="Newton", balance=Decimal("5.00"), version=1))
        raise RuntimeError("abort")

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The aborted insert was discarded: the find observes NO rows for account 7.
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 7))).results())


def aborted_delete_leaves_the_row_standing(db: Database) -> list[Entity]:
    def doomed(tx: Transaction) -> None:
        current = tx.find(Account.where(Account.id == 3)).result()  # observe the version
        tx.delete(current)
        tx.find(Account.where(Account.id == 3))  # forces the flush of the buffered delete
        raise RuntimeError("abort")  # even the force-flushed delete is rolled back

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The aborted delete was discarded: account 3 still stands.
    return list(db.transact(lambda tx: tx.find(Account.where(Account.id == 3))).results())


# --------------------------------------------------------------------------- #
# m-audit-write: Balance (audit-only) milestone-chaining stories (D-29/D-31). #
# --------------------------------------------------------------------------- #
def audit_only_insert_opens_a_current_milestone(db: Database) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    db.transact(fn)


def audit_only_terminate_closes_the_current_milestone(db: Database) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def close(tx: Transaction) -> None:
        # Observe the current milestone FIRST (`python.md` §5: temporal
        # update/terminate follow the same prior-observation rule as versioned
        # writes — in the default locking mode, the find's shared lock is
        # exactly what licenses the ungated close), then close it keyed off
        # the primary key alone (close-only, no chained row).
        current = tx.find(Balance.where(Balance.id == 1)).result()
        tx.terminate(current)

    db.transact(insert)
    db.transact(close)


def audit_only_chain_update_via_a_sparse_copy(db: Database) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()  # observe the milestone
        # The edited copy touches ONLY `value` — the D-30 fix merges the
        # observed payload onto it, so the chained row still carries `A`.
        tx.update(current.model_copy(update={"value": Decimal("150.00")}))

    db.transact(insert)
    db.transact(update)


def audit_only_chain_update_carries_every_new_attribute(db: Database) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(Balance(id=1, acct_num="A", value=Decimal("100.00")))

    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()  # observe the milestone
        tx.update(current.model_copy(update={"acct_num": "B", "value": Decimal("250.00")}))

    db.transact(insert)
    db.transact(update)


def audit_only_chain_update_from_existing_history(db: Database) -> None:
    # m-audit-write-005: the fixtures are loaded (`given.fixtures: true`) —
    # id 1 already carries a superseded [2024-01-01, 2024-06-01) milestone
    # (value 100.00) and a CURRENT [2024-06-01, infinity) milestone (value
    # 150.00). The close predicate (bal_id AND out_z = infinity) selects
    # exactly the ONE current row even with a superseded prior on record.
    def update(tx: Transaction) -> None:
        current = tx.find(Balance.where(Balance.id == 1)).result()  # observe the CURRENT milestone
        tx.update(current.model_copy(update={"value": Decimal("175.00")}))

    db.transact(update)


# --------------------------------------------------------------------------- #
# m-opt-lock: Account (versioned, non-temporal) keyed-write stories.          #
# --------------------------------------------------------------------------- #
def versioned_update_advances_the_version_ungated_in_locking_mode(db: Database) -> None:
    # m-opt-lock-002: the DEFAULT `locking` mode's in-transaction read already
    # took a shared row lock, so the keyed update needs no version check — it
    # advances the version with NO `and version = ?` gate (contrast optimistic
    # mode, m-opt-lock-005/-006). A writeSequence story (the corpus case's own
    # shape): no trailing find, the committed table state is the oracle.
    def fn(tx: Transaction) -> None:
        current = tx.find(Account.where(Account.id == 2)).result()  # observe the version
        tx.update(current.model_copy(update={"balance": Decimal("500.00")}))

    db.transact(fn)


# --------------------------------------------------------------------------- #
# m-batch-write: Wallet (unversioned, non-temporal) predicate-write stories.  #
# --------------------------------------------------------------------------- #
def wallet_predicate_delete_is_readless(db: Database) -> list[Entity]:
    # m-batch-write-005: Wallet carries no version and no temporal axis, so a
    # predicate-selected delete has nothing to gate per row — it lowers
    # DIRECTLY to one set-shaped `delete ... where balance < ?`, no
    # materializing read at all (contrast the versioned set delete,
    # m-opt-lock-015/m-batch-write-004). The verifying find carries no shared
    # read lock (the case's own lock-free golden) — optimistic concurrency,
    # never the locking-mode default (which would take one on ANY
    # transactional entity's find, m-read-lock-001).
    def fn(tx: Transaction) -> list[Entity]:
        tx.delete_where(Wallet.where(Wallet.balance < 200.00))
        return list(tx.find(Wallet.where(Wallet.balance < 200.00)).results())

    return db.transact(fn, concurrency="optimistic")


# --------------------------------------------------------------------------- #
# m-bitemp-write: Position (full bitemporal) stories (D-29/D-31).            #
# --------------------------------------------------------------------------- #
def bitemporal_insert_until_opens_one_bounded_rectangle(db: Database) -> None:
    def fn(tx: Transaction) -> None:
        tx.insert_until(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)


def bitemporal_plain_update_splits_head_and_new_tail(db: Database) -> None:
    # m-bitemp-write-006: a plain (unbounded) bitemporal `tx.update` is the
    # two-way degenerate of the rectangle split — no middle, no old tail (the
    # correction runs to infinity): inactivate the original on the processing
    # axis, then chain head (the OLD value, business [from_z, B)) + a new tail
    # (the NEW value, business [B, infinity)).
    def insert(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def correct(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1)).result()  # observe the rectangle
        tx.update(
            current.model_copy(update={"value": Decimal("200.00")}),
            valid_from=dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(correct)


def bitemporal_plain_insert_opens_a_fully_current_rectangle(db: Database) -> None:
    # m-bitemp-write-009: a plain (unbounded) bitemporal insert is a SINGLE
    # insert of a fully-current rectangle — business [B, infinity) at
    # processing [txInstant, infinity), current on BOTH axes. No prior row to
    # close, unlike the plain update/terminate splits.
    def fn(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)


def bitemporal_update_until_splits_head_middle_tail(db: Database) -> None:
    def insert(tx: Transaction) -> None:
        tx.insert(
            Position(id=1, acct_num="A", value=Decimal("100.00")),
            valid_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )

    def split(tx: Transaction) -> None:
        current = tx.find(Position.where(Position.id == 1)).result()  # observe the rectangle
        tx.update_until(
            current.model_copy(update={"value": Decimal("200.00")}),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(split)


# --------------------------------------------------------------------------- #
# m-value-object: Supplier (audit-only) / Branch (bitemporal) VO-owner        #
# stories — the value-object document rides milestone chaining/splitting     #
# exactly like a scalar column (D-30/D-31, D-23).                            #
# --------------------------------------------------------------------------- #
def supplier_audit_chain_update_carries_the_document(db: Database) -> None:
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
        current = tx.find(Supplier.where(Supplier.id == 1)).result()  # observe the milestone
        # The edited copy touches ONLY `address` — the D-30 fix merges the
        # observed payload onto it, so the chained row still carries `name`.
        tx.update(
            current.model_copy(
                update={
                    "address": Address(
                        street="2 New Avenue",
                        city="Bergen",
                        geo=Geo(country="NO"),
                        phones=(
                            Phone(type="work", number="555-0200"),
                            Phone(type="home", number="555-0201"),
                        ),
                    )
                }
            )
        )

    db.transact(insert)
    db.transact(update)


def branch_bitemporal_rectangle_split_carries_the_document(db: Database) -> None:
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
        current = tx.find(Branch.where(Branch.id == 1)).result()  # observe the rectangle
        tx.update_until(
            current.model_copy(
                update={
                    "address": Address(
                        street="30 New Road",
                        city="Tampere",
                        geo=Geo(country="FI"),
                        phones=(
                            Phone(type="main", number="555-3000"),
                            Phone(type="fax", number="555-3001"),
                        ),
                    )
                }
            ),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    db.transact(insert)
    db.transact(split)


# --------------------------------------------------------------------------- #
# m-value-object: Customer (non-temporal) VO-owner write stories (D-33, the   #
# Phase-9 ledger sweep) — the recursive `address` composite (`CustomerGeo`    #
# declares OPTIONAL `elevation`/`point`, unlike Supplier/Branch's own `Geo`),  #
# so these are the FIRST write stories to exercise `to_document`'s D-33       #
# omit-unset-optional-inner-members fix. Compiled under the Customer/         #
# Location/Depot family's OWN `CUSTOMER_REGISTRY` (ledger D-20), never the    #
# process default — see `WriteStory.registry`'s own docstring.               #
# --------------------------------------------------------------------------- #
def customer_insert_carries_the_whole_address_document(db: Database) -> None:
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


def customer_update_replaces_the_whole_address_document(db: Database) -> None:
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
        current = tx.find(Customer.where(Customer.id == 200)).result()  # observe the row
        # The new document drops `geo` and shrinks `phones` to one element —
        # a WHOLE-document replace, never a path-level merge with the prior
        # value (`m-value-object-026`'s own note).
        tx.update(
            current.model_copy(
                update={
                    "address": CustomerAddress(
                        street="9 New Way",
                        city="Stavanger",
                        phones=(CustomerPhone(type="work", number="555-2222"),),
                    )
                }
            )
        )

    db.transact(insert)
    db.transact(replace)


def customer_update_nulls_the_address_document_out(db: Database) -> None:
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
        current = tx.find(Customer.where(Customer.id == 300)).result()  # observe the row
        tx.update(current.model_copy(update={"address": None}))

    db.transact(insert)
    db.transact(null_out)


# --------------------------------------------------------------------------- #
# Per-story scripted clocks (D-29): one scripted instant per `db.transact`    #
# call above, in entry order, matching each mirrored case's own authored     #
# `at`/`until` instants.                                                     #
# --------------------------------------------------------------------------- #
def _audit_write_001_clock() -> Clock:
    return ScriptedClock([dt.datetime(2024, 1, 1, tzinfo=dt.UTC)])


def _audit_write_002_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 6, 1, tzinfo=dt.UTC)]
    )


def _audit_write_003_clock() -> Clock:
    return ScriptedClock(
        [dt.datetime(2024, 1, 1, tzinfo=dt.UTC), dt.datetime(2024, 8, 1, tzinfo=dt.UTC)]
    )


def _audit_write_005_clock() -> Clock:
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
        "m-audit-write-001",
        "Audit-only insert opens a current milestone",
        "commit",
        "balance",
        audit_only_insert_opens_a_current_milestone,
        clock=_audit_write_001_clock,
    ),
    WriteStory(
        "m-audit-write-002",
        "Audit-only chain update via a sparse edited copy",
        "commit",
        "balance",
        audit_only_chain_update_via_a_sparse_copy,
        clock=_audit_write_002_clock,
    ),
    WriteStory(
        "m-audit-write-003",
        "Audit-only terminate closes the current milestone",
        "commit",
        "balance",
        audit_only_terminate_closes_the_current_milestone,
        clock=_audit_write_003_clock,
    ),
    WriteStory(
        "m-audit-write-004",
        "Audit-only chain update carries every new attribute",
        "commit",
        "balance",
        audit_only_chain_update_carries_every_new_attribute,
        clock=_audit_write_002_clock,
    ),
    WriteStory(
        "m-audit-write-005",
        "Audit-only chain update starting from existing history",
        "commit",
        "balance",
        audit_only_chain_update_from_existing_history,
        clock=_audit_write_005_clock,
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
        "m-value-object-032",
        "Supplier audit chain update carries the address document",
        "commit",
        "supplier",
        supplier_audit_chain_update_carries_the_document,
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
        registry=CUSTOMER_REGISTRY,
    ),
    WriteStory(
        "m-value-object-026",
        "Customer update replaces the whole address document",
        "commit",
        "customer",
        customer_update_replaces_the_whole_address_document,
        registry=CUSTOMER_REGISTRY,
    ),
    WriteStory(
        "m-value-object-027",
        "Customer update nulls the address document out",
        "commit",
        "customer",
        customer_update_nulls_the_address_document_out,
        registry=CUSTOMER_REGISTRY,
    ),
)
