"""Docker-free proof that the deferral inventory and the claim do not overlap.

``_DEFERRED_EXECUTION_FEATURES`` records Features whose execution this
implementation has staged, and the active Conformance Slice records what it
claims to implement. The two must be disjoint: a Feature the claim covers but
the code defers would make every case exercising it fail at the read gate rather
than be honestly unclaimed, and listing it here is exactly the move
``docs/adr/0009`` forbids ("a Feature already claimed by the active slice but
missing in code is a defect and cannot be listed").

This is the compatibility lane's question rather than a unit one because the
claim's reach is a property of the CORPUS: a Feature is claimed by being carried
on a case the slice selects, so the check walks the cases the Python adapter
actually reaches.

Pure, Docker-free, in-process behaviour, so it classifies ``dbfree`` and
contributes to the database-free branch-coverage gate even though the rest of
``tests/compatibility/`` needs a database.
"""

from __future__ import annotations

from parallax.conformance import case_format, sweep
from parallax.conformance.claim import SNAPSHOT_CLAIM
from parallax.snapshot.handle._features import (
    _DEFERRED_EXECUTION_FEATURES,  # pyright: ignore[reportPrivateUsage] - the inventory is package-private on purpose; nothing but this proof reads it
)

_REACHABLE = sweep.reachable_cases()


def test_the_inventory_is_nonempty_free_form_feature_tags() -> None:
    # A module is claimed or not claimed wholesale, so a deferral is always a
    # free-form Feature tag rather than a reserved `m-` module tag. An empty
    # inventory is the expected END state and would make every assertion below
    # vacuous, so it is called out rather than passed silently.
    assert _DEFERRED_EXECUTION_FEATURES, "the inventory is empty: delete this lane with it"
    assert not any(case_format.is_module_tag(tag) for tag in _DEFERRED_EXECUTION_FEATURES)


def test_no_claimed_module_or_case_tag_names_a_deferred_feature() -> None:
    claimed = frozenset(SNAPSHOT_CLAIM.modules) | frozenset(SNAPSHOT_CLAIM.include)
    assert not claimed & _DEFERRED_EXECUTION_FEATURES


def test_no_case_the_python_slice_reaches_requires_a_deferred_feature() -> None:
    # The real check: reachability is the claim applied to the corpus, so a
    # deferred Feature tag on any case in this set would be claimed as
    # implemented and refused at execution.
    overlapping = {
        case.case_id: sorted(frozenset(case.tags) & _DEFERRED_EXECUTION_FEATURES)
        for case in _REACHABLE
        if frozenset(case.tags) & _DEFERRED_EXECUTION_FEATURES
    }
    assert not overlapping, f"claimed cases require deferred Features: {overlapping}"
