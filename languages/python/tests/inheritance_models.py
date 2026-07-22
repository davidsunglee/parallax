"""Idiomatic entity classes mirroring the corpus's inheritance families
(D-7 inheritance class spelling, DQ2, COR-3 Phase 7 increment 6a):
``models/payment.yaml`` (table-per-hierarchy: ``Payment`` / ``CardPayment`` /
``CashPayment``), ``models/document.yaml`` (table-per-concrete-subtype, with
an intermediate abstract subtype and a polymorphic owner: ``Document`` /
``FinancialDocument`` / ``Invoice`` / ``Receipt`` / ``Memo`` / ``Folder``), and
``models/rate.yaml`` (table-per-concrete-subtype BITEMPORAL, the root ALONE
extending the ``Bitemporal`` framework base: ``Rate`` / ``DepositRate`` /
``LoanRate``). This module deliberately
avoids ``from __future__ import annotations`` so the metaclass reads the live
``Attr[T]`` / ``Rel[T]`` objects directly.

The corpus-named classes themselves are **re-exported** from
``parallax.conformance.read_models`` (the installed package's own mirror,
which the API Conformance Suite's real-database read stories execute against
`db.find` — a real dev-only package module needs classes resolvable at
ordinary import time, not only under pytest's test-path magic): they are
declared there ONCE, so the unit lane's frontend/no-drift tests here and the
API-suite's execution both resolve the exact SAME registered class, never a
second, differently-scoped copy that would silently race it in the shared,
global, process-wide entity registry.

Lives at the top level of ``tests/`` (moved from ``tests/unit/`` in increment
6b) rather than lane-local: the unit lane's frontend/no-drift tests AND the API
Conformance Suite's descriptor no-drift guard both need the SAME classes, and
only a module directly on ``pythonpath = ["tools", "tests"]`` resolves
reliably regardless of which lane's files pytest collects first.
"""

from parallax.conformance.read_models import (
    CardPayment,
    CashPayment,
    DepositRate,
    Document,
    FinancialDocument,
    Folder,
    Invoice,
    LoanRate,
    Memo,
    Payment,
    Rate,
    Receipt,
)

__all__ = [
    "CardPayment",
    "CashPayment",
    "DepositRate",
    "Document",
    "FinancialDocument",
    "Folder",
    "Invoice",
    "LoanRate",
    "Memo",
    "Payment",
    "Rate",
    "Receipt",
]
