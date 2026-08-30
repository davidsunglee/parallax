"""The one place a Scenario position is added to a failure.

Every module a step's grading reaches — this package's own phases, write grading,
the Object Query oracle — speaks of the thing it was handed rather than of the
Scenario position that handed it over. The position is added here, once, at the
boundary that knows it.

The oracle names its own steps under the same rule and holds a live caller of its
own, so the boundary itself is shared assertion vocabulary
(:mod:`..case_assertions`) and this module is where the package names it.
"""

from __future__ import annotations

from ..case_assertions import reported_against

__all__ = ["reported_against"]
