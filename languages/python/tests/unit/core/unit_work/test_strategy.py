"""The Concurrency Preference vocabulary and its owner-provided validator
(`m-unit-work` "Strategy selection"): what the closed two-valued vocabulary
admits, how it refuses everything else, and what an accepted value comes back
as; and the audit port's neutral default.
"""

from __future__ import annotations

import pytest

from parallax.core.metamodel import AttributeIdentity
from parallax.core.unit_work import NO_AUDIT, concurrency_preference
from parallax.core.unit_work.strategy import CONCURRENCY_PREFERENCES, AuditStrategy
from parallax.core.write_plan import PlannedInsert
from parallax.core.write_plan.steps import NEW_LINEAGE, InsertEntry, PlannedRow
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of


class _UnhashableName(str):
    """A ``str`` no set can be asked about, so the validator is proved to compare."""

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_two_preferences() -> None:
    assert set(CONCURRENCY_PREFERENCES) == {"locking", "optimistic"}


@pytest.mark.parametrize("preference", sorted(CONCURRENCY_PREFERENCES))
def test_every_preference_of_the_vocabulary_is_returned_unchanged(preference: str) -> None:
    assert concurrency_preference(preference) == preference


@pytest.mark.parametrize(
    "value",
    [
        "pessimistic",
        "LOCKING",
        "",
        None,
        True,
        3,
        [],
        {"concurrency": "locking"},
        _UnhashableName("bogus"),
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"concurrency must be one of \['locking', 'optimistic'\]"):
        concurrency_preference(value)


def test_an_accepted_preference_comes_back_as_a_plain_hashable_str() -> None:
    preference = concurrency_preference(_UnhashableName("locking"))

    assert preference == "locking"
    assert {preference: "keyable"}


def test_the_audit_port_decorates_nothing_by_default() -> None:
    # Pipeline stage 8 exists as a seam from the start, so provenance decoration
    # becomes a change of injected adapter rather than a change of interface.
    # The default hands the step itself back rather than an equal rebuild, which
    # is what makes the seam cost nothing while nothing is wired behind it.
    account = entity_of(corpus_model("account"), "Account").identity
    row = PlannedRow(attributes={AttributeIdentity(account, "id"): 1})
    step = PlannedInsert(entity=account, entries=(InsertEntry(row=row, origin=NEW_LINEAGE),))
    decorated = NO_AUDIT.decorate(
        step, actor_identity=TEST_ACTOR_IDENTITY, transaction_instant=inert_instant()
    )
    assert decorated is step
    assert isinstance(NO_AUDIT, AuditStrategy)
