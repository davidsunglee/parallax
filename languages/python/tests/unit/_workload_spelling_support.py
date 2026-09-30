"""What more than one cost workload family spells the same way: the prefix each
Snapshot delivery family's workload ids begin with, and the value of a geometry
leaf.

Every family's support module builds its models when it runs, so these live
apart from all of them and build nothing: a reading child routes an address to
its family before running that family's module, and the leaf-type family values
its String control as the geometry families value their leaves without building
the geometry models.

Never imported by production code.
"""

from __future__ import annotations

from typing import Final

__all__ = ["CONTROL_PREFIX", "GEOMETRY_PREFIX", "LEAF_PREFIX", "PLAN_PREFIX", "leaf_value"]

GEOMETRY_PREFIX: Final = "read-"
PLAN_PREFIX: Final = "plan-"
LEAF_PREFIX: Final = "leaf-"
CONTROL_PREFIX: Final = "control-"


def leaf_value(index: int, key: int) -> str:
    """Leaf ``index`` of the occurrence keyed ``key``, fixed-width so two
    values of one level weigh the same."""
    return f"{index:03d}-{key:08d}"
