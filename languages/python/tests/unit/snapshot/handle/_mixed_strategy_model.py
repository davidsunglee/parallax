"""One model whose two Entities resolve to DIFFERENT Effective Concurrency
Strategies under a single Concurrency Preference.

``Consignment`` declares an optimistic-lock version and ``ConsignmentLeg`` does
not, so under the default `optimistic` preference the root participates
optimistically while the included Entity takes the mandatory Locking fallback
(`m-unit-work` "Strategy selection"). No corpus model pairs a versioned root
with an unversioned relationship target, which is why the per-level derivation
is proven here rather than as a compatibility case.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from decimal import Decimal

from parallax.core import ONE_TO_MANY, Attr, DomainModel, Entity, Rel, attr, rel

__all__ = ["MIXED_STRATEGY_MODEL", "Consignment", "ConsignmentLeg"]

_NAMESPACE = "parallax.compatibility"


class ConsignmentLeg(Entity, table="consignment_leg", namespace=_NAMESPACE):
    """The included Entity, declaring no version source at all.

    Its family supplies no gate, so every strategy derivation lands on Locking
    for it and a participating read of one always takes the shared row lock.
    """

    id: Attr[int] = attr(primary_key=True)
    consignment_id: Attr[int]
    carrier: Attr[str]


class Consignment(Entity, table="consignment", namespace=_NAMESPACE):
    """The queried root, declaring an explicit optimistic-lock version.

    Its family supplies a gate, so the default preference resolves it to
    Optimistic and a participating read of one takes no lock.
    """

    id: Attr[int] = attr(primary_key=True)
    total: Attr[Decimal] = attr(precision=18, scale=2)
    version: Attr[int] = attr(optimistic_locking=True)
    legs: Rel[tuple[ConsignmentLeg, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "consignment_id")
    )


MIXED_STRATEGY_MODEL = DomainModel(Consignment, ConsignmentLeg)
