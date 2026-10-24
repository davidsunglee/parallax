"""Compiled reads delivered end to end without a database.

A suite authors the cells a statement's rows hold by the names its SQL selects
them under. The structural port fake folds them into positional driver rows by
that SQL and its document-read ordinals, and the rows then cross the production
boundary every read crosses: ``bind``, ``ReadRowConverter.convert_row``, the
Page-owned stored-value judgment, and the converter's flat-row publisher. No
step reads the compiled result contract's keys, so an expectation authored from
a model's declarations stays independent of them.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import Metamodel
from parallax.core.read_delivery._page import (
    ROOT_LEVEL,
    PageBuilder,
    ViewSchema,
    page_rows,
    state_for,
)
from parallax.core.read_delivery._row_converter import bind
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin
from tests._support.document_reads import fold_mapping_rows
from tests.unit.snapshot._snapshot_page_support import rendered_members

__all__ = ["DeliveredRow", "deliver", "plain"]


@dataclass(frozen=True, slots=True)
class DeliveredRow:
    """One delivered row: the Entity it resolved to and its `familyVariant`,
    its judged members by declared name with absent members omitted, each stored
    data issue judgment recorded as its code beside the stored value it rejected,
    its published flat row as items in iteration order, and the raw shared
    document conversion handed back."""

    entity: str
    variant: str | None
    members: dict[str, object]
    issues: tuple[tuple[str, object], ...]
    published: tuple[tuple[str, object], ...]
    document: object | None


def plain(value: object) -> object:
    """``value`` with every mapping view a published occurrence holds made a
    ``dict``, so a published row compares against literal expectations."""
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in cast("Mapping[str, object]", value).items()}
    if isinstance(value, tuple):
        return tuple(plain(item) for item in cast("tuple[object, ...]", value))
    return value


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
    converter = bind(CatalogedModel(model), compiled.result_contract, compiled.projection)
    builder = PageBuilder(ViewSchema.of())
    converted = [
        converter.convert_row(row, builder, source=ROOT_LEVEL)
        for row in fold_mapping_rows(rows, compiled.document_reads, sql)
    ]
    page = page_rows(builder.finish(tuple(ref for ref, *_rest in converted), Pin()))
    publisher = converter.row_publisher()
    delivered: list[DeliveredRow] = []
    for root, (_ref, resolved, document, variant) in zip(page.roots, converted, strict=True):
        state = state_for(page, root)
        layout = page.layouts[root]
        assert layout.concrete == resolved
        published = publisher.publish(resolved, state.member_row, variant)
        delivered.append(
            DeliveredRow(
                resolved.name,
                variant,
                rendered_members(layout, state.member_row),
                tuple((issue.code, issue.stored_value) for issue in state.findings),
                tuple((key, plain(value)) for key, value in published.items()),
                document,
            )
        )
    return tuple(delivered)
