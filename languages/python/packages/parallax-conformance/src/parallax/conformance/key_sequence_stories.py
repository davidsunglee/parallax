"""Public-API stories mirroring the corpus's native key-sequence write cases:
each keyless draft is inserted through ``tx.insert``, which takes its key from
the block a native reservation holds, one ``db.transact`` per write-sequence
entry."""

from __future__ import annotations

from parallax.conformance.key_sequence_models import (
    AuditEntry,
    Badge,
    KeySequencePass,
    Pass,
    Ticket,
    Voucher,
    Wristband,
)
from parallax.snapshot import ScopedDatabase, TxnContext

__all__ = [
    "a_block_is_clipped_at_the_key_range_end",
    "a_block_of_one_holds_one_key",
    "a_keyless_transaction_time_insert_opens_its_milestone_under_its_key",
    "a_reservation_answers_its_initial_value",
    "a_stride_spaces_the_keys_of_a_block",
    "an_unused_remainder_of_a_block_is_abandoned",
    "each_reservation_of_a_block_of_one_advances_by_the_stride",
    "each_transaction_reserves_the_next_block",
    "each_unit_of_work_reserves_the_next_strided_block",
    "keyless_drafts_take_keys_from_one_reserved_block",
    "keyless_drafts_take_keys_ten_apart_from_one_block",
    "supplied_keys_spend_nothing_beside_a_keyless_draft",
    "the_fourth_draft_refills_the_reservation",
]


def a_block_of_one_holds_one_key(db: ScopedDatabase) -> None:
    db.transact(lambda tx: tx.insert(Badge(holder="Bo")))


def each_transaction_reserves_the_next_block(db: ScopedDatabase) -> None:
    for holder in ("Bo", "Cy", "Di"):
        db.transact(lambda tx, holder=holder: tx.insert(Badge(holder=holder)))


def a_reservation_answers_its_initial_value(db: ScopedDatabase) -> None:
    db.transact(lambda tx: tx.insert(Ticket(tier="gold")))


def each_reservation_of_a_block_of_one_advances_by_the_stride(db: ScopedDatabase) -> None:
    for tier in ("gold", "silver", "bronze"):
        db.transact(lambda tx, tier=tier: tx.insert(Ticket(tier=tier)))


def keyless_drafts_take_keys_from_one_reserved_block(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.insert(Pass(zone="north"))
        tx.insert(Pass(zone="south"))

    db.transact(fn)


def the_fourth_draft_refills_the_reservation(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        for zone in ("north", "south", "east", "west"):
            tx.insert(Pass(zone=zone))

    db.transact(fn)


def an_unused_remainder_of_a_block_is_abandoned(db: ScopedDatabase) -> None:
    db.transact(lambda tx: tx.insert(Pass(zone="north")))


def a_stride_spaces_the_keys_of_a_block(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.insert(Voucher(label="spring"))
        tx.insert(Voucher(label="summer"))

    db.transact(fn)


def each_unit_of_work_reserves_the_next_strided_block(db: ScopedDatabase) -> None:
    for labels in (("spring", "summer"), ("autumn", "winter")):

        def fn(tx: TxnContext, labels: tuple[str, str] = labels) -> None:
            for label in labels:
                tx.insert(Voucher(label=label))

        db.transact(fn)


def a_keyless_transaction_time_insert_opens_its_milestone_under_its_key(
    db: ScopedDatabase,
) -> None:
    db.transact(lambda tx: tx.insert(AuditEntry(note="opened")))


def keyless_drafts_take_keys_ten_apart_from_one_block(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.insert(KeySequencePass(holder="Bo"))
        tx.insert(KeySequencePass(holder="Cy"))

    db.transact(fn)


def supplied_keys_spend_nothing_beside_a_keyless_draft(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.insert(Badge(id=0, holder="Al"))
        tx.insert(Badge(holder="Bo"))
        tx.insert(Badge(id=7, holder="Cy"))

    db.transact(fn)


def a_block_is_clipped_at_the_key_range_end(db: ScopedDatabase) -> None:
    def fn(tx: TxnContext) -> None:
        tx.insert(Wristband(gate="east"))
        tx.insert(Wristband(gate="west"))

    db.transact(fn)
