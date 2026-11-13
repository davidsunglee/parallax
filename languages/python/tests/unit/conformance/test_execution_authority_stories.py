"""The scoped execution-authority guide story closes the root it opens."""

from decimal import Decimal

from parallax.conformance import execution_authority_stories as stories
from parallax.conformance.story_models import ACCOUNT_MODEL
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import Read, ScriptedAdapter, Transact

_ROW = {"id": 2, "owner": "Bob", "balance": Decimal("250.00"), "version": 1}


def test_the_scoped_authority_story_closes_the_runtime_it_opened() -> None:
    with ScriptedAdapter(Read(rows=[_ROW]), Transact(Read(rows=[_ROW]))) as adapter:
        stories.scopes_capture_authority_and_share_the_root_lifetime(
            adapter, ACCOUNT_MODEL, TEST_BINDING, object()
        )

    assert adapter.closes == 1
