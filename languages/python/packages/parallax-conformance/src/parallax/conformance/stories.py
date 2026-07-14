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
snippets. They use the D-16 **neutral, provisional** transaction verbs; the
Phase-7 instance model graduates the spellings (the guide carries the staging
notice).
"""

from __future__ import annotations

import contextlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.db_port import Row
from parallax.snapshot.handle import Database, Transaction

__all__ = ["WRITE_STORIES", "WriteStory", "story_snippet"]

# How a story concludes, which is also how each consumer grades it: a `commit`
# story returns its final observation; an `abort` story suppresses its own
# deliberate failure and returns the follow-up observation proving the discard;
# a `boundary` story lets the failure propagate (the withheld-value contract).
StoryKind = Literal["commit", "abort", "boundary"]


@dataclass(frozen=True, slots=True)
class WriteStory:
    """One executable public-API story mirroring a corpus write case."""

    case_id: str
    title: str
    kind: StoryKind
    model: str
    run: Callable[[Database], list[Row] | None]


def story_snippet(story: WriteStory) -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return inspect.getsource(story.run).rstrip("\n")


def insert_then_read_your_own_write(db: Database) -> list[Row]:
    def fn(tx: Transaction) -> list[Row]:
        tx.insert("Account", {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1})
        return tx.find("Account", {"eq": {"attr": "Account.id", "value": 7}})

    return db.transact(fn)  # the dependent find observes the flushed insert


def aborted_update_is_discarded(db: Database) -> list[Row]:
    db.transact(lambda tx: tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}}))

    def doomed(tx: Transaction) -> None:
        tx.update("Account", {"id": 1, "balance": 999.00, "version": 2})
        raise RuntimeError("changed my mind")  # abort: the buffered update is discarded

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The same find re-resolves and observes the ORIGINAL balance, not 999.00.
    return db.transact(lambda tx: tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}}))


def fk_ordered_inserts(db: Database) -> None:
    def fn(tx: Transaction) -> None:
        order = {"id": 100, "name": "Hopper", "sku": "X-1", "qty": 1}
        order |= {"price": 9.99, "active": True, "orderedOn": "2024-07-01"}
        tx.insert("Order", order)
        tx.insert("OrderItem", {"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3})

    db.transact(fn)  # the flush inserts the parent before the child


def callback_value_withheld_on_abort(db: Database) -> list[Row]:
    def fn(tx: Transaction) -> list[Row]:
        tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}})  # observe the row
        tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
        tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}})  # forces the flush
        raise RuntimeError("abort")  # even the force-flushed write is rolled back

    return db.transact(fn)  # raises — no value is returned as though durable


def keyed_update_observed_in_transaction(db: Database) -> list[Row]:
    def fn(tx: Transaction) -> list[Row]:
        tx.update("Account", {"id": 1, "balance": 175.00, "version": 2})
        return tx.find("Account", {"eq": {"attr": "Account.id", "value": 1}})

    return db.transact(fn)


def keyed_delete_observed_in_transaction(db: Database) -> list[Row]:
    def fn(tx: Transaction) -> list[Row]:
        tx.delete("Account", {"id": 3})
        return tx.find("Account", {"eq": {"attr": "Account.id", "value": 3}})

    return db.transact(fn)  # [] — the dependent find observes the deletion


def create_then_delete_a_parent_child_pair(db: Database) -> None:
    def create(tx: Transaction) -> None:
        order = {"id": 100, "name": "Hopper", "sku": "X-1", "qty": 1}
        order |= {"price": 9.99, "active": True, "orderedOn": "2024-07-01"}
        tx.insert("Order", order)
        tx.insert("OrderItem", {"id": 200, "orderId": 100, "sku": "X-1", "quantity": 3})

    def teardown(tx: Transaction) -> None:
        tx.delete("OrderItem", {"id": 200})  # child first, mirroring the FK-ordered insert
        tx.delete("Order", {"id": 100})

    db.transact(create)
    db.transact(teardown)


def one_flush_combined_mixed_verb_order(db: Database) -> list[Row]:
    def fn(tx: Transaction) -> list[Row]:
        tx.insert("Account", {"id": 9, "owner": "Noether", "balance": 5.00, "version": 1})
        tx.update("Account", {"id": 1, "balance": 20.00, "version": 2})
        tx.delete("Account", {"id": 3})
        return tx.find("Account", {"lessThan": {"attr": "Account.balance", "value": 50.00}})

    return db.transact(fn)  # one flush: insert, update, delete — then the find


def aborted_insert_never_becomes_durable(db: Database) -> list[Row]:
    def doomed(tx: Transaction) -> None:
        tx.insert("Account", {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1})
        raise RuntimeError("abort")

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The aborted insert was discarded: the find observes NO rows for account 7.
    return db.transact(lambda tx: tx.find("Account", {"eq": {"attr": "Account.id", "value": 7}}))


def aborted_delete_leaves_the_row_standing(db: Database) -> list[Row]:
    def doomed(tx: Transaction) -> None:
        tx.delete("Account", {"id": 3})
        raise RuntimeError("abort")

    with contextlib.suppress(RuntimeError):
        db.transact(doomed)
    # The aborted delete was discarded: account 3 still stands.
    return db.transact(lambda tx: tx.find("Account", {"eq": {"attr": "Account.id", "value": 3}}))


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
)
