"""Database-free proof for the scoped execution-authority guide story."""

from decimal import Decimal

from parallax.conformance import execution_authority_stories as stories
from parallax.conformance.story_models import ACCOUNT_MODEL
from parallax.snapshot import DatabaseOptions
from tests._support.db_port import Read, ScriptedAdapter, Transact

_ROW = {"id": 2, "owner": "Bob", "balance": Decimal("250.00"), "version": 1}


# The guide story must execute one login-authority read and one principal-authority
# transaction from independently captured scopes on the same owned root. Equal
# principal captures join the outer transaction, while the derived serializable
# option combines with the root retry default and both reads observe the same row.
def test_the_scoped_authority_guide_story_runs_without_a_database() -> None:
    with ScriptedAdapter(Read(rows=[_ROW]), Transact(Read(rows=[_ROW]))) as adapter:
        shape = stories.scopes_capture_authority_and_share_the_root_lifetime(
            adapter,
            ACCOUNT_MODEL,
            object(),
        )

    assert shape == stories.ScopedAuthorityShape(
        login_balance=Decimal("250.00"),
        principal_balance=Decimal("250.00"),
        joined_same_transaction=True,
        options=DatabaseOptions(max_retries=1, isolation="serializable"),
    )
    assert adapter.closes == 1
