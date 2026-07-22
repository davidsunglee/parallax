"""Select the corpus cases reachable by the compile and run sweeps.

Selection is derived at runtime from the active slice and
:data:`IMPLEMENTED_MODULES`; a case is reachable only when every module tag it
declares is implemented. This keeps sweep coverage aligned with the module DAG
without hard-coded case counts. The selected modules cover descriptor and
operation processing, SQL and database execution, inheritance and graph
materialization, writes, temporal behavior, locking, retries, and concurrency.
Cases that need run-only state or multi-session choreography remain reachable
and are routed to their specialized runners by case shape.
"""

from __future__ import annotations

from typing import Final

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim

__all__ = ["IMPLEMENTED_MODULES", "reachable_cases"]

# A case is reachable only when all of its module tags occur in this set. The
# always-on intersection prevents partially implemented compositions from
# entering a compile or run sweep.
IMPLEMENTED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "m-core",
        "m-case-format",
        "m-conformance-adapter",
        "m-descriptor",
        "m-pk-gen",
        "m-inheritance",
        "m-metamodel",
        "m-model-formation",
        "m-value-object",
        "m-relationship",
        "m-op-algebra",
        "m-dialect",
        "m-db-port",
        "m-db-error",
        "m-sql",
        "m-temporal-read",
        "m-api-conformance",
        "m-unit-work",
        "m-navigate",
        "m-deep-fetch",
        "m-snapshot-read",
        "m-opt-lock",
        "m-txtime-write",
        "m-bitemp-write",
        "m-read-lock",
        "m-auto-retry",
        # `m-batch-write-004` tags both `m-batch-write` and `m-opt-lock`, so the
        # reachability intersection requires both. Buffered-batch cases use
        # `lower_write`'s multi-row collapse, while predicate-selected cases
        # use the readless predicate-write path.
        "m-batch-write",
    }
)


def reachable_cases(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """Return active-slice cases whose module tags are all implemented."""
    corpus = cases if cases is not None else case_format.load_cases()
    flt = case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.exclude),
    )
    return case_format.select(corpus, flt, implemented_modules=IMPLEMENTED_MODULES)
