from __future__ import annotations

import datetime as dt

__all__ = ["stated_start"]


def stated_start(valid_from: dt.datetime | None) -> dict[str, dt.datetime]:
    """``valid_from`` as the keyword a public write takes, omitted where the
    target takes no start: a stated ``None`` is refused, never read as
    omission."""
    return {} if valid_from is None else {"valid_from": valid_from}
