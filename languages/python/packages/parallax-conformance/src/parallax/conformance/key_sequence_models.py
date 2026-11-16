"""Entity Classes mirroring the corpus's native key-sequence models."""

from __future__ import annotations

from typing import Final

from parallax.core import Attr, DomainModel, Entity, Int32, KeySequence, TxTemporal, attr

__all__ = [
    "PK_AUDIT_MODEL",
    "PK_KEY_SEQUENCE_MODEL",
    "PK_SEQUENCE_MODEL",
    "AuditEntry",
    "Badge",
    "KeySequencePass",
    "Pass",
    "Ticket",
    "Voucher",
    "Wristband",
]

_NS: Final = "parallax.compatibility"


class Badge(Entity, table="badge", namespace=_NS):
    id: Attr[int] = attr(primary_key=KeySequence("badge_seq", batch_size=1))
    holder: Attr[str] = attr(max_length=64)


class Ticket(Entity, table="ticket", namespace=_NS):
    id: Attr[int] = attr(
        primary_key=KeySequence("ticket_seq", batch_size=1, initial_value=1000, increment_size=5)
    )
    tier: Attr[str] = attr(max_length=64)


class Pass(Entity, table="pass", namespace=_NS):
    id: Attr[int] = attr(primary_key=KeySequence("pass_seq", batch_size=3))
    zone: Attr[str] = attr(max_length=64)


class Voucher(Entity, table="voucher", namespace=_NS):
    id: Attr[int] = attr(
        primary_key=KeySequence("voucher_seq", batch_size=2, initial_value=100, increment_size=10)
    )
    label: Attr[str] = attr(max_length=64)


class Wristband(Entity, table="wristband", namespace=_NS):
    id: Attr[int] = attr(
        type=Int32,
        primary_key=KeySequence("wristband_seq", batch_size=3, initial_value=2**31 - 2),
    )
    gate: Attr[str] = attr(max_length=64)


PK_SEQUENCE_MODEL: Final = DomainModel(Badge, Ticket, Pass, Voucher, Wristband)


class AuditEntry(TxTemporal, table="audit_entry", namespace=_NS):
    id: Attr[int] = attr(primary_key=KeySequence("entry_seq"))
    note: Attr[str] = attr(max_length=64)


PK_AUDIT_MODEL: Final = DomainModel(AuditEntry)


class KeySequencePass(Entity, name="Pass", table="pass", namespace=_NS):
    id: Attr[int] = attr(
        primary_key=KeySequence("pass_ids", batch_size=3, initial_value=100, increment_size=10)
    )
    holder: Attr[str] = attr(max_length=64)


PK_KEY_SEQUENCE_MODEL: Final = DomainModel(KeySequencePass)
