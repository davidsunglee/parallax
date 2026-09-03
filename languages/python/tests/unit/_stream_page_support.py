"""The scripted root statements one streamed delivery issues.

Lives beside the unit suites that drive a delivery rather than in `_support/`,
because paging is what those suites are about and no other semantic surface
scripts a page loop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from _support.db_port import Read

__all__ = ["paged_reads"]


def paged_reads(rows: Sequence[Mapping[str, object]], *, size: int) -> list[Read]:
    """The root statements a streamed delivery of ``rows`` at page size ``size``
    issues, in order.

    A page asks for one root MORE than it may deliver, so each entry is a page's
    own batch plus the first root of the page that follows it — read to prove a
    further page exists, discarded, and returned again by that page's own
    statement. The delivery ends on the first page that comes back short, so a
    result filling its last page exactly costs no terminal statement.
    """
    reads: list[Read] = []
    start = 0
    while True:
        page = list(rows[start : start + size + 1])
        reads.append(Read(rows=page))
        if len(page) <= size:
            return reads
        start += size
