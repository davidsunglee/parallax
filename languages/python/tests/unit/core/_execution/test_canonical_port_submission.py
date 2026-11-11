from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

import pytest

from parallax.core._execution._write_lowering import LoweringCursor
from parallax.core.execution_lifecycle._activity import INERT
from parallax.core.internal.db_port import OrderedWriteResultComplete, PipelineStatement, Row
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.predicate import Comparison, FieldSubject
from parallax.core.internal.read_delivery._fetch import execute_read
from parallax.core.internal.read_delivery._page_reader import (
    _PendingFetch,  # pyright: ignore[reportPrivateUsage] - the pending fetch is the pipeline submission input
    _pipelined_rows,  # pyright: ignore[reportPrivateUsage] - the pipeline submission under test
)
from parallax.core.internal.sql_gen._context import LoweredStatement
from tests._support.db_port import (
    Ordered,
    OrderedCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Write,
    WriteCall,
)
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target
from tests.unit.core._execution._write_step_support import close, open_flush, step_executor


class _CanonicalPort(ScriptedAdapter):
    def __init__(self) -> None:
        super().__init__(
            Read(),
            Read(),
            Read(),
            Write(),
            Ordered(OrderedWriteResultComplete((1, 1))),
            ordered=True,
        )
        self.pipeline_sql: tuple[str, ...] | None = None

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        self.pipeline_sql = tuple(statement.sql for statement in statements)
        return super().execute_pipeline(statements, read_only=read_only)


def test_core_submits_canonical_sql_through_all_four_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = " and 'literal?%s' = 'literal?%s' and \"rate?%s\" = \"rate?%s\""
    orders = model("orders")
    compiled = compile_read(
        Comparison(op="eq", subject=FieldSubject("Order.id"), value=7),
        orders,
        POSTGRES,
        target(orders, "Order"),
    )
    read_sql = compiled.statement.sql + suffix
    compiled = replace(compiled, statement=replace(compiled.statement, sql=read_sql))

    original_lowered = LoweringCursor._lowered  # pyright: ignore[reportPrivateUsage] - observe the existing lowering seam

    def with_literals(cursor: LoweringCursor, step: Any) -> LoweredStatement:
        statement = original_lowered(cursor, step)
        return replace(statement, sql=statement.sql + suffix)

    monkeypatch.setattr(LoweringCursor, "_lowered", with_literals)

    port = _CanonicalPort()
    assert execute_read(port, compiled, INERT) == []
    pending = _PendingFetch(0, cast("Any", None), (), compiled, cast("Any", None))
    assert _pipelined_rows((pending, pending), port, INERT) == [[], []]

    with open_flush() as flush:
        step_executor(port).execute((close(1),), allocates=False, flush=flush)
    with open_flush() as flush:
        step_executor(port).execute((close(2), close(3)), allocates=False, flush=flush)

    assert read_sql.count("?") >= 2
    assert "%s" in read_sql
    assert port.pipeline_sql == (read_sql, read_sql)
    assert port.calls[:3] == [ReadCall(read_sql, (7,), True)] * 3
    writes = port.calls[3:]
    assert isinstance(writes[0], WriteCall)
    assert isinstance(writes[1], OrderedCall)
    for call in (writes[0], *writes[1].writes):
        assert call.sql.endswith(suffix)
        assert "?" in call.sql
        assert "%s" in call.sql
        assert len(call.binds) > 0
