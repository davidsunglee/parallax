from __future__ import annotations

from collections.abc import Sequence as SequenceOf
from typing import Final

from parallax.core.internal.metamodel import (
    AttributeLocation,
    AttributeMetadata,
    CandidateMetamodel,
    IssueCode,
    KeySequence,
    MetamodelIssue,
    PrimaryKey,
    Sequence,
    inheritance_parent,
)
from parallax.core.internal.model_formation import ModuleIdentity

__all__ = ["ISSUE_CODES", "PK_GEN_MODULE", "RULE_SET"]

PK_GEN_MODULE: Final[ModuleIdentity] = "m-pk-gen"

SEQUENCE_CONFLICT: Final[IssueCode] = "pk-gen-sequence-conflict"
"""Two key declarations name one Sequence allocator but disagree on its batch
size, initial value, increment size, or key type, so no single allocator can
serve both."""

KEY_SEQUENCE_CONFLICT: Final[IssueCode] = "pk-gen-key-sequence-conflict"
"""Two key declarations name one KeySequence allocator but disagree on its batch
size, initial value, increment size, or key type, or one of them names it as a
Sequence, so no single native sequence can serve both."""

KEY_SEQUENCE_SUBTYPE_OVERRIDE: Final[IssueCode] = "pk-gen-key-sequence-subtype-override"
"""An inheritance subtype declares a KeySequence key of its own: a family
allocates from the one declaration its root makes."""

ISSUE_CODES: Final[frozenset[IssueCode]] = frozenset(
    {SEQUENCE_CONFLICT, KEY_SEQUENCE_CONFLICT, KEY_SEQUENCE_SUBTYPE_OVERRIDE}
)
"""This module's complete owned Issue Code set, as the Formation Manifest
declares it."""


type _Generator = Sequence | KeySequence


def _allocator_terms(attribute: AttributeMetadata, generator: _Generator) -> tuple[object, ...]:
    return (
        type(generator),
        generator.batch_size,
        generator.initial_value,
        generator.increment_size,
        attribute.type,
    )


def _allocator_declarations(
    candidate: CandidateMetamodel,
) -> dict[str, list[tuple[AttributeMetadata, _Generator]]]:
    """Every allocator-named key declaration, grouped by allocator key in canonical order.

    Only an Entity's own declared Attributes are read, so a family's key, which
    its declaring ancestor alone holds, contributes once however many positions
    inherit it, including a TPCS root that owns no table.
    """
    declarations: dict[str, list[tuple[AttributeMetadata, _Generator]]] = {}
    for entity in sorted(candidate.entities, key=lambda entity: entity.identity.sort_key):
        for attribute in entity.attributes:
            key = attribute.primary_key
            if isinstance(key, PrimaryKey) and isinstance(key.generation, Sequence | KeySequence):
                declarations.setdefault(key.generation.name, []).append((attribute, key.generation))
    return declarations


def validate_shared_allocators(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every declaration disagreeing with the first declaration of its allocator key.

    A disagreement involving a KeySequence is a :data:`KEY_SEQUENCE_CONFLICT`;
    one between Sequence declarations alone stays a :data:`SEQUENCE_CONFLICT`.
    """
    issues: list[MetamodelIssue] = []
    for name, declarations in _allocator_declarations(candidate).items():
        first_attribute, first_generator = declarations[0]
        expected = _allocator_terms(first_attribute, first_generator)
        first_location = AttributeLocation(first_attribute.identity)
        first_name = f"{first_attribute.identity.entity.canonical}.{first_attribute.identity.name}"
        for attribute, generator in declarations[1:]:
            if _allocator_terms(attribute, generator) == expected:
                continue
            native = isinstance(generator, KeySequence) or isinstance(first_generator, KeySequence)
            issues.append(
                MetamodelIssue(
                    KEY_SEQUENCE_CONFLICT if native else SEQUENCE_CONFLICT,
                    AttributeLocation(attribute.identity),
                    (first_location,),
                    message=(
                        f"allocator {name!r} is already declared by {first_name} with a "
                        "different generation, batch size, initial value, increment size, "
                        "or key type"
                        if native
                        else f"Sequence {name!r} is already declared by {first_name} "
                        "with different batch size, initial value, increment size, or key type"
                    ),
                )
            )
    return tuple(issues)


def validate_family_generators(candidate: CandidateMetamodel) -> tuple[MetamodelIssue, ...]:
    """Every KeySequence key an inheritance subtype declares for itself."""
    return tuple(
        MetamodelIssue(
            KEY_SEQUENCE_SUBTYPE_OVERRIDE,
            AttributeLocation(attribute.identity),
            message=(
                f"{entity.identity.canonical} extends another Entity, and a family allocates "
                "its keys from the KeySequence its root declares; declare the key and its "
                "generator on the family root"
            ),
        )
        for entity in sorted(candidate.entities, key=lambda entity: entity.identity.sort_key)
        if inheritance_parent(entity.inheritance) is not None
        for attribute in entity.attributes
        if isinstance(key := attribute.primary_key, PrimaryKey)
        and isinstance(key.generation, KeySequence)
    )


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
        """Report every shared-allocator disagreement and subtype generator
        ``candidate`` carries."""
        return (*validate_shared_allocators(candidate), *validate_family_generators(candidate))


RULE_SET: Final[PkGenRuleSet] = PkGenRuleSet()
"""The single stateless Rule Set instance a composition root supplies."""
