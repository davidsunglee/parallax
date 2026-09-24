from __future__ import annotations

from dataclasses import dataclass

from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Column,
    PrimaryKey,
    default_column_name,
)

__all__ = ["DirectRoles", "declares_column_override"]


@dataclass(frozen=True, slots=True)
class DirectRoles:
    """The designations that make an Attribute a direct Column under ``Document``.

    Each set is one role of the closed list: model primary keys are read from the
    Attribute itself, ``joined`` are the endpoints of accepted Relationship
    Joins, ``temporal`` the starts and ends of the family's As-Of Axes, and an
    explicit optimistic-lock Attribute is likewise read from the Attribute
    itself. The table-per-hierarchy variant tag is framework-owned rather than an
    Attribute, so it is not decided here. Audit Metadata designates no Attribute
    in any accepted model, so that role selects nothing and carries no set of its
    own: a set only one of the two deciders could be given is a residency the
    other could never accept.

    Every designation names a declared Attribute by the Identity its declaring
    Entity bears, never by the position that inherits it, so membership answers
    the same way wherever the declaration is reached from.

    Overlapping designations still name one Attribute and one role, so the answer
    is membership rather than a ranking.
    """

    joined: frozenset[AttributeIdentity] = frozenset()
    temporal: frozenset[AttributeIdentity] = frozenset()

    def covers(self, attribute: AttributeMetadata) -> bool:
        """Whether ``attribute`` holds a direct role and stays a Column."""
        return (
            isinstance(attribute.primary_key, PrimaryKey)
            or attribute.optimistic_locking
            or attribute.identity in self.joined
            or attribute.identity in self.temporal
        )


def declares_column_override(name: str, storage: Column) -> bool:
    """Whether ``storage`` is an override rather than ``name``'s conventional spelling.

    A canonical descriptor normalizes a member's conventional Column spelling to
    absence, and every frontend resolves an omitted one through the portable
    default, so an accepted location equal to that default carries no authored
    override and restating the default is never a rejection.
    """
    return storage.name != default_column_name(name)
