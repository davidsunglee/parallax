"""Idiomatic entity classes mirroring the corpus's two inheritance families
(D-7 inheritance class spelling, DQ2, COR-3 Phase 7 increment 6a):
``models/payment.yaml`` (table-per-hierarchy: ``Payment`` / ``CardPayment`` /
``CashPayment``) and ``models/document.yaml`` (table-per-concrete-subtype, with
an intermediate abstract subtype and a polymorphic owner: ``Document`` /
``FinancialDocument`` / ``Invoice`` / ``Receipt`` / ``Memo`` / ``Folder``).
This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.

The corpus-named classes themselves are **re-exported** from
``parallax.conformance.read_models`` (the installed package's own mirror,
which the API Conformance Suite's real-database read stories execute against
`db.find` — a real dev-only package module needs classes resolvable at
ordinary import time, not only under pytest's test-path magic): they are
declared there ONCE, so the unit lane's frontend/no-drift tests here and the
API-suite's execution both resolve the exact SAME registered class, never a
second, differently-scoped copy that would silently race it in the shared,
global, process-wide entity registry. ``WirePayment`` stays local: a
standalone structural fixture no corpus no-drift proof or read example needs.

Lives at the top level of ``tests/`` (moved from ``tests/unit/`` in increment
6b) rather than lane-local: the unit lane's frontend/no-drift tests AND the API
Conformance Suite's descriptor no-drift guard both need the SAME classes, and
only a module directly on ``pythonpath = ["tools", "tests"]`` resolves
reliably regardless of which lane's files pytest collects first.
"""

from parallax.conformance.read_models import (
    CardPayment,
    CashPayment,
    Document,
    FinancialDocument,
    Folder,
    Invoice,
    Memo,
    Payment,
    Receipt,
)
from parallax.core import Attr, EntityConfig, Field
from parallax.core.entity.base import Concrete

__all__ = [
    "CardPayment",
    "CashPayment",
    "Document",
    "FinancialDocument",
    "Folder",
    "Invoice",
    "Memo",
    "Payment",
    "Receipt",
    "WirePayment",
]

_NS = "parallax.compatibility"


class WirePayment(Payment, frozen=True):
    """A TPH concrete subtype with an EXPLICIT table override — D-7's escape
    hatch: ``EntityConfig(table=...)`` wins over the strategy's own shared-
    table default (not part of the payment.yaml no-drift proof; a standalone
    structural fixture)."""

    __parallax__ = EntityConfig(
        table="wire_payment",
        namespace=_NS,
        mutability="transactional",
        inheritance=Concrete(tag_value="wire"),
    )

    reference: Attr[str | None] = Field(type="string", max_length=32, nullable=True)
