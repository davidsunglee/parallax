"""One classified member of a driver row, read as the Page lane reads it.

Binding a compiled read prepares one classifier per classified member, and
conversion applies it to the raw member the row carries; composing those two
calls here keeps a test on that path rather than on a decoder of its own.
"""

from __future__ import annotations

from collections.abc import Mapping

from parallax.core.document_codec import DocumentFinding
from parallax.core.sql_gen._compile import CompiledRead


def classified_member(
    compiled: CompiledRead, row: Mapping[str, object], key: str
) -> tuple[object, tuple[DocumentFinding, ...]]:
    """``key``'s value and findings in ``row``, under the Entity the row names."""
    resolved = compiled.row_identity(row)[0]
    classify = compiled.raw_member_classifier(resolved, key)
    return classify(compiled.raw_member_of(row, resolved, key))
