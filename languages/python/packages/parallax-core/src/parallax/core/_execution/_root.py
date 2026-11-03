from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType
from typing import Self

from parallax.core._execution._options import OMITTED, Omitted, TxnOptions, patch_options
from parallax.core._execution._publication import ServingModel
from parallax.core._execution._routing import resolved_read_policy
from parallax.core._execution._scope import ExecutionScope
from parallax.core._execution._transaction._runner import TransactionRunner
from parallax.core._execution._unit_work.clock import Clock, SystemClock
from parallax.core.concurrency import ConcurrencyPreference
from parallax.core.db_port import DatabaseRuntime, IsolationLevel, RoutePolicy
from parallax.core.execution_authority._authority import (
    ExecutionAuthority,
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
    register_pool_observations,
)
from parallax.core.read_delivery._read_plan import (
    DEFAULT_READ_PLAN_CACHE_CAPACITY,
    ReadPlanCache,
    check_read_plan_cache_capacity,
)

__all__ = ["DatabaseRoot", "RootResources"]


class RootResources[Authorization]:
    """The one shared resource owner behind every root alias and scope.

    It holds the runtime, the Serving Model, the Clock, the installed
    lifecycle, the shared read-plan cache instance, the transaction runner,
    and one pool observation per source the runtime publishes, once, and is the
    identity a joining transaction's ownership is settled against.
    """

    __slots__ = (
        "clock",
        "lifecycle",
        "observations",
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
        self.observations: tuple[PoolObservation, ...] = register_pool_observations(
            lifecycle_provider, runtime.pool_metrics
        )

    def scope(
        self, authority: ExecutionAuthority, options: TxnOptions, read_policy: RoutePolicy
    ) -> ExecutionScope:
        return ExecutionScope(
            self.transaction_runner,
            authority,
            options,
            read_policy,
            routes=self.runtime.routes,
            lifecycle=self.lifecycle,
            serving=self.serving,
            planner=self.planner,
        )

    def close(self) -> None:
        with self.shutdown:
            try:
                self.runtime.close()
            finally:
                observations = self.observations
                self.observations = ()
                close_pool_observations(observations)


class DatabaseRoot[Authorization, Scope]:
    """A Database Root over one runtime, specialized by the lifecycle facade
    ``scope_for`` builds over each authority-selected :class:`ExecutionScope`.

    Option and routing aliases and execution scopes share the root's
    resources. Closing any alias closes them for all of them; selecting
    authority or routing acquires no connection.

    ``read_policy`` is what new read execution requests. Omitted, it is
    ``reader_only`` where the runtime declares a reader and ``writer_only``
    otherwise; a policy the declared routes cannot honor is refused before the
    root is built.
    """

    __slots__ = ("_options", "_read_policy", "_resources", "_scope_for")

    def __init__(
        self,
        runtime: DatabaseRuntime[Authorization],
        serving: ServingModel,
        *,
        scope_for: Callable[[ExecutionScope], Scope],
        options: TxnOptions | None = None,
        read_policy: RoutePolicy | None = None,
        read_plan_cache_capacity: int = DEFAULT_READ_PLAN_CACHE_CAPACITY,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> None:
        capacity = check_read_plan_cache_capacity(read_plan_cache_capacity)
        self._read_policy: RoutePolicy = resolved_read_policy(read_policy, runtime.routes)
        self._options = options if options is not None else TxnOptions()
        self._scope_for = scope_for
        self._resources = RootResources(
            runtime,
            serving,
            capacity=capacity,
            clock=clock,
            lifecycle_provider=lifecycle_provider,
        )

    def _alias(self, options: TxnOptions, read_policy: RoutePolicy) -> Self:
        alias = object.__new__(type(self))
        alias._resources = self._resources
        alias._scope_for = self._scope_for
        alias._options = options
        alias._read_policy = read_policy
        return alias

    def with_options(
        self,
        *,
        max_retries: int | Omitted = OMITTED,
        concurrency: ConcurrencyPreference | Omitted = OMITTED,
        isolation: IsolationLevel | Omitted = OMITTED,
    ) -> Self:
        return self._alias(
            patch_options(
                self._options,
                max_retries=max_retries,
                concurrency=concurrency,
                isolation=isolation,
            ),
            self._read_policy,
        )

    def with_routing(self, *, read_policy: RoutePolicy) -> Self:
        return self._alias(
            self._options, resolved_read_policy(read_policy, self._resources.runtime.routes)
        )

    def using_principal(self, principal: Principal[Authorization], /) -> Scope:
        authority = capture_principal(self._resources.runtime, principal)
        return self._scope_for(self._resources.scope(authority, self._options, self._read_policy))

    def using_database_login(self) -> Scope:
        authority = capture_database_login(self._resources.runtime)
        return self._scope_for(self._resources.scope(authority, self._options, self._read_policy))

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
