from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

from parallax.core.db_port import DatabaseAdapter, DatabaseRuntime, IsolationLevel
from parallax.core.entity import DomainModel
from parallax.core.execution import DatabaseOptions, ServingModel, prepare_model
from parallax.core.execution._options import OMITTED, Omitted
from parallax.core.execution._root import DatabaseRoot
from parallax.core.execution._scope import ExecutionScope
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.read_delivery import RowsResult
from parallax.core.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    check_read_plan_cache_capacity,
)
from parallax.core.unit_work import Clock, Concurrency
from parallax.snapshot._handle._errors import SnapshotConnectionError
from parallax.snapshot._handle._read import Snapshot, typed_publication_for
from parallax.snapshot._handle._stream import SnapshotStream
from parallax.snapshot._handle._transaction import Transaction, transaction_for
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
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> ScopedDatabase:
        return self.create(
            self._execution.with_options(
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            )
        )

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        return cast(
            "Snapshot[S]",
            self._execution.read(
                query, convert_query=object_query_node, build_publication=typed_publication_for
            ),
        )

    def stream[S](self, query: ObjectQuery[Any, S], *, batch_size: int = 1000) -> SnapshotStream[S]:
        return SnapshotStream(
            self._execution,
            query,
            batch_size,
            convert_query=object_query_node,
            build_publication=typed_publication_for,
        )

    @property
    def wire(self) -> WireDatabaseView:
        return WireDatabaseView(self._execution)

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        return self._execution.read_rows(query)

    def transact[T](
        self,
        fn: Callable[[Transaction], T],
        /,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> T:
        return self._execution.transact(
            fn,
            transaction_for,
            max_retries=max_retries,
            concurrency=concurrency,
            retry_optimistic_conflicts=retry_optimistic_conflicts,
            isolation=isolation,
        )


class Database[Authorization](DatabaseRoot[Authorization, ScopedDatabase]):
    """Owns a runtime; close it explicitly or use it as a context manager.

    Option aliases and execution scopes share that runtime. Closing any root
    alias closes it for all of them; creating a scope acquires no connection.
    """

    __slots__ = ()

    def __init__(
        self,
        runtime: DatabaseRuntime[Authorization],
        model: DomainModel | ServingModel,
        *,
        options: DatabaseOptions | None = None,
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
        options: DatabaseOptions | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database[Auth]:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        serving = served_model(model, _CONNECT_REFUSAL)
        defaults = options if options is not None else DatabaseOptions()
        runtime = adapter.open()
        try:
            return Database(
                runtime,
                serving,
                options=defaults,
                read_plan_cache_capacity=capacity,
                clock=clock,
                lifecycle_provider=lifecycle_provider,
            )
        except BaseException:
            runtime.close()
            raise


connect = Database.connect
