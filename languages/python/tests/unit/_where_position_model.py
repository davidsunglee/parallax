"""The `_where`-verb materialization suites' local Bitemporal Entity.

`models/position.yaml` has a shared mirror (`parallax.conformance.story_models.Position`),
but it is not a drop-in: it maps to table `position` with columns `pos_id`/`val`,
while the suites using this one pin emitted SQL against `where_position`/`id`/`value`.
"""

from __future__ import annotations

from decimal import Decimal

from parallax.core import Attr, Bitemporal, DomainModel, attr

__all__ = ["WHERE_POSITION_META", "WherePosition"]


class WherePosition(Bitemporal, table="where_position", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(precision=18, scale=2)


WHERE_POSITION_META = DomainModel(WherePosition)
