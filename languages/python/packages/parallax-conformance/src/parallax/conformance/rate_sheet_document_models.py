from parallax.core import (
    ONE_TO_MANY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Int32,
    Rel,
    attr,
    desc,
    rel,
)

_NS = "parallax.compatibility"

__all__ = ["RATE_SHEET_DOCUMENT_MODEL", "RateSheet", "SheetDeposit", "SheetLoan", "SheetRate"]


class SheetRate(
    Bitemporal,
    namespace=_NS,
    layout=Document(),
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
):
    id: Attr[int] = attr(primary_key=True)
    sheet_id: Attr[int]
    priority: Attr[int | None] = attr(type=Int32)
    tier: Attr[int | None] = attr(type=Int32)


class SheetDeposit(SheetRate, table="sheet_deposit", namespace=_NS, inheritance=ConcreteSubtype):
    grade: Attr[str | None] = attr(max_length=8)


class SheetLoan(SheetRate, table="sheet_loan", namespace=_NS, inheritance=ConcreteSubtype):
    spread: Attr[int | None] = attr(type=Int32)


class RateSheet(Bitemporal, table="rate_sheet", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)
    rates: Rel[tuple[SheetRate, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "sheet_id"))
    ranked_rates: Rel[tuple[SheetRate, ...]] = rel(
        cardinality=ONE_TO_MANY,
        join=("id", "sheet_id"),
        order_by=(desc("priority"), "tier", "id"),
    )


RATE_SHEET_DOCUMENT_MODEL = DomainModel(RateSheet, SheetRate, SheetDeposit, SheetLoan)
