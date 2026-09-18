"""`DatabaseOptions` through the shipped public surface (spec §5): the connect
and constructor keywords a root is configured with, the transaction keywords
that override them, `Transaction.options`, and — against a real Postgres —
that the level a root resolves is the level a transaction runs at even where
the database's own configured default is stronger.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from parallax.conformance import engine, provision
from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance.case_format import default_cases_dir, load_case
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Account
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.snapshot import DatabaseOptions, connect
from parallax.snapshot.handle import Database, Transaction

_ACCOUNT = MODELS["account"]


# --------------------------------------------------------------------------- #
# The public shape, pinned directly: the export snapshot records names alone.  #
# --------------------------------------------------------------------------- #
def test_connect_takes_options_as_its_first_keyword_in_the_documented_order() -> None:
    parameters = list(inspect.signature(connect).parameters)
    assert parameters == [
        "adapter",
        "model",
        "options",
        "read_plan_cache_capacity",
        "clock",
        "lifecycle_provider",
    ]
    options = inspect.signature(connect).parameters["options"]
    assert options.kind is inspect.Parameter.KEYWORD_ONLY
    assert options.default is None


def test_the_direct_constructor_takes_the_same_keywords_over_an_open_runtime() -> None:
    parameters = list(inspect.signature(Database).parameters)
    assert parameters == [
        "runtime",
        "model",
        "options",
        "read_plan_cache_capacity",
        "clock",
        "lifecycle_provider",
    ]


def test_transact_names_the_four_options_by_their_record_field_names() -> None:
    signature = inspect.signature(Database.transact)
    keywords = [name for name in signature.parameters if name not in ("self", "fn")]
    assert keywords == ["max_retries", "concurrency", "retry_optimistic_conflicts", "isolation"]
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in keywords
    )
    assert "retries" not in signature.parameters
    # Every keyword's default is the one shared omission marker, never `None`,
    # and it names itself as omission rather than as any value.
    defaults = {signature.parameters[name].default for name in keywords}
    assert len(defaults) == 1
    assert None not in defaults
    assert repr(next(iter(defaults))) == "OMITTED"


def test_the_record_is_read_only_on_the_transaction_and_names_the_same_four_fields() -> None:
    assert isinstance(Transaction.options, property)
    assert Transaction.options.fset is None
    assert [field.name for field in dataclasses.fields(DatabaseOptions)] == [
        "max_retries",
        "concurrency",
        "retry_optimistic_conflicts",
        "isolation",
    ]


# --------------------------------------------------------------------------- #
# The database's configured default is not the root's default.                #
# --------------------------------------------------------------------------- #
class _IsolationProbe:
    """A fully delegating connection that reads the session's configured default
    and the effective level inside each transaction the handle opens.

    ``transaction`` records the level the handle requested, hands the real
    port a body that runs the two diagnostic queries after the port has applied
    the level and before the work runs, and then calls the work. The queries
    are transaction-control diagnostics rather than the application's work, so
    they live in this test alone and never in a corpus assertion.
    """

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

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        seen = self._seen

        def probing(conn: DatabaseConnection) -> T:
            seen.append(
                {
                    "requested": isolation,
                    "configured": _show(conn, "default_transaction_isolation"),
                    "effective": _show(conn, "transaction_isolation"),
                }
            )
            return body(conn)

        return self._inner.transaction(probing, isolation=isolation)


def _show(conn: DatabaseConnection, setting: str) -> str:
    rows = conn.execute(f"show {setting}", ())
    return str(rows[0][0])


def _seeded(profile_run: Any) -> None:
    case = load_case(default_cases_dir() / "m-unit-work-001-read-your-own-writes.yaml")
    profile_run.reset(
        engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
    )


def _probed(profile_run: Any, seen: list[dict[str, str | None]]) -> Any:
    configured = profile_run.configured(
        settings={"default_transaction_isolation": r"repeatable\ read"}
    )
    return DecoratingAdapter(configured, lambda conn: _IsolationProbe(conn, seen))


def _read_one(tx: Transaction) -> Account:
    return tx.find(Account.where(Account.id == 1)).result()


def test_an_unconfigured_root_runs_at_read_committed_over_a_stronger_session_default(
    profile_run: Any,
) -> None:
    # The session is configured to default to Repeatable Read, and the root is
    # not configured at all. What the transaction runs at is the root's own
    # Read Committed: the database's default is a fallback nothing above the
    # port consults, so the transaction requested its level and got it.
    _seeded(profile_run)
    seen: list[dict[str, str | None]] = []
    with connect(_probed(profile_run, seen), _ACCOUNT) as db:
        options = db.transact(lambda tx: (_read_one(tx), tx.options)[1])
    assert options == DatabaseOptions()
    assert seen == [
        {
            "requested": "read_committed",
            "configured": "repeatable read",
            "effective": "read committed",
        }
    ]


def test_a_root_default_and_an_explicit_override_each_reach_the_transaction(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    seen: list[dict[str, str | None]] = []
    root = DatabaseOptions(isolation="serializable")
    with connect(_probed(profile_run, seen), _ACCOUNT, options=root) as db:
        inherited = db.transact(lambda tx: (_read_one(tx), tx.options)[1])
        overridden = db.transact(
            lambda tx: (_read_one(tx), tx.options)[1], isolation="repeatable_read"
        )
    assert inherited is root
    assert overridden == DatabaseOptions(isolation="repeatable_read")
    assert [(entry["requested"], entry["effective"]) for entry in seen] == [
        ("serializable", "serializable"),
        ("repeatable_read", "repeatable read"),
    ]
    assert {entry["configured"] for entry in seen} == {"repeatable read"}


@pytest.mark.parametrize("level", ["read_committed", "repeatable_read", "serializable"])
def test_every_level_a_root_can_be_configured_with_is_the_level_its_attempts_run_at(
    profile_run: Any, level: IsolationLevel
) -> None:
    _seeded(profile_run)
    seen: list[dict[str, str | None]] = []
    with connect(
        _probed(profile_run, seen), _ACCOUNT, options=DatabaseOptions(isolation=level)
    ) as db:
        db.transact(_read_one)
    assert [entry["requested"] for entry in seen] == [level]
    assert [entry["effective"] for entry in seen] == [level.replace("_", " ")]
