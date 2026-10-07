from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import Self

from parallax.core.db_port import DatabaseRuntime, IsolationLevel
from parallax.core.execution._options import OMITTED, DatabaseOptions, Omitted, patch_options
from parallax.core.execution._publication import ServingModel
from parallax.core.execution._runner import TransactionRunner
from parallax.core.execution._scope import ExecutionScope
from parallax.core.execution_authority._authority import (
    ExecutionCapture,
    Principal,
    capture_database_login,
    capture_principal,
)
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
from parallax.core.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    ReadPlanCache,
    check_read_plan_cache_capacity,
)
from parallax.core.unit_work import Clock, Concurrency, SystemClock

__all__ = ["DatabaseRoot", "RootResources"]


class RootResources[Authorization]:
    """The one shared resource owner behind every root alias and scope.

    It holds the runtime, the Serving Model, the Clock, the installed
    lifecycle, the shared read-plan cache instance, the transaction runner,
    and the pool observation once, and is the identity a joining transaction's
    ownership is settled against.
    """

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

    def scope(self, capture: ExecutionCapture, options: DatabaseOptions) -> ExecutionScope:
        return ExecutionScope(
            self.transaction_runner,
            capture,
            options,
            lifecycle=self.lifecycle,
            serving=self.serving,
            planner=self.planner,
        )

    def close(self) -> None:
        with self.shutdown:
            try:
                self.runtime.close()
            finally:
                observation = self.observation
                self.observation = None
                if observation is not None:
                    close_pool_observations((observation,))


class DatabaseRoot[Authorization, Scope]:
    """A Database Root over one runtime, specialized by the lifecycle facade
    ``scope_for`` builds over each authority-selected :class:`ExecutionScope`.

    Option aliases and execution scopes share the root's resources. Closing any
    alias closes them for all of them; selecting authority acquires no
    connection.
    """

    __slots__ = ("_options", "_resources", "_scope_for")

    def __init__(
        self,
        runtime: DatabaseRuntime[Authorization],
        serving: ServingModel,
        *,
        scope_for: Callable[[ExecutionScope], Scope],
        options: DatabaseOptions | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        self._options = options if options is not None else DatabaseOptions()
        self._scope_for = scope_for
        self._resources = RootResources(
            runtime,
            serving,
            capacity=capacity,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
        )

    def _alias(self, options: DatabaseOptions) -> Self:
        alias = object.__new__(type(self))
        alias._resources = self._resources
        alias._scope_for = self._scope_for
        alias._options = options
        return alias

    def with_options(
        self,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: Concurrency | Omitted = OMITTED,
        retry_optimistic_conflicts: bool | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> Self:
        return self._alias(
            patch_options(
                self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                retry_optimistic_conflicts=retry_optimistic_conflicts,
                isolation=isolation,
            )
        )

    def using_principal(self, principal: Principal[Authorization], /) -> Scope:
        capture = capture_principal(self._resources.runtime, principal)
        return self._scope_for(self._resources.scope(capture, self._options))

    def using_database_login(self) -> Scope:
        capture = capture_database_login(self._resources.runtime)
        return self._scope_for(self._resources.scope(capture, self._options))

    def close(self) -> None:
        self._resources.close()

    def __enter__(self) -> Self:
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
