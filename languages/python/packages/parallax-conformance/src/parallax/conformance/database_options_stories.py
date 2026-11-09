from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core import UsageError
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.execution import (
    TRANSACTION_OPTION_CONFLICT,
    AdaptiveBackoff,
    RetryPolicy,
    TxnOptions,
)
from parallax.snapshot import TxnContext, connect

__all__ = [
    "ResolvedOptions",
    "ResolvedRetryPolicies",
    "a_root_default_is_overridden_per_call_and_a_join_inherits_the_override",
    "a_tuned_retry_policy_is_inherited_until_a_call_replaces_it_whole",
    "retry_policy_snippet",
    "root_options_snippet",
]

_TARGET_ID = 2


@dataclass(frozen=True, slots=True)
class ResolvedOptions:
    """What each transaction of the story ran under, read off ``tx.options``."""

    inherited: TxnOptions
    overridden: TxnOptions
    joined: TxnOptions
    repeated: TxnOptions
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
    root = TxnOptions(isolation="repeatable_read", retry=RetryPolicy(max_retries=2))
    with connect(adapter, model, options=root) as database:
        db = database.using_database_login()
        inherited = db.transact(lambda tx: tx.options)

        def outer(tx: TxnContext) -> ResolvedOptions:
            account = tx.find(Account.where(Account.id == _TARGET_ID)).result()

            def joined_body(joined_tx: TxnContext) -> TxnOptions:
                return joined_tx.options

            joined = db.transact(joined_body)
            repeated = db.transact(joined_body, isolation="serializable")
            refused = False
            try:
                db.transact(joined_body, isolation="repeatable_read")
            except UsageError as refusal:
                if refusal.code != TRANSACTION_OPTION_CONFLICT:
                    raise
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


@dataclass(frozen=True, slots=True)
class ResolvedRetryPolicies:
    """The Retry Policy each transaction of the story ran under."""

    inherited: RetryPolicy
    replaced: RetryPolicy
    equal_policy_joined: RetryPolicy
    other_backoff_refused_on_join: bool


def a_tuned_retry_policy_is_inherited_until_a_call_replaces_it_whole(
    adapter: DatabaseAdapter, model: DomainModel
) -> ResolvedRetryPolicies:
    """A root tuned once, a call that replaces the whole policy, and a joining
    call compared with the policy of the transaction it joins.

    A policy is one value. Naming ``max_retries`` alone leaves nothing of the
    root's backoff in force: the fields a policy omits take their built-in
    values, never the inherited ones. A joining call may repeat a policy equal
    to the active one; the same bound with another backoff is a different policy.
    """
    tuned = RetryPolicy(max_retries=3, backoff=AdaptiveBackoff(base_delay=0.002, max_delay=0.05))
    with connect(adapter, model, options=TxnOptions(retry=tuned)) as database:
        db = database.using_database_login()
        inherited = db.transact(lambda tx: tx.options.retry)

        def outer(tx: TxnContext) -> ResolvedRetryPolicies:
            def joined_body(joined_tx: TxnContext) -> RetryPolicy:
                return joined_tx.options.retry

            equal = db.transact(joined_body, retry=RetryPolicy(max_retries=1))
            refused = False
            try:
                db.transact(joined_body, retry=RetryPolicy(max_retries=1, backoff=tuned.backoff))
            except UsageError as refusal:
                if refusal.code != TRANSACTION_OPTION_CONFLICT:
                    raise
                refused = True
            return ResolvedRetryPolicies(
                inherited=inherited,
                replaced=tx.options.retry,
                equal_policy_joined=equal,
                other_backoff_refused_on_join=refused,
            )

        return db.transact(outer, retry=RetryPolicy(max_retries=1))


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


def retry_policy_snippet() -> str:
    """The Retry Policy story's own source, with the record it answers."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            ResolvedRetryPolicies,
            a_tuned_retry_policy_is_inherited_until_a_call_replaces_it_whole,
        )
    )
