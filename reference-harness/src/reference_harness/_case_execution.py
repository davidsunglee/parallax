"""Case-aware SQL execution over providers and held sessions."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol, cast

from ._declared_contributor import DeclaredContributor
from ._statement_bind_inference import infer_statement_bind_targets
from .case import Case
from .ddl_builder import declared_contributors
from .storage_layout import ColumnContributor, ColumnSlot


class _ReadExecutor(Protocol):
    @property
    def dialect(self) -> str: ...

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]: ...


class _StatementExecutor(_ReadExecutor, Protocol):
    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int: ...


class _SessionSource(Protocol):
    def open_session(
        self, isolation: str | None = None
    ) -> AbstractContextManager[_StatementExecutor]: ...


class _PeerSource(Protocol):
    def open_peer(self) -> AbstractContextManager[_StatementExecutor]: ...


class _TransactionExecutor(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class CaseExecution:
    """Execute logical case statements after metadata-directed bind conversion."""

    __slots__ = ("_case", "_declarations", "_executor")

    def __init__(self, case: Case, executor: _ReadExecutor) -> None:
        if isinstance(executor, CaseExecution):
            executor = executor._executor
        self._case = case
        self._executor = executor
        self._declarations: Mapping[ColumnContributor, DeclaredContributor] = declared_contributors(
            case.model
        )

    @property
    def dialect(self) -> str:
        return self._executor.dialect

    def query(self, sql: str, binds: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._executor.query(sql, self._provider_binds(sql, binds))

    def execute(self, sql: str, binds: Sequence[Any] = ()) -> int:
        executor = cast(_StatementExecutor, self._executor)
        return executor.execute(sql, self._provider_binds(sql, binds))

    def commit(self) -> None:
        cast(_TransactionExecutor, self._executor).commit()

    def rollback(self) -> None:
        cast(_TransactionExecutor, self._executor).rollback()

    @contextmanager
    def open_session(self, isolation: str | None = None) -> Iterator[CaseExecution]:
        source = cast(_SessionSource, self._executor)
        with source.open_session(isolation) as session:
            yield CaseExecution(self._case, session)

    @contextmanager
    def open_peer(self) -> Iterator[CaseExecution]:
        source = cast(_PeerSource, self._executor)
        with source.open_peer() as peer:
            yield CaseExecution(self._case, peer)

    def _provider_binds(self, statement: str, binds: Sequence[Any]) -> tuple[Any, ...]:
        provider_binds = list(binds)
        targets = infer_statement_bind_targets(self._case, statement, binds, self._executor.dialect)
        for index, target in targets.items():
            if not isinstance(target, ColumnSlot) or index >= len(provider_binds):
                continue
            declared = self._declarations.get(target.contributor)
            if declared is not None:
                provider_binds[index] = declared.provider_bind(provider_binds[index])
        return tuple(provider_binds)
