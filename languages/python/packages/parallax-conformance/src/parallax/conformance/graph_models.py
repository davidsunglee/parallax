# ruff: noqa: UP037 - Relationship targets remain strings until model formation.

from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    DomainModel,
    Rel,
    TxTemporal,
    attr,
    index,
    rel,
)

_NS = "parallax.compatibility"

__all__ = ["INVOICE_MODEL", "POLICY_MODEL", "Claim", "Coverage", "Invoice", "InvoiceLine", "Policy"]


class Policy(
    Bitemporal,
    table="policy",
    namespace=_NS,
):
    """Mirror of ``models/policy.yaml`` ``Policy`` (bitemporal, root of the
    ``coverages`` to-many relationship)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    coverages: Rel[tuple["Coverage", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "policy_id"), dependent=True
    )


class Coverage(
    Bitemporal,
    table="coverage",
    namespace=_NS,
    indices=(index("coverage_policy", "policy_id"),),
):
    """Mirror of ``models/policy.yaml`` ``Coverage`` (bitemporal; the temporal
    navigate hop ``Policy.coverages`` reaches)."""

    id: Attr[int] = attr(primary_key=True)
    policy_id: Attr[int]
    amount: Attr[Decimal] = attr(precision=18, scale=2)
    claims: Rel[tuple["Claim", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "coverage_id"), dependent=True
    )
    policy: Rel[Policy | None] = rel(reverse_of="coverages")


class Claim(
    Bitemporal,
    table="claim",
    namespace=_NS,
    indices=(index("claim_coverage", "coverage_id"),),
):
    """Mirror of ``models/policy.yaml`` ``Claim`` (bitemporal; the to-one
    ``coverage`` hop reaches a milestoned Coverage)."""

    id: Attr[int] = attr(primary_key=True)
    coverage_id: Attr[int]
    reserve: Attr[Decimal] = attr(precision=18, scale=2)
    coverage: Rel[Coverage | None] = rel(reverse_of="claims")


POLICY_MODEL = DomainModel(Policy, Coverage, Claim)


class Invoice(TxTemporal, table="invoice", namespace=_NS):
    """Mirror of ``models/invoice.yaml`` ``Invoice`` (Transaction-Time-only, root of
    the ``lines`` to-many relationship)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    lines: Rel[tuple["InvoiceLine", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "invoice_id"), dependent=True
    )


class InvoiceLine(
    TxTemporal,
    table="invoice_line",
    namespace=_NS,
    indices=(index("invoice_line_invoice", "invoice_id"),),
):
    """Mirror of ``models/invoice.yaml`` ``InvoiceLine`` (Transaction-Time-only)."""

    id: Attr[int] = attr(primary_key=True)
    invoice_id: Attr[int]
    amount: Attr[Decimal] = attr(precision=18, scale=2)


INVOICE_MODEL = DomainModel(Invoice, InvoiceLine)
