"""A lifecycle Provider that lets another session commit between a flush's
coverage read and the writes it binds."""

from __future__ import annotations

from collections.abc import Callable

from tests.api._statement_interleaving import AfterReadStatement


class AfterCoverageRead(AfterReadStatement):
    """Runs ``peer`` right after the ``nth`` coverage read flushes issue for
    ``table`` — between that read and the writes it binds."""

    def __init__(self, table: str, peer: Callable[[], None], *, nth: int = 1) -> None:
        super().__init__(lambda sql: table in sql and "thru_z >" in sql, peer, nth=nth)
