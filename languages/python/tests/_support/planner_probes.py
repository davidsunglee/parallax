"""Write Planner probes for suites that drive the unit-of-work shell or the
write-lowering seam directly, without a full ``Database``.

:func:`planner_for` builds the SAME production-wired planner
``parallax.snapshot.handle.build_write_planner`` does, rather than a parallel
fake: several of these suites pin the planner's own settling behavior, so a
fake strategy set would test something other than what ships.
"""

from __future__ import annotations

from typing import Final

from parallax.core.metamodel import Metamodel
from parallax.core.unit_work import SubjectIdentity, WritePlanner
from parallax.snapshot.handle import build_write_planner

__all__ = ["TEST_SUBJECT_IDENTITY", "planner_for"]

# An arbitrary nonempty Subject Identity: `m-unit-work` requires one on every
# Planning Request and guarantees it is never inspected, so any value serves
# every suite here identically.
TEST_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity("test-subject")


def planner_for(model: Metamodel) -> WritePlanner:
    """A production-wired ``WritePlanner`` for ``model``."""
    return build_write_planner(model)
