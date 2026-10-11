"""A real psycopg connection over a scripted libpq session, for the ordered
write operation's Docker-free proofs.

Everything psycopg itself decides runs for real: the connection, its pipeline,
its cursors, its result queue, and its prepared-statement cache. Only what libpq
would do is scripted — sending each command, answering it the way a server in
pipeline mode does, and handing results back while statements are still being
queued or only once the pipeline synchronizes, and withholding them while psycopg
waits until a cancellation releases them. A statement here carries no
binds, because psycopg's compiled bind dumpers require a real libpq connection.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import cast

import psycopg
import pytest
from psycopg.pq import ConnStatus, DiagnosticField, ExecStatus, TransactionStatus
from psycopg.rows import TupleRow
from psycopg.waiting import Ready, Wait


@dataclass(frozen=True)
class Statement:
    """A canonical count-only statement, as execution presents one."""

    sql: str
    binds: tuple[object, ...] = ()


@dataclass
class Result:
    """One libpq result, answering exactly what psycopg and the adapter ask of it."""

    status: int
    command_tuples: int | None = None
    command_status: bytes | None = None
    fields: dict[int, bytes] = field(default_factory=dict[int, bytes])
    message: str = ""

    def error_field(self, code: int) -> bytes | None:
        return self.fields.get(code)

    def get_error_message(self, encoding: str = "utf-8") -> str:
        del encoding
        return self.message


def counted(rows: int) -> Result:
    return Result(ExecStatus.COMMAND_OK, rows, f"UPDATE {rows}".encode())


def failed(
    sqlstate: str, message: str, *, severity: bytes = b"ERROR", constraint: str | None = None
) -> Result:
    fields: dict[int, bytes] = {
        DiagnosticField.SQLSTATE: sqlstate.encode(),
        DiagnosticField.SEVERITY_NONLOCALIZED: severity,
        DiagnosticField.MESSAGE_PRIMARY: message.encode(),
    }
    if constraint is not None:
        fields[DiagnosticField.CONSTRAINT_NAME] = constraint.encode()
    return Result(ExecStatus.FATAL_ERROR, fields=fields, message=message)


def unowned(message: str) -> Result:
    """A failure libpq raises itself, which carries no diagnostic fields."""
    return Result(ExecStatus.FATAL_ERROR, message=message)


def aborted() -> Result:
    return Result(ExecStatus.PIPELINE_ABORTED)


def synced() -> Result:
    return Result(ExecStatus.PIPELINE_SYNC)


def closed() -> Result:
    return Result(ExecStatus.COMMAND_OK)


def _counting_one(query: bytes) -> list[Result]:
    del query
    return [counted(1)]


class Server:
    """The libpq session under one psycopg connection, scripted.

    Each statement is answered by ``answer`` in the order it is sent; after a
    failed answer every command until the next synchronization is aborted, as
    a server in pipeline mode does. Answers reach psycopg as it fetches, or
    while it is still queueing when ``early`` is set. While ``held``, psycopg
    waits for them, as it does on a statement blocked behind a lock;
    ``on_wait`` runs on each wait and a cancellation ends the hold.
    """

    def __init__(self, answer: Callable[[bytes], list[Result]] | None = None) -> None:
        self.answer: Callable[[bytes], list[Result]] = (
            answer if answer is not None else _counting_one
        )
        self.status = ConnStatus.OK
        self.transaction_status = TransactionStatus.IDLE
        self.pipeline_status = 0
        self._encoding = "utf-8"
        self.socket = -1
        self.notice_handler: object = None
        self.notify_handler: object = None
        self.early = False
        self.sent: list[object] = []
        self.answers: deque[list[Result]] = deque()
        self.handed_early = 0
        self.refuse: Callable[[bytes], bool] = lambda _query: False
        self.on_communicate: Callable[[int], None] = lambda _call: None
        self.on_fetch: Callable[[int], None] = lambda _call: None
        self.held = False
        self.on_wait: Callable[[], None] = lambda: None
        self.communications = 0
        self.fetches = 0
        self._aborting = False

    def _respond(self, respond: Callable[[], list[Result]]) -> None:
        if self._aborting:
            self.answers.append([aborted()])
            return
        results = respond()
        if any(result.status == ExecStatus.FATAL_ERROR for result in results):
            self._aborting = True
        self.answers.append(results)

    def send_query_params(self, query: bytes, params: object, **_: object) -> None:
        del params
        if self.refuse(query):
            raise psycopg.OperationalError("sending query and params failed")
        self.sent.append(query)
        self._respond(lambda: self.answer(query))

    def send_close_prepared(self, name: bytes) -> None:
        self.sent.append(("close", name))
        self._respond(lambda: [closed()])

    def pipeline_sync(self) -> None:
        self.sent.append("sync")
        self._aborting = False
        self.answers.append([synced()])

    def enter_pipeline_mode(self) -> None:
        self.pipeline_status = 1

    def exit_pipeline_mode(self) -> None:
        self.pipeline_status = 0

    def send_flush_request(self) -> None:
        return

    def finish(self) -> None:
        self.status = ConnStatus.BAD

    def cancel(self) -> None:
        self.held = False

    def communicate(self, commands: deque[Callable[[], None]]) -> None:
        self.communications += 1
        while commands:
            commands.popleft()()
        self.on_communicate(self.communications)

    def hand_early(self) -> list[list[Result]]:
        if not self.early:
            return []
        handed = list(self.answers)
        self.answers.clear()
        self.handed_early += len(handed)
        return handed

    def fetch(self) -> list[Result]:
        self.fetches += 1
        self.on_fetch(self.fetches)
        return self.answers.popleft() if self.answers else []

    def lose(self, message: str) -> None:
        """Take every answer waiting to be read and fail before handing any
        over, as a read that fails part way through a batch does."""
        self.answers.clear()
        raise psycopg.OperationalError(message)


def _communicate(
    pgconn: Server, commands: deque[Callable[[], None]]
) -> Generator[Wait, Ready, list[list[Result]]]:
    pgconn.communicate(commands)
    while pgconn.held:
        yield Wait.RW
    return pgconn.hand_early()


def _fetch_many(pgconn: Server) -> Generator[Wait, Ready, list[Result]]:
    while pgconn.held:
        yield Wait.R
    return pgconn.fetch()


def _send(pgconn: Server) -> Generator[None]:
    del pgconn
    return
    yield


def script(*groups: list[Result]) -> Callable[[bytes], list[Result]]:
    """Answer each statement sent with the next of ``groups``."""
    pending = deque(groups)
    return lambda _query: pending.popleft()


@contextmanager
def native_session(
    monkeypatch: pytest.MonkeyPatch, server: Server
) -> Generator[psycopg.Connection[TupleRow]]:
    """A real autocommit psycopg connection over ``server``, closed afterwards."""

    def wait(gen: Generator[Wait, Ready, object], *_args: object, **_kwargs: object) -> object:
        try:
            next(gen)
            while True:
                server.on_wait()
                gen.send(Ready.RW)
        except StopIteration as done:
            return done.value

    def cancel(connection: psycopg.Connection[TupleRow], **_kwargs: object) -> None:
        cast("Server", connection.pgconn).cancel()

    monkeypatch.setattr("psycopg.waiting.wait", wait)
    monkeypatch.setattr(psycopg.Connection, "_try_cancel", cancel)
    monkeypatch.setattr("psycopg._pipeline_base.pipeline_communicate", _communicate)
    monkeypatch.setattr("psycopg._pipeline_base.fetch_many", _fetch_many)
    monkeypatch.setattr("psycopg._pipeline_base.send", _send)
    connection = psycopg.Connection[TupleRow](server)  # pyright: ignore[reportArgumentType] - the scripted session stands in for libpq's
    connection.autocommit = True
    try:
        yield connection
    finally:
        connection.close()
