from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

from parallax.core._execution._options import OMITTED, Omitted, TxnOptions
from parallax.core._execution._planning import prepare_model
from parallax.core._execution._publication import ServingModel
from parallax.core._execution._root import DatabaseRoot
from parallax.core._execution._routing import check_read_policy
from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._unit_work.clock import Clock
from parallax.core.auto_retry import RetryPolicy
from parallax.core.concurrency import ConcurrencyPreference
from parallax.core.db_port import DatabaseAdapter, DatabaseRuntime, IsolationLevel, RoutePolicy
from parallax.core.entity import DomainModel
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    check_read_plan_cache_capacity,
)
from parallax.snapshot._handle._errors import SnapshotConnectionError
from parallax.snapshot._handle._read import Snapshot, typed_publication_for
from parallax.snapshot._handle._stream import DEFAULT_BATCH_SIZE, SnapshotStream
from parallax.snapshot._handle._transaction import (
    ReadOnlyTxnContext,
    TxnContext,
    read_only_context_for,
    transaction_for,
)
from parallax.snapshot._handle._wire import WireDatabaseView

__all__ = ["Database", "ScopedDatabase", "connect"]


_CONNECT_REFUSAL = (
    "connect() takes a Domain Model — one composed from Entity Classes, or one a descriptor "
    "produced — or a ServingModel holding a prepared one "
    "(snapshot-class-backed-model-required); a bare accepted Metamodel is a form no "
    "application holds"
)

_CONSTRUCTOR_REFUSAL = (
    "a Database connects to a Domain Model — one composed from Entity Classes, or one a "
    "descriptor produced — or to a ServingModel holding a prepared one; a bare accepted "
    "Metamodel names no model a connection can serve (snapshot-class-backed-model-required)"
)


def served_model(model: DomainModel | ServingModel, refusal: str) -> ServingModel:
    """Return the Serving Model a root will own, preparing static models once."""
    if isinstance(model, ServingModel):
        return model
    if not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise SnapshotConnectionError(refusal)
    return ServingModel(prepare_model(model, edition=f"static-{uuid4().hex}"))


class ScopedDatabase:
    """An immutable, connectionless execution view with captured authority."""

    __slots__ = ("_execution",)

    _execution: ExecutionScope

    def __init__(self) -> None:
        raise TypeError("ScopedDatabase values are created by Database authority selection")

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ScopedDatabase is immutable")

    @classmethod
    def create(cls, execution: ExecutionScope) -> ScopedDatabase:
        scoped = object.__new__(cls)
        object.__setattr__(scoped, "_execution", execution)
        return scoped

    def with_options(
        self,
        *,
        retry: RetryPolicy | Omitted = OMITTED,
        concurrency: ConcurrencyPreference | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> ScopedDatabase:
        return self.create(
            self._execution.with_options(
                retry=retry,
                concurrency=concurrency,
                isolation=isolation,
            )
        )

    def with_routing(self, *, read_policy: RoutePolicy) -> ScopedDatabase:
        return self.create(self._execution.with_routing(read_policy=read_policy))

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        return cast(
            "Snapshot[S]",
            self._execution.read(
                query, convert_query=typed_read_query, build_publication=typed_publication_for
            ),
        )

    def stream[S](
        self, query: ObjectQuery[Any, S], *, batch_size: int = DEFAULT_BATCH_SIZE
    ) -> SnapshotStream[S]:
        return SnapshotStream(
            self._execution,
            query,
            batch_size,
            convert_query=typed_read_query,
            build_publication=typed_publication_for,
        )

    @property
    def wire(self) -> WireDatabaseView:
        return WireDatabaseView(self._execution)

    def transact[T](
        self,
        fn: Callable[[TxnContext], T],
        /,
        *,
        retry: RetryPolicy | Omitted = OMITTED,
        concurrency: ConcurrencyPreference | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> T:
        return self._execution.transact(
            fn,
            transaction_for,
            retry=retry,
            concurrency=concurrency,
            isolation=isolation,
        )

    def read_only[T](
        self,
        fn: Callable[[ReadOnlyTxnContext], T],
        /,
        *,
        retry: RetryPolicy | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> T:
        return self._execution.read_only(
            fn, read_only_context_for, retry=retry, isolation=isolation
        )


class Database[Authorization](DatabaseRoot[Authorization, ScopedDatabase]):
    """Owns a runtime; close it explicitly or use it as a context manager.

    Option and routing aliases and execution scopes share that runtime. Closing
    any root alias closes it for all of them; creating a scope acquires no
    connection.
    """

    __slots__ = ()

    def __init__(
        self,
        runtime: DatabaseRuntime[Authorization],
        model: DomainModel | ServingModel,
        *,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        super().__init__(
            runtime,
            served_model(model, _CONSTRUCTOR_REFUSAL),
            scope_for=ScopedDatabase.create,
            options=options,
            read_policy=read_policy,
            read_plan_cache_capacity=capacity,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
        )

    @classmethod
    def connect[Auth](
        cls,
        adapter: DatabaseAdapter[Auth],
        model: DomainModel | ServingModel,
        *,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database[Auth]:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        serving = served_model(model, _CONNECT_REFUSAL)
        defaults = options if options is not None else TxnOptions()
        policy = check_read_policy(read_policy)
        runtime = adapter.open()
        try:
            return Database(
                runtime,
                serving,
                options=defaults,
                read_policy=policy,
                read_plan_cache_capacity=capacity,
                clock=clock,
                lifecycle_provider=lifecycle_provider,
            )
        except BaseException:
            runtime.close()
            raise


connect = Database.connect
