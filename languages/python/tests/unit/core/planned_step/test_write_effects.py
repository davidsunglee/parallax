"""What a write's success publishes (m-planned-step values).

An attempt that opened nothing owns nothing, and holds nothing for any source
to continue from.
"""

from __future__ import annotations

from parallax.core.internal.planned_step.keys import ObjectKey, VersionedObjectStateKey
from parallax.core.internal.planned_step.write_effects import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    TemporalRowCoordinates,
)
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ACCOUNT = entity_of(corpus_model("account"), "Account").identity


def test_an_attempt_that_opened_nothing_owns_nothing_an_insertion_opened() -> None:
    coordinates = TemporalRowCoordinates(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.owns(coordinates)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.continues_insertion(coordinates)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.insertion_coverage(coordinates, None) == ()


def test_an_attempt_that_opened_nothing_holds_nothing_for_a_source_to_continue() -> None:
    coordinates = TemporalRowCoordinates(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    target = ObjectKey(_ACCOUNT, (("id", 1),))
    state = VersionedObjectStateKey(target, 1)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.demanded(state, coordinates)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.continues(object(), None) is None
    assert tuple(NO_TEMPORAL_WRITE_OWNERSHIP.current_rows(target, None)) == ()
