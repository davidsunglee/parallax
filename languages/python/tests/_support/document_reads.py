"""Provider-neutral document folding for structural database-port fakes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core.base import SQL_NULL, PresentDocument, SqlNull, is_document_value
from parallax.core.db_port import DocumentReadOrdinals, Row


def fold_mapping_document_reads(
    row: Mapping[str, object], document_reads: Sequence[DocumentReadOrdinals]
) -> Row:
    """Fold a logical fake row according to a compiled adjacent projection contract."""
    if not document_reads:
        return dict(row)
    values = list(row.values())
    width = len(values) + len(document_reads)
    presences = {presence for presence, _document in document_reads}
    documents = {document for _presence, document in document_reads}
    managed: Row = {}
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
    rows: Sequence[Mapping[str, object]], document_reads: Sequence[DocumentReadOrdinals]
) -> list[Row]:
    """Fold every logical row returned by a structural database-port fake."""
    return [fold_mapping_document_reads(row, document_reads) for row in rows]
