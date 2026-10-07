from __future__ import annotations

from collections.abc import Iterable
from typing import Final, Protocol, cast

from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.read_delivery._page._rows import StoredDataIssueCode, StoredDataIssueInput
from parallax.core.read_delivery._page._stored_data import StoredDataIssue
from parallax.core.temporal_read import (
    Edge,
    NonTemporal,
    TemporalFacet,
    TemporalReadError,
    milestone_edge,
)
from parallax.core.write_plan import ObjectKey

__all__ = [
    "NON_HYDRATING_CODES",
    "VersionAttributes",
    "diagnosis",
    "hydrates",
    "observed_edge",
    "observed_object_key",
    "observed_version",
]


class VersionAttributes(Protocol):
    """Where an Entity's explicit optimistic-lock version Attribute is named.

    Answers ``None`` for a family that carries no explicit version, a temporal
    one included. The runtime composing a read supplies the policy that owns
    that fact, so publishing an observed version needs no Metadata scan here.
    """

    def version_attribute(
        self, model: Metamodel, entity: EntityIdentity
    ) -> AttributeIdentity | None: ...


NON_HYDRATING_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-leaf-undecodable",
        "stored-data-attribute-null",
        "stored-data-family-tag-unknown",
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
    }
)
"""The codes for which no conforming value exists to hydrate (`m-snapshot-read`).

Their complement — a required member absent or stored null, and a wrong-kind
occurrence — is exactly the set the normative absence collapse already answers,
so a root carrying only those hydrates completely.
"""


def hydrates(issues: Iterable[StoredDataIssueInput]) -> bool:
    """Whether a node carrying ``issues`` still publishes a value.

    The question every consumer of a classified node asks before treating it as
    ordinary data: a hydratable node's collapse produced legal member values, so
    it is an Entity a caller reads and a row a later write settles against, while
    a non-hydrating one has no conforming value to be either.
    """
    return not any(issue.code in NON_HYDRATING_CODES for issue in issues)


_UNIDENTIFIED_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {
        "stored-data-primary-key-null",
        "stored-data-primary-key-undecodable",
        "stored-data-family-tag-unknown",
    }
)
"""The codes that leave a node with no trustworthy Object Key of its own: its
identity did not decode, or the Entity that identity would name is unresolved."""


def diagnosis(issue: StoredDataIssueInput, key: ObjectKey | None) -> StoredDataIssue:
    """One internal issue as its public diagnosis, attributed to ``key``.

    Attribution is the whole of what classification adds: the path and the
    evidence are carried by reference exactly as conversion froze them.
    """
    return StoredDataIssue(
        issue.code,
        issue.entity,
        issue.member,
        key,
        path=issue.path,
        stored_value=issue.stored_value,
    )


def observed_object_key(
    layout: EntityLayout,
    member_row: tuple[object, ...],
    findings: tuple[StoredDataIssueInput, ...],
) -> ObjectKey | None:
    """A judged state's object identity, or absence where nothing trustworthy decoded.

    Derived exactly as a keyed write derives its own: the row's OWN resolved
    concrete Entity, never family-normalized, paired with the family key's
    ``(name, value)`` pair read at the layout's key position (`m-unit-work`).
    """
    if any(issue.code in _UNIDENTIFIED_CODES for issue in findings):
        return None
    position = layout.primary_key[0]
    value = member_row[position]
    return ObjectKey(
        layout.concrete,
        (
            (
                cast("AttributeIdentity", layout.members[position]).name,
                None if value is ABSENT else value,
            ),
        ),
    )


def observed_version(
    model: Metamodel,
    versions: VersionAttributes,
    layout: EntityLayout,
    member_row: tuple[object, ...],
) -> int | None:
    """A judged state's observed explicit version, or absence for every other shape."""
    attribute = versions.version_attribute(model, layout.concrete)
    if attribute is None:
        return None
    value = _member(layout, member_row, attribute)
    return value if isinstance(value, int) else None


def observed_edge(
    temporal: TemporalFacet, layout: EntityLayout, member_row: tuple[object, ...]
) -> Edge | None:
    """A judged state's observed milestone, or absence where no temporal edge decoded."""
    shape = temporal.shape(layout.concrete)
    if shape is None or isinstance(shape, NonTemporal):
        return None
    try:
        return milestone_edge(shape, _JudgedAxes(layout, member_row), None)
    except TemporalReadError:
        return None


class _JudgedAxes:
    """One judged member row read at its As-Of Axis positions."""

    __slots__ = ("_layout", "_member_row")

    def __init__(self, layout: EntityLayout, member_row: tuple[object, ...]) -> None:
        self._layout = layout
        self._member_row = member_row

    def axis_start(self, at: None, attribute: AttributeIdentity, /) -> object:
        del at
        return self._member_row[self._layout.index_of[attribute]]

    def axis_end(self, at: None, attribute: AttributeIdentity, /) -> object:
        del at
        return self._member_row[self._layout.index_of[attribute]]


def _member(layout: EntityLayout, values: tuple[object, ...], member: AttributeIdentity) -> object:
    """One member's value by position, with an absent one answering ``None``.

    A locator reads what the row carries, and a position this read did not carry
    is a position it observed nothing at — the same answer a stored null gives,
    which is all a key or a version can say about a member that is not there.
    """
    position = layout.index_of.get(member)
    if position is None:  # pragma: no cover - a family locator is family-effective
        return None
    value = values[position]
    return None if value is ABSENT else value
