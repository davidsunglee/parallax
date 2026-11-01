from __future__ import annotations

from parallax.core.db_port import Route, RoutePolicy

__all__ = ["planned_route"]


def planned_route(policy: RoutePolicy, *, has_reader: bool) -> Route:
    """The one route a strict ``policy`` is served on.

    Pure: it reads no route's state and no clock. Core resolves a policy against
    the routes a runtime declares before asking, so a reader policy without a
    reader is a caller defect rather than a condition to classify, and
    ``reader_preferred``'s writer fallback is not provided by this runtime.
    """
    if policy == "writer_only":
        return "writer"
    if policy == "reader_only" and has_reader:
        return "reader"
    raise ValueError(f"this runtime does not serve read_policy={policy!r}")
