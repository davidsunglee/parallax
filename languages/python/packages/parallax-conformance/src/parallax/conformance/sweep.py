"""The reachable corpus intersection for the compile / run sweeps.

The sweeps are parametrized from the corpus at runtime (never a hard-coded
count): the active slice intersected with the capability tags of the modules
already implemented, so a case joins a sweep exactly when every module it tags is
online. :data:`IMPLEMENTED_MODULES` grows one phase at a time — this is the COR-3
Phase 5 set (the read path across ``m-op-algebra`` / ``m-sql`` / ``m-dialect`` /
``m-db-port`` on top of the metamodel hub and the conformance spine).
"""

from __future__ import annotations

from typing import Final

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim

__all__ = ["IMPLEMENTED_MODULES", "reachable_cases"]

# The modules whose behaviour is implemented as of COR-3 Phase 6 (milestone 1). A
# reachable case is one whose module tags are ALL in this set (case_format's
# always-on reachable-intersection filter). Phase-6 milestone 1 adds `m-db-error`
# (neutral category classification + call-site predicates + the port-boundary
# re-raise); its corpus cases are all `error`-shape and become reachable but stay
# reasoned-skipped until error/concurrency-shape `run` support lands (the later
# Phase-6 case-instruction translation). Remaining Phase-6 modules (`m-unit-work`,
# `m-temporal-read`) and the snapshot/write modules append here as they land.
IMPLEMENTED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "m-core",
        "m-case-format",
        "m-conformance-adapter",
        "m-descriptor",
        "m-pk-gen",
        "m-inheritance",
        "m-value-object",
        "m-op-algebra",
        "m-dialect",
        "m-db-port",
        "m-db-error",
        "m-sql",
        "m-api-conformance",
    }
)


def reachable_cases(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """The active-slice cases whose module tags are all implemented (this phase)."""
    corpus = cases if cases is not None else case_format.load_cases()
    flt = case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.exclude),
    )
    return case_format.select(corpus, flt, implemented_modules=IMPLEMENTED_MODULES)
