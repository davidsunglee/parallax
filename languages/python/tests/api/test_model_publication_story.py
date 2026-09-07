"""The host-owned model update against real Postgres (python.md §2,
m-api-conformance).

The Docker-free half runs the same story over a fake port, where a schema
statement is a string a double accepted. What only a real database can show is
that the three steps are one working order: the delta the generator wrote
actually carries the schema, the edition published over it actually serves, and
the added member is a column a later-edition write commits into and an
earlier-edition read never selects.

The publication story is the Usage Guide's own source, executed here so the
documented spelling of an update cannot drift from a working one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from parallax.conformance import model_publication_stories as stories
from parallax.conformance import provision
from parallax.conformance.story_models import (
    ACCOUNT_MODEL,
    NICKNAMED_ACCOUNT_MODEL,
    Account,
    NicknamedAccount,
)
from parallax.core.entity import model_of
from parallax.evolution import evolve, schema_delta
from parallax.snapshot import (
    PublicationConflictError,
    ServingModel,
    connect,
    prepare_model,
)

_TARGET_ID = 2


def _seeded(profile_run: Any) -> Any:
    profile_run.reset(model_of(ACCOUNT_MODEL), provision.load_fixtures("models/account.yaml"))
    return profile_run.port


def test_the_usage_guide_update_story_runs_against_a_real_database(profile_run: Any) -> None:
    update = stories.a_running_service_publishes_an_evolved_model_without_restarting(
        _seeded(profile_run)
    )
    # The rollout ledger the host keeps, empty because this evolution adds a
    # Column and no Index; what a database accepted, and what it then answers
    # with, is the whole of what this test grades. The statements themselves are
    # the schema-delta generator's own subject, never a golden string here.
    assert update.created_indices == ()
    # One handle across the whole update: the transaction before it adopted the
    # earlier selection and the one after it adopted the published one, with no
    # reconnection between them.
    assert update.before_edition == "2026-09-a"
    assert update.after_edition == "2026-09-b"
    assert update.nickname == "rainy-day"

    later = connect(profile_run.port, NICKNAMED_ACCOUNT_MODEL)
    named = later.find(NicknamedAccount.where(NicknamedAccount.id == _TARGET_ID)).result()
    # The write committed into the column the delta added, which is what makes
    # the publication an update rather than a relabelling.
    assert named.nickname == "rainy-day"

    # Edition Overlap: a connection still serving the earlier model reads the
    # same rows against the evolved schema, because an added Attribute is a
    # column that model never selects.
    earlier = connect(profile_run.port, ACCOUNT_MODEL)
    account = earlier.find(Account.where(Account.id == _TARGET_ID)).result()
    assert account.balance == Decimal("250.00")
    assert not hasattr(account, "nickname")


def test_a_stale_publisher_is_refused_and_rebases_onto_what_is_held(profile_run: Any) -> None:
    port = _seeded(profile_run)
    a = prepare_model(ACCOUNT_MODEL, edition="2026-09-a")
    serving = ServingModel(a)
    db = connect(port, serving)

    first = prepare_model(NICKNAMED_ACCOUNT_MODEL, edition="2026-09-b")
    evolution = stories.unilateral(evolve(model_of(a.model), model_of(first.model)))
    stories.apply_schema_delta(port, schema_delta(evolution, port.dialect))
    serving.publish(first, expected=a)

    # A second rollout controller still believing the earlier selection is
    # serving is refused rather than overwriting the winner, and `held` is what
    # it rebases onto — a second `current()` could already name a third.
    second = prepare_model(NICKNAMED_ACCOUNT_MODEL, edition="2026-09-c")
    with pytest.raises(PublicationConflictError) as refused:
        serving.publish(second, expected=a)
    assert refused.value.expected is a
    assert refused.value.held is first
    assert db.transact(lambda tx: tx.edition) == "2026-09-b"

    serving.publish(second, expected=refused.value.held)
    assert db.transact(lambda tx: tx.edition) == "2026-09-c"
