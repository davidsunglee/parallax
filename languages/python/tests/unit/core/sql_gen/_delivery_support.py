"""Compiled reads delivered end to end without a database.

A suite authors the cells a statement's rows hold by the names its SQL selects
them under. The structural port fake folds them into positional driver rows by
that SQL and its document-read ordinals, and the rows then cross the production
boundary every read crosses: ``bind``, ``ReadRowConverter.record_row``, and the
Page-owned stored-value judgment. No step reads the compiled result contract's
keys, so an expectation authored from a model's declarations stays independent
of them.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.metamodel import Metamodel
from parallax.core.internal.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    ViewSchema,
    entity_state,
    page_rows,
)
from parallax.core.internal.read_delivery._row_converter import bind
from parallax.core.internal.sql_gen._compile import CompiledRead
from parallax.core.internal.temporal_read import Pin
from tests._support.bindings import TEST_BINDING
from tests._support.document_reads import fold_mapping_rows
from tests.unit.snapshot._snapshot_page_support import rendered_members

__all__ = ["DeliveredRow", "deliver"]


@dataclass(frozen=True, slots=True)
class DeliveredRow:
    """One delivered row: the Entity it resolved to, its judged members by
    declared name with absent members omitted, each stored data issue judgment
    recorded as its code beside the stored value it rejected, and the raw shared
    document conversion handed back."""

    entity: str
    members: dict[str, object]
    issues: tuple[tuple[str, object], ...]
    document: object | None


def deliver(
    model: Metamodel, compiled: CompiledRead, rows: Sequence[Mapping[str, object]]
) -> tuple[DeliveredRow, ...]:
    """``rows``, each spelled by the names ``compiled``'s statement selects its
    cells under, delivered in order through one bound converter and one Page.

    A name the statement never spells is refused rather than silently read as
    SQL ``NULL``; a selected cell a row leaves unnamed is SQL ``NULL``.
    """
    sql = compiled.statement.sql
    for row in rows:
        unknown = [key for key in row if re.search(rf"\b{re.escape(key)}\b", sql) is None]
        assert not unknown, f"{unknown} are not spelled by {sql!r}"
    converter = bind(
        CatalogedModel(model, TEST_BINDING), compiled.result_contract, compiled.projection
    )
    builder = PageBuilder(ViewSchema.of())
    converted = [
        converter.record_row(row, builder, source=ROOT_LEVEL)
        for row in fold_mapping_rows(rows, compiled.document_reads, sql)
    ]
    page = page_rows(builder.finish(tuple(ref for ref, *_rest in converted), Pin()))
    delivered: list[DeliveredRow] = []
    for root, (_ref, resolved, document) in zip(page.roots, converted, strict=True):
        state = entity_state(page, root)
        layout = page.layouts[root]
        assert layout.concrete == resolved
        delivered.append(
            DeliveredRow(
                resolved.name,
                rendered_members(layout, state.member_row),
                tuple((issue.code, issue.stored_value) for issue in state.findings),
                document,
            )
        )
    return tuple(delivered)
