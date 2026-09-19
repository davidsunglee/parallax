"""``parallax.conformance.database_options_stories`` — the executable API-suite
story for configuring transaction defaults on the Database Root and overriding
them per call (`m-unit-work`, `m-auto-retry`, `m-db-port`; ADR 0065).

`m-unit-work-041`'s portable oracle states what a joining call is held to when
the outer call overrode the root, and the boundary runner grades it. What no
oracle can state is the SPELLING an application reaches that through: one
:class:`~parallax.snapshot.DatabaseOptions` record handed to ``connect``, a
sparse keyword on the one call that wants something else, and
``Transaction.options`` answering the resolved record inside the work — which
is the story here, executed against real Postgres by
``tests/api/test_database_options.py`` so the documented spelling cannot drift
from the executed one.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.snapshot import DatabaseOptions, connect
from parallax.snapshot.handle import Transaction, TransactionOptionConflictError

__all__ = [
    "ResolvedOptions",
    "a_root_default_is_overridden_per_call_and_a_join_inherits_the_override",
    "root_options_snippet",
]

_TARGET_ID = 2


@dataclass(frozen=True, slots=True)
class ResolvedOptions:
    """What each transaction of the story ran under, read off ``tx.options``."""

    inherited: DatabaseOptions
    overridden: DatabaseOptions
    joined: DatabaseOptions
    repeated: DatabaseOptions
    root_level_refused_on_join: bool
    balance: Decimal


def a_root_default_is_overridden_per_call_and_a_join_inherits_the_override(
    adapter: DatabaseAdapter, model: DomainModel
) -> ResolvedOptions:
    """A root configured once, a call that overrides one field, and a joining
    call held to the override rather than to the root.

    ``adapter`` is the shipped adapter's configuration for the story database,
    which holds the seeded account row the transactions read. The record handed
    to ``connect`` is every transaction's default; a keyword on ``transact`` is
    an explicit request for that one call, resolved over the record; and a
    joining call inherits what the ACTIVE transaction resolved — omitting a
    field inherits it, repeating the resolved value is accepted, and naming any
    other value, the root's own included, is refused before the joined body
    runs. Nothing is passed as ``None``: only an omitted keyword inherits.
    """
    root = DatabaseOptions(isolation="repeatable_read", max_retries=2)
    with connect(adapter, model, options=root) as database:
        db = database.using_database_login()
        inherited = db.transact(lambda tx: tx.options)

        def outer(tx: Transaction) -> ResolvedOptions:
            account = tx.find(Account.where(Account.id == _TARGET_ID)).result()

            def joined_body(joined_tx: Transaction) -> DatabaseOptions:
                return joined_tx.options

            joined = db.transact(joined_body)
            repeated = db.transact(joined_body, isolation="serializable")
            refused = False
            try:
                db.transact(joined_body, isolation="repeatable_read")
            except TransactionOptionConflictError:
                refused = True
            return ResolvedOptions(
                inherited=inherited,
                overridden=tx.options,
                joined=joined,
                repeated=repeated,
                root_level_refused_on_join=refused,
                balance=account.balance,
            )

        return db.transact(outer, isolation="serializable")


def root_options_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift.

    The record the story answers and the call are one story: a snippet showing
    the call alone would leave the reader to guess what it returns.
    """
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            ResolvedOptions,
            a_root_default_is_overridden_per_call_and_a_join_inherits_the_override,
        )
    )
