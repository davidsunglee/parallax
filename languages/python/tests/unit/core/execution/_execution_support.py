"""A Database Root whose scope and transaction factories answer the neutral
objects themselves, over a scripted port."""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

from parallax.conformance.class_models import MODELS
from parallax.conformance.scripted_clock import FixedClock
from parallax.core.db_port import DatabaseAdapter
from parallax.core.entity import DomainModel
from parallax.core.entity._model import model_of
from parallax.core.execution import DatabaseOptions, ServingModel, prepare_model
from parallax.core.execution._root import DatabaseRoot
from parallax.core.execution._scope import ExecutionScope
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.unit_work import KeyedWrite
from parallax.core.unit_work.instructions import PreparedKeyedWrite, prepare_typed_write
from tests._support.root_ownership import own_root

ACCOUNT: Final = MODELS["account"]
FIXED: Final = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def itself[T](value: T, /) -> T:
    """The scope and transaction factory that answers the neutral object itself."""
    return value


def root(
    adapter: DatabaseAdapter[Any],
    model: DomainModel | ServingModel = ACCOUNT,
    *,
    options: DatabaseOptions | None = None,
    provider: ExecutionLifecycleProvider | None = None,
) -> DatabaseRoot[Any, ExecutionScope]:
    """A root over ``adapter`` the current test owns, serving ``model``."""
    serving = (
        model
        if isinstance(model, ServingModel)
        else ServingModel(prepare_model(model, edition="test"))
    )
    return own_root(
        DatabaseRoot(
            adapter.open(),
            serving,
            scope_for=itself,
            options=options,
            clock=FixedClock(FIXED),
            lifecycle_provider=provider,
        )
    )


def scope(
    adapter: DatabaseAdapter[Any],
    model: DomainModel | ServingModel = ACCOUNT,
    *,
    options: DatabaseOptions | None = None,
    provider: ExecutionLifecycleProvider | None = None,
) -> ExecutionScope:
    """The database-login scope of a fresh owned root."""
    return root(adapter, model, options=options, provider=provider).using_database_login()


def account_insert(account_id: int = 7) -> PreparedKeyedWrite:
    """One prepared Account insert, buffered by a case straight into a unit of work."""
    prepared = prepare_typed_write(
        KeyedWrite(
            "insert",
            "Account",
            ({"id": account_id, "owner": "Newton", "balance": 5},),
        ),
        model_of(ACCOUNT),
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    return prepared
