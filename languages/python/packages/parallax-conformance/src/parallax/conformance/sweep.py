from __future__ import annotations

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim

__all__ = ["reachable_cases"]


def reachable_cases(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """Return the cases ``claim``'s active slice selects."""
    corpus = cases if cases is not None else case_format.load_cases()
    flt = case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.excluded_tags),
    )
    return case_format.select(corpus, flt)
