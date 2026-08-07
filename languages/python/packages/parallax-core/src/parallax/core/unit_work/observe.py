"""The closed Write Observation algebra (m-unit-work).

A Write Observation is the database evidence a surviving write against existing
state retains. Absence is **structural**: an insert and an unversioned
Non-Temporal write carry no observation value at all, rather than a null one, so
there is no ``NoObservation``, no nullable observation flowing downstream, and no
representable "a version *and* a predecessor" or "neither" state. A required
observation that is missing is a planning error, raised while the step is being
settled, in **both** concurrency modes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from parallax.core.base import detach_json_container

__all__ = [
    "PredecessorRow",
    "TemporalObservation",
    "VersionObservation",
    "WriteObservation",
]


@dataclass(frozen=True, slots=True)
class VersionObservation:
    """The optimistic-lock version a versioned Non-Temporal row was read at."""

    observed_version: int


@dataclass(frozen=True, slots=True)
class PredecessorRow:
    """The complete, immutable persisted state a Temporal Observation retains.

    ``members`` holds every applicable member of the observed row by its declared
    name — every scalar Attribute, every complete Value Object occurrence, the
    complete primary key, every temporal bound, and every audit value — and no
    generated-value expression. Completeness is required because temporal
    expansion carries members the authored mutation never mentioned, and because
    a later decorator must tell carried state from changed state without a second
    read.

    ``document`` is the raw Structured Column document the observing read
    returned, retained beside the member state and never as an entry in it, so a
    successor is built by patching what the row actually held rather than by
    re-encoding the members this model happens to declare. The value is the read's
    own, unchanged; what this row keeps of it is a private portable JSON copy
    through :func:`~parallax.core.base.detach_json_container`. It is **absent** —
    not empty — under `Columns`
    layout, where the row has no Structured Column, and absent likewise for an
    observation whose source read no row; the member map stays purely logical
    either way, so a consumer iterating members can never surface the document as
    a result field or an Entity member.
    """

    members: Mapping[str, object]
    document: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", MappingProxyType(dict(self.members)))
        object.__setattr__(self, "document", detach_json_container(self.document))
        if not self.members:
            raise ValueError("a Predecessor Row carries the observed row's complete state")

    def member(self, name: str) -> object:
        """The observed value of one member, by its declared name."""
        return self.members[name]


@dataclass(frozen=True, slots=True)
class TemporalObservation:
    """The predecessor milestone a temporal close addresses, gates on, and
    carries state forward from.

    Transaction-Time-Only and Bitemporal entities have identical observation
    requirements; the accepted Temporal Facet, not a variant per temporal flavor,
    decides which topology applies.
    """

    predecessor: PredecessorRow


type WriteObservation = VersionObservation | TemporalObservation
"""The closed algebra of database evidence a write against existing state
retains."""
