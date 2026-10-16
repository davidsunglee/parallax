"""Read-only transactions through the shipped public surface (`spec/execution.md`),
against a real Postgres: the usage guide's own read-only story, and the access
mode each entrypoint requests reaching the native transaction — a read-only
callback runs in a transaction the database itself keeps read-only, and a
writable one runs read/write even where the session defaults to read-only.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

from parallax.conformance import engine, provision, read_only_stories
from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_port import (
    AccessMode,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    OrderedWriteTransport,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.execution import ReadOnlyTxnOptions
from parallax.snapshot import TxnContext, connect

_ACCOUNT = MODELS["account"]


class _AccessModeProbe:
    """A fully delegating connection that reads, inside each transaction the
    handle opens, the access mode the session defaults to and the one the
    transaction runs in, beside the mode the handle requested."""

    def __init__(self, inner: DatabaseConnection, seen: list[dict[str, str | None]]) -> None:
        self._inner = inner
        self._seen = seen

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._inner.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return self._inner.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return self._inner.execute_write(sql, binds)

    @property
    def ordered_write_transport(self) -> OrderedWriteTransport | None:
        return self._inner.ordered_write_transport

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        seen = self._seen

        def probing(conn: DatabaseConnection) -> T:
            seen.append(
                {
                    "requested": access_mode,
                    "configured": _show(conn, "default_transaction_read_only"),
                    "effective": _show(conn, "transaction_read_only"),
                }
            )
            return body(conn)

        return self._inner.transaction(probing, isolation=isolation, access_mode=access_mode)


def _show(conn: DatabaseConnection, setting: str) -> str:
    rows = conn.execute(f"show {setting}", ())
    return str(rows[0][0])


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_setup_metamodel(case),
        provision.load_fixtures(engine.case_setup_model_ref(case)),
    )


def test_the_read_only_usage_guide_story_runs_against_a_real_database(profile_run: Any) -> None:
    _seeded(profile_run)
    report = read_only_stories.reads_run_in_one_read_only_transaction_at_a_chosen_isolation(
        profile_run.port, _ACCOUNT
    )
    assert report.options == ReadOnlyTxnOptions(max_retries=10, isolation="repeatable_read")
    assert report.balance == report.reread_balance == Decimal("250.00")
    assert report.read_only_join_shared_the_context
    assert report.writable_join_refused


def test_each_entrypoint_runs_in_its_own_mode_whatever_the_session_defaults_to(
    profile_run: Any,
) -> None:
    # The session defaults to read-only, so a writable invocation that asked for
    # nothing would inherit it and fail its write. Each entrypoint asks for its
    # mode explicitly: the read-only one runs read-only, and the writable one
    # runs read/write and commits.
    _seeded(profile_run)
    seen: list[dict[str, str | None]] = []
    configured = profile_run.configured(settings={"default_transaction_read_only": "on"})
    probed = DecoratingAdapter(configured, lambda conn: _AccessModeProbe(conn, seen))
    with connect(probed, _ACCOUNT) as database:
        db = database.using_database_login()
        read = db.read_only(lambda rtx: rtx.find(Account.where(Account.id == 2)).result())

        def credit(tx: TxnContext) -> None:
            account = tx.find(Account.where(Account.id == 2)).result()
            tx.amend(account.edit(balance=account.balance + 1))

        db.transact(credit)
        reread = db.read_only(lambda rtx: rtx.find(Account.where(Account.id == 2)).result())
    assert read.balance == Decimal("250.00")
    assert reread.balance == Decimal("251.00")
    assert [(entry["requested"], entry["effective"]) for entry in seen] == [
        ("read_only", "on"),
        ("read_write", "off"),
        ("read_only", "on"),
    ]
    assert {entry["configured"] for entry in seen} == {"on"}
