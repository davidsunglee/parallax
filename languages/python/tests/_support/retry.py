from __future__ import annotations

from typing import Final

from parallax.core.internal.execution import AdaptiveBackoff, RetryPolicy

__all__ = ["TINY_BACKOFF", "fast_retry"]

TINY_BACKOFF: Final = AdaptiveBackoff(base_delay=1e-6, max_delay=1e-6)
"""For a test about attempts rather than waits: too short to spend real time."""


def fast_retry(max_retries: int) -> RetryPolicy:
    return RetryPolicy(max_retries=max_retries, backoff=TINY_BACKOFF)
