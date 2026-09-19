"""Database-root composition and immutable scoped execution views."""

from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

from parallax.core.db_port import DatabaseAdapter, DatabaseRuntime, IsolationLevel
from parallax.core.entity import DomainModel, EntityGraphConstruction, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import class_index, model_of
from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
from parallax.core.execution_lifecycle._activity import (
    InstalledLifecycle,
    installed_lifecycle,
)
from parallax.core.execution_lifecycle._pool_observation import (
    PoolObservation,
    close_pool_observations,
    register_pool_observation,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query._fluent import ObjectQuery
from parallax.core.unit_work import Clock, Concurrency, SystemClock
from parallax.snapshot.handle._errors import SnapshotConnectionError
from parallax.snapshot.handle._execution_authority import (
    ExecutionCapture,
    Principal,
    capture_database_login,
    capture_principal,
)
from parallax.snapshot.handle._options import (
    OMITTED,
    DatabaseOptions,
    Omitted,
    patch_options,
)
from parallax.snapshot.handle._planning import build_write_planner
from parallax.snapshot.handle._publication import (
    ModelSelection,
    ServingModel,
    check_edition,
    select_model,
)
from parallax.snapshot.handle._read import RowsResult, Snapshot
from parallax.snapshot.handle._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    ReadPlanCache,
    check_read_plan_cache_capacity,
)
from parallax.snapshot.handle._read_scope import ReadScope, standalone_read_scope
from parallax.snapshot.handle._stream import SnapshotStream
from parallax.snapshot.handle._transaction import Transaction
from parallax.snapshot.handle._transaction_runner import TransactionRunner
from parallax.snapshot.handle._wire import WireDatabaseView

__all__ = ["Database", "ScopedDatabase", "connect", "prepare_model"]


def prepare_model(model: DomainModel, *, edition: str) -> ModelSelection:
    """Prepare one complete immutable model selection without database I/O."""
    check_edition(edition)
    if not isinstance(model, DomainModel):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError(
            f"prepare_model takes a Domain Model — one composed from Entity Classes, or one a "
            f"descriptor produced — not {model!r}"
        )
    catalog = CatalogedModel(model_of(model))
    classes = class_index(model)
    return select_model(
        model,
        edition=edition,
        catalog=catalog,
        construction=(None if classes is None else EntityGraphConstruction(catalog, classes)),
        codec=EntityRowCodec(catalog),
        planner=build_write_planner(catalog.meta),
    )


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


class _DatabaseResources[Authorization]:
    """The one shared resource owner behind every Database alias and scope."""

    __slots__ = (
        "clock",
        "lifecycle",
        "observation",
        "planner",
        "runtime",
        "serving",
        "shutdown",
        "transaction_runner",
    )

    def __init__(
        self,
        runtime: DatabaseRuntime[Authorization],
        serving: ServingModel,
        *,
        capacity: int,
        clock: Clock | None,
        lifecycle_provider: ExecutionLifecycleProvider | None,
    ) -> None:
        self.runtime = runtime
        self.serving = serving
        self.clock: Clock = clock if clock is not None else SystemClock()
        self.lifecycle: InstalledLifecycle | None = installed_lifecycle(lifecycle_provider)
        self.planner = ReadPlanCache(capacity)
        self.transaction_runner = TransactionRunner(
            self,
            self.clock,
            self.lifecycle,
            serving,
            self.planner,
        )
        self.shutdown = threading.RLock()
        self.observation: PoolObservation | None = register_pool_observation(
            lifecycle_provider, runtime.pool_metrics
        )

    def scoped(self, capture: ExecutionCapture, options: DatabaseOptions) -> ScopedDatabase:
        reads = standalone_read_scope(
            lifecycle=self.lifecycle,
            serving=self.serving,
            capture=capture,
            planner=self.planner,
        )
        return ScopedDatabase.create(self.transaction_runner, capture, options, reads)

    def close(self) -> None:
        with self.shutdown:
            try:
                self.runtime.close()
            finally:
                observation = self.observation
                self.observation = None
                if observation is not None:
                    close_pool_observations((observation,))


class Database[Authorization]:
    """The resource-owning Database Root and authority-selection surface."""

    __slots__ = ("_options", "_resources")

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
        serving = served_model(model, _CONSTRUCTOR_REFUSAL)
        self._options = options if options is not None else DatabaseOptions()
        self._resources = _DatabaseResources(
            runtime,
            serving,
            capacity=capacity,
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

    @classmethod
    def _alias(
        cls, resources: _DatabaseResources[Authorization], options: DatabaseOptions
    ) -> Database[Authorization]:
        alias = object.__new__(cls)
        alias._resources = resources
        alias._options = options
        return alias

    def with_options(
        self,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> Database[Authorization]:
        return self._alias(
            self._resources,
            patch_options(
                self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            ),
        )

    def using_principal(self, principal: Principal[Authorization], /) -> ScopedDatabase:
        capture = capture_principal(self._resources.runtime, principal)
        return self._resources.scoped(capture, self._options)

    def using_database_login(self) -> ScopedDatabase:
        capture = capture_database_login(self._resources.runtime)
        return self._resources.scoped(capture, self._options)

    def close(self) -> None:
        self._resources.close()

    def __enter__(self) -> Database[Authorization]:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        del exc_type, exc, traceback
        self.close()


class ScopedDatabase:
    """An immutable, connectionless execution view with captured authority."""

    __slots__ = ("_capture", "_options", "_reads", "_transaction_runner")

    def __init__(self) -> None:
        raise TypeError("ScopedDatabase values are created by Database authority selection")

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("ScopedDatabase is immutable")

    @classmethod
    def create(
        cls,
        runner: TransactionRunner,
        capture: ExecutionCapture,
        options: DatabaseOptions,
        reads: ReadScope,
    ) -> ScopedDatabase:
        scoped = object.__new__(cls)
        object.__setattr__(scoped, "_transaction_runner", runner)
        object.__setattr__(scoped, "_capture", capture)
        object.__setattr__(scoped, "_options", options)
        object.__setattr__(scoped, "_reads", reads)
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
            self._transaction_runner,
            self._capture,
            patch_options(
                self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            ),
            self._reads,
        )

    def find[S](self, query: ObjectQuery[Any, S]) -> Snapshot[S]:
        return cast("Snapshot[S]", self._reads.find(query))

    def stream[S](self, query: ObjectQuery[Any, S], *, batch_size: int = 1000) -> SnapshotStream[S]:
        return cast("SnapshotStream[S]", self._reads.stream(query, batch_size))

    @property
    def wire(self) -> WireDatabaseView:
        return WireDatabaseView(self._reads)

    def read_rows(self, query: ObjectQueryNode) -> RowsResult:
        return cast("RowsResult", self._reads.read_rows(query))

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
        return cast(
            "T",
            self._transaction_runner.transact(
                fn,
                capture=self._capture,
                defaults=self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            ),
        )


connect = Database.connect
