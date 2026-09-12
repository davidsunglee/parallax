"""Provider-neutral document folding for structural database-port fakes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from parallax.core.base import SQL_NULL, PresentDocument, SqlNull, is_document_value
from parallax.core.db_port import DocumentReadOrdinals, MappingRow, Row


def fold_mapping_document_reads(
    row: Mapping[str, object], document_reads: Sequence[DocumentReadOrdinals]
) -> MappingRow:
    """Fold a logical fake row according to a compiled adjacent projection contract."""
    if not document_reads:
        return dict(row)
    values = list(row.values())
    width = len(values) + len(document_reads)
    presences = {presence for presence, _document in document_reads}
    documents = {document for _presence, document in document_reads}
    managed: MappingRow = {}
    source = iter(row.items())
    for ordinal in range(width):
        if ordinal in documents:
            try:
                name, value = next(source)
            except StopIteration as exc:
                raise ValueError("a fake row does not match its document-read projection") from exc
            if value is None:
                managed[name] = SQL_NULL
            elif isinstance(value, (SqlNull, PresentDocument)):
                managed[name] = value
            elif is_document_value(value):
                managed[name] = PresentDocument(value)
            else:
                raise ValueError("a fake document cell is not a portable document value")
        elif ordinal not in presences:
            try:
                name, value = next(source)
            except StopIteration as exc:
                raise ValueError("a fake row does not match its document-read projection") from exc
            managed[name] = value
    try:
        next(source)
    except StopIteration:
        return managed
    raise ValueError("a fake row does not match its document-read projection")


def fold_mapping_rows(
    rows: Sequence[Mapping[str, object]],
    document_reads: Sequence[DocumentReadOrdinals],
    sql: str | None = None,
) -> list[Row]:
    """Fold every logical row returned by a structural database-port fake."""
    projection = _projection(sql) if sql is not None else ()
    presence_ordinals = {presence for presence, _payload in document_reads}
    return [
        tuple(
            fold_mapping_document_reads(
                {
                    result_key: _projection_value(row, result_key, source_key)
                    for ordinal, (result_key, source_key) in enumerate(projection)
                    if ordinal not in presence_ordinals
                }
                if projection
                else row,
                document_reads,
            ).values()
        )
        for row in rows
    ]


_RESULT_ALIAS = re.compile(r"\s+as\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$", re.IGNORECASE)
_TRAILING_ALIAS = re.compile(r"\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*$")
_IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*$")


def _projection(sql: str) -> tuple[tuple[str, str | None], ...]:
    start = len("select ")
    depth = 0
    end = -1
    for index in range(start, len(sql)):
        char = sql[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and sql[index : index + 6].lower() == " from ":
            end = index
            break
    if end < 0:
        return ()

    items: list[str] = []
    item_start = start
    depth = 0
    for index in range(start, end):
        char = sql[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(sql[item_start:index].strip())
            item_start = index + 1
    items.append(sql[item_start:end].strip())

    projection: list[tuple[str, str | None]] = []
    for item in items:
        alias = _RESULT_ALIAS.search(item)
        trailing = None if alias is not None else _TRAILING_ALIAS.search(item)
        if alias is not None:
            result_key = alias.group(1)
            expression = item[: alias.start()].strip()
        elif trailing is not None:
            result_key = trailing.group(1)
            expression = item[: trailing.start()].strip()
        else:
            result_key = item.rsplit(".", 1)[-1].strip('`"')
            expression = item
        source = expression.rsplit(".", 1)[-1].strip('`"')
        projection.append((result_key, source if _IDENTIFIER.fullmatch(source) else None))
    return tuple(projection)


def _projection_value(row: Mapping[str, object], result_key: str, source_key: str | None) -> object:
    if result_key in row:
        return row[result_key]
    if source_key is not None and source_key in row:
        return row[source_key]
    return None
