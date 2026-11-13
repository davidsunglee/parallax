from __future__ import annotations

from collections.abc import Sequence as SequenceOf
from typing import Final

from parallax.core.internal.metamodel import (
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    IssueCode,
    MetamodelIssue,
    PrimaryKey,
    Sequence,
)
from parallax.core.internal.model_formation import ModuleIdentity

__all__ = ["ISSUE_CODES", "PK_GEN_MODULE", "RULE_SET"]

PK_GEN_MODULE: Final[ModuleIdentity] = "m-pk-gen"

SEQUENCE_CONFLICT: Final[IssueCode] = "pk-gen-sequence-conflict"
"""Two key declarations name one Sequence allocator but disagree on its batch
size, initial value, increment size, or key type, so no single allocator can
serve both."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset({SEQUENCE_CONFLICT})
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


def _allocator_terms(attribute: AttributeMetadata, sequence: Sequence) -> tuple[object, ...]:
    return (sequence.batch_size, sequence.initial_value, sequence.increment_size, attribute.type)


def _sequence_declarations(
    candidate: CandidateMetamodel,
) -> dict[str, list[tuple[AttributeMetadata, Sequence]]]:
    """Every Sequence key declaration, grouped by allocator key in canonical order.

    Only an Entity's own declared Attributes are read, so a family's key, which
    its declaring ancestor alone holds, contributes once however many positions
    inherit it, including a TPCS root that owns no table.
    """
    declarations: dict[str, list[tuple[AttributeMetadata, Sequence]]] = {}
    for entity in sorted(candidate.entities, key=lambda entity: entity.identity.sort_key):
        for attribute in entity.attributes:
            key = attribute.primary_key
            if isinstance(key, PrimaryKey) and isinstance(key.generation, Sequence):
                declarations.setdefault(key.generation.name, []).append((attribute, key.generation))
    return declarations


def validate_shared_allocators(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every declaration disagreeing with the first declaration of its allocator key."""
    issues: list[MetamodelIssue] = []
    for name, declarations in _sequence_declarations(candidate).items():
        first_attribute, first_sequence = declarations[0]
        expected = _allocator_terms(first_attribute, first_sequence)
        first_location = AttributeLocation(first_attribute.identity)
        issues.extend(
            MetamodelIssue(
                SEQUENCE_CONFLICT,
                AttributeLocation(attribute.identity),
                (first_location,),
                message=(
                    f"Sequence {name!r} is already declared by "
                    f"{first_attribute.identity.entity.canonical}.{first_attribute.identity.name} "
                    "with different batch size, initial value, increment size, or key type"
                ),
            )
            for attribute, sequence in declarations[1:]
            if _allocator_terms(attribute, sequence) != expected
        )
    return tuple(issues)


class PkGenRuleSet:
    """This module's Model Formation Rule Set: issues only, never a facet."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this Rule Set and its Issue Codes."""
        return PK_GEN_MODULE

    @property
    def issue_codes(self) -> frozenset[IssueCode]:
        """The complete owned code set every emission is held to."""
        return ISSUE_CODES

    def validate(self, candidate: CandidateMetamodel) -> SequenceOf[MetamodelIssue]:
        """Report every shared-allocator disagreement ``candidate`` carries."""
        return validate_shared_allocators(candidate)


RULE_SET: Final[PkGenRuleSet] = PkGenRuleSet()
"""The single stateless Rule Set instance a composition root supplies."""
