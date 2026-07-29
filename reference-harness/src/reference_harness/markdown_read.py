"""Read declared facts out of Markdown prose.

A document that carries a machine-checked declaration has to be read the way a
human reads it, not the way a line-oriented pattern happens to. Markdown wraps
freely, and prose in this repository is wrapped by convention, so a rule that
consumes one physical line silently stops seeing whatever a later edit pushes
onto the next one — passing rather than failing. These readers work in the units
Markdown actually has: an inline code span, and a whole list item.

The module is neutral: it knows nothing about what the facts mean, so tooling
that checks a spec and tooling that checks a command graph can share it.
"""

from __future__ import annotations

import re

__all__ = ["CODE_SPAN_RE", "code_spans", "list_items"]

CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
"""One inline code span's content. A span does not span lines, so a citation
broken across a wrap is not a citation."""

_LIST_MARKER_RE = re.compile(r"(?P<indent>[ \t]*)[-*+][ \t]+")


def code_spans(text: str) -> frozenset[str]:
    """Every distinct inline code span in *text*."""
    return frozenset(CODE_SPAN_RE.findall(text))


def list_items(text: str) -> list[str]:
    """Every list item in *text*, each returned as one logical line.

    An item runs from its bullet to the first blank line or the first line
    indented no further than the bullet, and its continuation lines are joined
    with single spaces. A nested item is an item of its own, in source order.
    """
    items: list[str] = []
    body: list[str] = []
    indent = 0
    for line in text.splitlines():
        marker = _LIST_MARKER_RE.match(line)
        if marker is not None:
            if body:
                items.append(" ".join(body))
            body = [line[marker.end() :].strip()]
            indent = len(marker.group("indent"))
            continue
        if body and line.strip() and len(line) - len(line.lstrip()) > indent:
            body.append(line.strip())
            continue
        if body:
            items.append(" ".join(body))
            body = []
    if body:
        items.append(" ".join(body))
    return items
