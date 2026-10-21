"""Parsed corpus shared within a test process; callers own their documents."""

from __future__ import annotations

import copy
import functools

from parallax.conformance import case_format, sweep


@functools.cache
def _by_id() -> dict[str, case_format.Case]:
    index: dict[str, case_format.Case] = {}
    for case in case_format.load_cases():
        previous = index.setdefault(case.case_id, case)
        if previous is not case:
            raise ValueError(
                f"case id {case.case_id!r} is claimed by both "
                f"{previous.path.name} and {case.path.name}"
            )
    return index


@functools.cache
def _reachable_ids() -> frozenset[str]:
    return frozenset(case.case_id for case in sweep.reachable_cases(cases=list(_by_id().values())))


def case(case_id: str, *, reachable: bool = False) -> case_format.Case:
    """Return a private copy, optionally requiring active-slice reachability."""
    if reachable and case_id not in _reachable_ids():
        raise KeyError(case_id)
    return copy.deepcopy(_by_id()[case_id])


def cases() -> list[case_format.Case]:
    return copy.deepcopy(list(_by_id().values()))


def reachable_cases() -> list[case_format.Case]:
    return copy.deepcopy(
        [case for case_id, case in _by_id().items() if case_id in _reachable_ids()]
    )
