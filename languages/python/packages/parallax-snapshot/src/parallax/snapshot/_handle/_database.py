from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final, NoReturn, cast, overload
from uuid import uuid4

from parallax.core._execution._options import OMITTED, Omitted, TxnOptions
from parallax.core._execution._planning import prepare_model
from parallax.core._execution._publication import ServingModel, read_projection
from parallax.core._execution._root import DatabaseRoot
from parallax.core._execution._routing import check_read_policy
from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._unit_work.clock import Clock
from parallax.core.execution_lifecycle._activity import ExecutionLifecycleProvider
from parallax.core.internal.auto_retry import RetryPolicy
from parallax.core.internal.base import UsageError
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.database_binding import REQUIRED, DatabaseBinding, require_binding
from parallax.core.internal.db_port import (
    DatabaseAdapter,
    DatabaseRuntime,
    IsolationLevel,
    RoutePolicy,
)
from parallax.core.internal.dialect import Dialect
from parallax.core.internal.entity import DomainModel
from parallax.core.internal.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.internal.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    check_read_plan_cache_capacity,
)
from parallax.snapshot._handle._errors import SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED
from parallax.snapshot._handle._read import (
    SharingScope,
    Snapshot,
    typed_publication_builder,
)
from parallax.snapshot._handle._stream import DEFAULT_BATCH_SIZE, SnapshotStream
from parallax.snapshot._handle._transaction import (
    ReadOnlyTxnContext,
    TxnContext,
    read_only_context_for,
    transaction_for,
)
from parallax.snapshot._handle._wire import WireDatabaseView

__all__ = [
    "CONNECT_BACKEND_MISMATCH",
    "CONNECT_BINDING_UNEXPECTED",
    "Database",
    "ScopedDatabase",
    "connect",
]

CONNECT_BACKEND_MISMATCH: Final = "connect-backend-mismatch"
"""A model's binding names another backend than the adapter it connects through."""

CONNECT_BINDING_UNEXPECTED: Final = "connect-binding-unexpected"
"""A binding accompanied a ServingModel, whose selections already carry theirs."""


_CONNECT_REFUSAL = (
    "connect() takes a Domain Model — one composed from Entity Classes, or one a descriptor "
    "produced — or a ServingModel holding a prepared one; a bare accepted Metamodel is a "
    "form no application holds"
)

_CONSTRUCTOR_REFUSAL = (
    "a Database connects to a Domain Model — one composed from Entity Classes, or one a "
    "descriptor produced — or to a ServingModel holding a prepared one; a bare accepted "
    "Metamodel names no model a connection can serve"
)


def served_model(
    model: DomainModel | ServingModel, binding: object, dialect: Dialect, refusal: str
) -> ServingModel:
    """Return the Serving Model a root will own, preparing a static model once
    under ``binding``.

    A Serving Model takes no binding, since each selection it holds carries its
    own; either way the served backend must be ``dialect``. Every refusal comes
    before anything opens.
    """
    if isinstance(model, ServingModel):
        if binding is not REQUIRED:
            raise UsageError(
                CONNECT_BINDING_UNEXPECTED,
                "a ServingModel's selections carry their own binding; connect it without binding=",
            )
        serving = model
    elif not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise UsageError(SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED, refusal)
    else:
        placement = require_binding(binding, "connect")
        _check_backend(placement.dialect, dialect)
        return ServingModel(
            prepare_model(model, binding=placement, edition=f"static-{uuid4().hex}")
        )
    _check_backend(read_projection(serving.current()).model.resolved.dialect, dialect)
    return serving


def _check_backend(served: Dialect, connected: Dialect) -> None:
    if served.name != connected.name:
        raise UsageError(
            CONNECT_BACKEND_MISMATCH,
            f"the model is bound for {served.name!r}, but the adapter connects to "
            f"{connected.name!r}",
        )


class ScopedDatabase:
    """A database view bound to a principal's authority; it holds no connection."""

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

    def find[S](
        self, query: ObjectQuery[Any, S], *, sharing_scope: SharingScope = "root"
    ) -> Snapshot[S]:
        return cast(
            "Snapshot[S]",
            self._execution.read(
                query,
                convert_query=typed_read_query,
                build_publication=typed_publication_builder(sharing_scope),
            ),
        )

    def stream[S](
        self,
        query: ObjectQuery[Any, S],
        *,
        batch_size: int = DEFAULT_BATCH_SIZE,
        sharing_scope: SharingScope = "root",
    ) -> SnapshotStream[S]:
        return SnapshotStream(
            self._execution,
            query,
            batch_size,
            convert_query=typed_read_query,
            build_publication=typed_publication_builder(sharing_scope),
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
    """A connected database; close it, or use it as a context manager.

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
        binding: DatabaseBinding | None = None,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        super().__init__(
            runtime,
            served_model(
                model,
                REQUIRED if binding is None else binding,
                runtime.dialect,
                _CONSTRUCTOR_REFUSAL,
            ),
            scope_for=ScopedDatabase.create,
            options=options,
            read_policy=read_policy,
            read_plan_cache_capacity=capacity,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
        )

    @overload
    @classmethod
    def connect[Auth](
        cls,
        adapter: DatabaseAdapter[Auth],
        model: DomainModel,
        *,
        binding: DatabaseBinding,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database[Auth]: ...

    @overload
    @classmethod
    def connect[Auth](
        cls,
        adapter: DatabaseAdapter[Auth],
        model: ServingModel,
        *,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database[Auth]: ...

    @overload
    @classmethod
    def connect[Auth](
        cls,
        adapter: DatabaseAdapter[Auth],
        model: DomainModel,
        *,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> NoReturn: ...

    @classmethod
    def connect[Auth](
        cls,
        adapter: DatabaseAdapter[Auth],
        model: DomainModel | ServingModel,
        *,
        binding: object = REQUIRED,
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> Database[Auth]:
        """Open a root over ``adapter`` serving ``model``.

        A Domain Model is prepared once under the required ``binding``; a
        ServingModel takes none. Either way the served backend must be the
        adapter's, and every refusal comes before ``adapter.open()``.
        """
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        serving = served_model(model, binding, adapter.dialect, _CONNECT_REFUSAL)
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
"""Open a `Database` over an adapter and a model; the same as `Database.connect`."""
