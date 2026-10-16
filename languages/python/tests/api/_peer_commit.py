"""A peer transaction committed while the caller's own attempt is open."""

from __future__ import annotations

import threading
from collections.abc import Callable


def commit_as_a_peer(work: Callable[[], object]) -> None:
    """Run ``work`` to completion on another thread, whose transactions bind no
    attempt of the caller's, and re-raise whatever it raised.

    A caller inside an attempt uses it to let another session commit between
    that attempt's read and the write the read licenses.
    """
    failures: list[BaseException] = []

    def run() -> None:
        try:
            work()
        except BaseException as failure:  # re-raised on the caller's thread below
            failures.append(failure)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=10.0)
    assert not thread.is_alive(), "the peer transaction never finished"
    if failures:
        raise failures[0]
