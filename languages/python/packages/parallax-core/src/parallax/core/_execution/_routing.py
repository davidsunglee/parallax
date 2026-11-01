from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast, get_args

from parallax.core.db_port import (
    ConnectionContext,
    ConnectionContextSource,
    Route,
    RouteCapabilities,
    RoutePolicy,
    RouteSelection,
)

__all__ = ["OperationRouting", "check_read_policy", "resolved_read_policy"]

_POLICIES: Final = cast("tuple[RoutePolicy, ...]", get_args(RoutePolicy))


def resolved_read_policy(
    requested: object, routes: Mapping[Route, RouteCapabilities]
) -> RoutePolicy:
    """The read policy new execution under a root or scope requests.

    ``None`` resolves to the declared topology's default: ``reader_only`` where a
    reader is declared, ``writer_only`` otherwise. A policy naming a route the
    runtime does not declare is refused here, before anything acquires, because
    no acquisition could ever honor it.
    """
    policy = check_read_policy(requested)
    if policy is None:
        return "reader_only" if "reader" in routes else "writer_only"
    if policy != "writer_only" and "reader" not in routes:
        raise ValueError(
            f"read_policy={policy!r} needs a reader route, and this database declares only "
            f"a writer; configure a reader or use with_routing(read_policy='writer_only')"
        )
    return policy


def check_read_policy(value: object) -> RoutePolicy | None:
    """``value`` as the vocabulary's own spelling, or ``None`` for an omitted one.

    Judged without the routes a runtime declares, so a misspelling is refused
    before anything opens. Each candidate is compared rather than looked up, so
    a value no set can hash is refused the same way as any other.
    """
    if value is None:
        return None
    if isinstance(value, str):
        for policy in _POLICIES:
            if value == policy:
                return policy
    raise ValueError(f"read_policy must be one of {sorted(_POLICIES)}, got {value!r}")


class OperationRouting:
    """The policy one operation requests from every acquisition it makes.

    One operation is one eager read, one whole stream across its pages, or one
    outer transaction invocation across its retries. Once any acquisition it
    made fell back to the writer, every later one requests ``writer_only``: the
    operation stays where it was served rather than returning to a route that
    just failed it.
    """

    __slots__ = ("_policy", "_source")

    def __init__(self, source: ConnectionContextSource, policy: RoutePolicy) -> None:
        self._source = source
        self._policy: RoutePolicy = policy

    @property
    def policy(self) -> RoutePolicy:
        return self._policy

    def new_context(self) -> ConnectionContext:
        return self._source.new_context(self._policy)

    def record(self, selection: RouteSelection | None) -> None:
        if selection is not None and selection.fallback is not None:
            self._policy = "writer_only"
