"""A shared Subject Identity for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``.
"""

from __future__ import annotations

from typing import Final

from parallax.core.unit_work import SubjectIdentity

__all__ = ["TEST_SUBJECT_IDENTITY"]

# An arbitrary nonempty Subject Identity: `m-unit-work` requires one on every
# Planning Request and guarantees it is never inspected, so any value serves
# every suite here identically.
TEST_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity("test-subject")
