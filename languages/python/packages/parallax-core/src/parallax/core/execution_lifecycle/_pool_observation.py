from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from parallax.core.db_port import PoolMetricsSource, report_unregistration_failure

__all__ = [
    "PoolMetricsObserver",
    "PoolObservation",
    "close_pool_observations",
    "register_pool_observation",
    "register_pool_observations",
]


class PoolObservation(Protocol):
    """One live registration of an interest in a pool's measurements.

    A handle holds it from composition until close and closes it exactly once.
    Nothing else reads it: it is a lifetime, not a channel.
    """

    def close(self) -> None:
        """Give up this interest.

        Called once, while the handle that registered it is closing, after its
        runtime has been closed and its source detached — so a sample taken from
        here on answers detached whether or not this ran. Ordinary failures are
        contained by the caller: a registration that will not close cannot be
        allowed to stop the rest of a shutdown.
        """
        ...


@runtime_checkable
class PoolMetricsObserver(Protocol):
    """The optional half of the composition seam: interest in the pool itself.

    An application implements this ON the Provider it already passes to
    ``connect``, which is what keeps composition to one argument. Implementing
    it is the whole declaration of interest — there is no capability flag, no
    second seam, and no way to ask for it that composition would have to answer.
    """

    def observe_pool(self, source: PoolMetricsSource, /) -> PoolObservation | None:
        """Take an interest in ``source``, or answer ``None`` to take none.

        Called once per source, during composition, before the handle is
        published and only where the runtime publishes a source at all — a
        runtime keeping one pool per route publishes one source per route, and
        each names its own. A source is stable for that runtime's life, so it
        may be retained; sampling through it is the observer's own to schedule.

        An ordinary failure here fails composition — no handle is published and
        the runtime that was opened is closed — because a registration that
        raised has said nothing about what it did or did not take.
        """
        ...


def register_pool_observation(
    provider: object, source: PoolMetricsSource
) -> PoolObservation | None:
    """Offer ``source`` to ``provider``, where the Provider takes an interest.

    Answers ``None`` for every way there is nothing to register: no Provider, a
    Provider that observes no pool, and one that was offered the source and
    declined it.
    """
    if not isinstance(provider, PoolMetricsObserver):
        return None
    return provider.observe_pool(source)


def register_pool_observations(
    provider: object, sources: Sequence[PoolMetricsSource]
) -> tuple[PoolObservation, ...]:
    """Offer each of ``sources`` to ``provider`` once, in order.

    Composition holds the answer and closes it; empty is a shutdown with
    nothing to do. A registration that RAISES closes every one already taken
    before the exception leaves with its identity intact, because no handle
    will be published to close them.
    """
    registered: list[PoolObservation] = []
    try:
        for source in sources:
            observation = register_pool_observation(provider, source)
            if observation is not None:
                registered.append(observation)
    except BaseException:
        close_pool_observations(registered)
        raise
    return tuple(registered)


def close_pool_observations(observations: Sequence[PoolObservation]) -> None:
    """Close every one of ``observations``, containing ordinary failures.

    Every registration is attempted, whatever the ones before it did: this runs
    while something else is being unwound — a shutdown, or a registration that
    raised partway through a composition — and an interest left open because a
    sibling refused to close would be a leak caused by an unrelated failure.

    A contained failure reports through the restricted resource log, which
    states that a registration would not close and nothing about why: what
    raised is application code holding application state, and this is the one
    reporting path that runs with no Handler left to receive anything. An
    interrupt is not contained: the first one propagates, but only once every
    registration has been attempted.
    """
    interrupted: BaseException | None = None
    for observation in observations:
        try:
            observation.close()
        except Exception:
            report_unregistration_failure()
        except BaseException as failure:
            if interrupted is None:
                interrupted = failure
    if interrupted is not None:
        raise interrupted
