"""Direct-column roles and derived Document Paths (m-storage-layout).

Under Relational Document Layout, where a member lives is decided twice from two
different inputs — by the Rule Set over the Candidate Metamodel, and by the
compiler over accepted Metadata — so the decision itself lives here once. Both
sides pass the same reference-free Attribute values and the same designation
sets, which is what keeps a rejection and a placement from disagreeing about
whether a member is document-resident.
"""

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
    Joins, ``temporal`` the starts and ends of the family's As-Of Axes,
    ``audit`` the Attributes accepted Audit Metadata designates, and an explicit
    optimistic-lock Attribute is likewise read from the Attribute itself. The
    table-per-hierarchy variant tag is framework-owned rather than an Attribute,
    so it is not decided here.

    Overlapping designations still name one Attribute and one role, so the answer
    is membership rather than a ranking.
    """

    joined: frozenset[AttributeIdentity] = frozenset()
    temporal: frozenset[AttributeIdentity] = frozenset()
    audit: frozenset[AttributeIdentity] = frozenset()

    def covers(self, attribute: AttributeMetadata) -> bool:
        """Whether ``attribute`` holds a direct role and stays a Column."""
        return (
            isinstance(attribute.primary_key, PrimaryKey)
            or attribute.optimistic_locking
            or attribute.identity in self.joined
            or attribute.identity in self.temporal
            or attribute.identity in self.audit
        )


def declares_column_override(name: str, storage: Column) -> bool:
    """Whether ``storage`` is an override rather than ``name``'s conventional spelling.

    A canonical descriptor normalizes a member's conventional Column spelling to
    absence, and every frontend resolves an omitted one through the portable
    default, so an accepted location equal to that default carries no authored
    override and restating the default is never a rejection.
    """
    return storage.name != default_column_name(name)
