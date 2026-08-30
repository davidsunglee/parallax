"""The one place a Scenario position is added to a failure.

Every module a step's grading reaches — this package's own phases, write grading,
the Object Query oracle — speaks of the thing it was handed rather than of the
Scenario position that handed it over. The position is added here, once, at the
boundary that knows it.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

from ..case import Case
from ..case_assertions import CaseFailure

__all__ = ["reported_against"]


@contextlib.contextmanager
def reported_against(case: Case, step_index: int) -> Iterator[None]:
    """Name the active step on every authored failure raised inside.

    A driver exception is not an authored failure and passes through untouched,
    and a failure already naming both the case and this step is re-raised as it
    was written — so nesting this boundary inside another one it already crossed
    adds nothing a second time.
    """
    try:
        yield
    except CaseFailure as failure:
        marker = f"scenario[{step_index}]"
        prefix = f"{case.path.name}: "
        message = str(failure)
        if message.startswith(prefix) and marker in message:
            raise
        detail = message[len(prefix) :] if message.startswith(prefix) else message
        raise CaseFailure(f"{prefix}{marker} {detail}") from failure
