"""Executable API-suite story for scoped execution authority."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.snapshot import DatabaseOptions, connect
from parallax.snapshot.handle import Transaction

__all__ = [
    "AuthorityPrincipal",
    "ScopedAuthorityShape",
    "scoped_authority_snippet",
    "scopes_capture_authority_and_share_the_root_lifetime",
]

_TARGET_ID = 2


@dataclass(frozen=True, slots=True)
class AuthorityPrincipal[Authorization]:
    """An application Principal paired with the provider's authorization type."""

    subject: str
    database_authorization: Authorization


@dataclass(frozen=True, slots=True)
class ScopedAuthorityShape:
    """What the two authority modes and an independently captured join observed."""

    login_balance: Decimal
    principal_balance: Decimal
    joined_same_transaction: bool
    options: DatabaseOptions


def scopes_capture_authority_and_share_the_root_lifetime[Authorization](
    adapter: DatabaseAdapter[Authorization],
    model: DomainModel,
    authorization: Authorization,
) -> ScopedAuthorityShape:
    """Select both authority modes from one explicitly owned Database Root.

    The root context owns and closes the runtime. Its scopes are immutable,
    connectionless views: the login scope captures the runtime's authenticated
    identity, while each principal scope captures the application's subject and
    provider authorization once. Options derive a new scope without changing
    that capture. Two independently selected equal principal scopes can join
    because execution authority compares by value within the same root.
    """
    defaults = DatabaseOptions(max_retries=1)
    with connect(adapter, model, options=defaults) as root:
        login = root.using_database_login()
        principal_value = AuthorityPrincipal("authority-guide", authorization)
        principal = root.using_principal(principal_value).with_options(isolation="serializable")
        independently_captured = root.using_principal(principal_value)

        login_balance = login.find(Account.where(Account.id == _TARGET_ID)).result().balance

        def outer(tx: Transaction) -> tuple[Decimal, bool, DatabaseOptions]:
            account = tx.find(Account.where(Account.id == _TARGET_ID)).result()
            joined = independently_captured.transact(lambda joined_tx: joined_tx is tx)
            return account.balance, joined, tx.options

        principal_balance, joined_same_transaction, options = principal.transact(outer)

    return ScopedAuthorityShape(
        login_balance=login_balance,
        principal_balance=principal_balance,
        joined_same_transaction=joined_same_transaction,
        options=options,
    )


def scoped_authority_snippet() -> str:
    """Render the exact public story executed by the API suite."""
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            AuthorityPrincipal,
            ScopedAuthorityShape,
            scopes_capture_authority_and_share_the_root_lifetime,
        )
    )
