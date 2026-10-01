from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core.inheritance._compile import MODEL_COMPILER, root_metadata
from parallax.core.inheritance._facet import (
    FACET_KEY,
    INHERITANCE_MODULE,
    EntityMemberSelection,
    InheritanceEntityView,
    InheritanceFacet,
    InheritanceFamilyView,
    InheritancePositionView,
    view,
)
from parallax.core.inheritance._rules import ISSUE_CODES, RULE_SET
from parallax.core.inheritance._table_groups import (
    AttributeTableContributor,
    InheritanceTableGroup,
    TableGroupContributor,
    TopLevelValueObjectTableContributor,
    project_table_groups,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    ConcreteSubtype,
    EntityIdentity,
    EntityMetadata,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel

__all__ = [
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "ISSUE_CODES",
    "MODEL_COMPILER",
    "RULE_SET",
    "AttributeTableContributor",
    "EntityMemberSelection",
    "InheritanceEntityView",
    "InheritanceError",
    "InheritanceFacet",
    "InheritanceFamilyView",
    "InheritancePositionView",
    "InheritanceTableGroup",
    "TableGroupContributor",
    "TopLevelValueObjectTableContributor",
    "family_variant_name",
    "project_table_groups",
    "reject_predicate_write",
    "root_metadata",
    "validate_subtype_write",
    "view",
]


class InheritanceError(ValueError):
    """An inheritance family invariant is violated: either a raw descriptor's
    structural family shape (``parallax.descriptor.validate_inheritance_families``)
    or an accepted model's concrete-subtype write-payload shape
    (:func:`validate_subtype_write` / :func:`reject_predicate_write`).

    ``rule`` is the corpus ``rejectedRule`` classification (e.g.
    ``inheritance-cycle``); ``entity`` names the offending participant when one.
    """

    def __init__(self, rule: str, message: str, *, entity: str | None = None) -> None:
        super().__init__(message)
        self.rule = rule
        self.entity = entity


def family_variant_name(facet: InheritanceFacet, concrete: EntityIdentity) -> str:
    """Return ``concrete``'s stable wire/graph variant spelling.

    A family-unique local Entity name stays bare for compatibility. When two
    concrete subtypes in the same family share that local name across namespaces,
    the canonical qualified Entity spelling is required so the value resolves to
    exactly one accepted Identity.
    """
    concrete_view = _entity_view(facet, concrete)
    root_view = _entity_view(facet, concrete_view.root)
    matches = sum(1 for candidate in root_view.concrete_subtypes if candidate.name == concrete.name)
    return concrete.canonical if matches > 1 else concrete.name


_FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset({"tag", "tagValue", "familyVariant"})


def validate_subtype_write(
    model: AcceptedMetamodel, entity: EntityMetadata, row: Mapping[str, object]
) -> None:
    """Validate a concrete-subtype write payload's SHAPE, raising :class:`InheritanceError`.

    A no-op for a non-participant ``entity`` (every entity outside an inheritance
    family accepts any well-formed row shape here). For a participant, checks in
    the normative order (m-inheritance "A validator checks these payload-shape
    rules... before the target-validity rule"): **keyless**
    (``subtype-write-set-based-unsupported`` -- ``row`` carries none of the
    family's root-owned primary-key attributes, denoting an unsupported
    set-based write), **metadata** (``subtype-write-metadata-field`` -- ``row``
    carries the framework-owned tag column / ``tag`` / ``tagValue`` /
    ``familyVariant``), **sibling** (``subtype-write-sibling-attribute`` -- no
    single concrete subtype in ``entity``'s effective set accepts every
    FAMILY-DECLARED field ``row`` carries; a name the family declares nowhere sits
    on no branch, so it belongs to the caller's own member-honesty check and is
    excluded here rather than failing every ancestry chain), then **target-validity**
    (``abstract-write-target`` -- ``entity`` itself is not a concrete subtype).
    A payload tripping more than one defect pins the earliest, most specific one.
    """
    if entity.inheritance is None:
        return
    facet = view(model)
    position = _entity_view(facet, entity.identity)
    root = _entity_view(facet, position.root)
    key = position.primary_key.identity.name
    name = entity.identity.name
    if key not in row:
        raise InheritanceError(
            "subtype-write-set-based-unsupported",
            f"{name}: write carries none of the family's primary-key attribute(s) "
            f"{[key]} -- a keyless payload denotes an unsupported set-based "
            "inheritance write",
            entity=name,
        )
    forbidden = _FORBIDDEN_METADATA_KEYS
    if position.tag_column is not None:
        forbidden = forbidden | {position.tag_column}
    carried_metadata = sorted(forbidden & row.keys())
    if carried_metadata:
        raise InheritanceError(
            "subtype-write-metadata-field",
            f"{name}: write carries framework-owned metadata field(s) "
            f"{carried_metadata} -- the tag / tagValue / familyVariant are derived, never "
            "authored",
            entity=name,
        )
    effective = tuple(concrete.name for concrete in position.concrete_subtypes)
    accepted = _concrete_accepted_field_names(facet, position.concrete_subtypes)
    # The domain of the comparison is every name the FAMILY declares somewhere, so
    # it is taken from the ROOT's concrete set rather than the target's effective
    # set (`m-inheritance`: "The rule ranges over the names the family declares
    # somewhere"). A concrete target's effective set is the target alone, so
    # measuring against it would make every sibling name look undeclared and hand
    # the family's own branch conflict to the member-honesty gate, which cannot
    # name it.
    family_declared = frozenset[str]().union(
        *_concrete_accepted_field_names(facet, root.concrete_subtypes), frozenset()
    )
    candidate_fields = frozenset(row) & family_declared
    if not any(candidate_fields <= names for names in accepted):
        raise InheritanceError(
            "subtype-write-sibling-attribute",
            f"{name}: no single concrete subtype in the effective set {sorted(effective)} "
            f"accepts every field {sorted(candidate_fields)} -- the accepted fields are exactly "
            "the target's own ancestry chain",
            entity=name,
        )
    if not isinstance(entity.inheritance, ConcreteSubtype):
        raise InheritanceError(
            "abstract-write-target",
            f"{name}: a create/update/delete/terminate handle MUST name a concrete "
            f"subtype, not the abstract {_ABSTRACT_ROLES[type(entity.inheritance)]}",
            entity=name,
        )


# The role spellings an abstract position reports. The variant is the role, so
# the algebra carries no role field of its own; a concrete position never
# reaches this table.
_ABSTRACT_ROLES: Mapping[type, str] = {
    AbstractRoot: "root",
    AbstractSubtype: "abstract-subtype",
}


def _entity_view(facet: InheritanceFacet, identity: EntityIdentity) -> InheritanceEntityView:
    """``identity``'s family-effective view; the facet covers every accepted Entity."""
    position = facet.entity(identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{identity.canonical}: the model declares no such entity")
    return position


def reject_predicate_write(entity: EntityMetadata) -> None:
    """Reject a predicate-selected (set-based) write on ANY inheritance-family
    ``entity`` — root, abstract-subtype, or concrete-subtype alike — with the
    SAME ``subtype-write-set-based-unsupported`` classification
    :func:`validate_subtype_write`'s keyless-row branch raises (`m-inheritance`
    "Per-object writes are keyed; set-based inheritance writes are out of
    scope").

    A deliberate, TARGET-ENTITY-ONLY call shape:
    a predicate-selected write is set-based BY CONSTRUCTION (there is no row at
    all, keyed or otherwise), so this needs no row inspection and never
    synthesizes a fake keyless row just to trigger
    :func:`validate_subtype_write`'s own branch. Its caller is prepared-write
    production, shared by
    :func:`~parallax.core.unit_work.instructions.prepare_typed_write` and
    :func:`~parallax.core.unit_work.instructions.prepare_wire_write`, so no
    ingress can classify an inheritance-family predicate write differently and
    no prepared product names one. A
    no-op for a non-participant ``entity`` (every entity outside an
    inheritance family accepts a predicate-selected write, subject to every
    OTHER m-batch-write / m-opt-lock rule).
    """
    if entity.inheritance is None:
        return
    name = entity.identity.name
    raise InheritanceError(
        "subtype-write-set-based-unsupported",
        f"{name}: a predicate-selected (set-based) write on an inheritance-family "
        "entity is unsupported (subtype-write-set-based-unsupported) — per-object writes "
        "are keyed (m-inheritance 'Per-object writes are keyed; set-based inheritance "
        "writes are out of scope')",
        entity=name,
    )


def _concrete_accepted_field_names(
    facet: InheritanceFacet, effective: Sequence[EntityIdentity]
) -> tuple[frozenset[str], ...]:
    """Each concrete subtype in ``effective`` mapped to its OWN accepted field set.

    A concrete position's applicable members are exactly its own ancestry chain's
    declarations, which is the set a write targeting it may name; a sibling
    branch's member is absent from every one of them. Called with the FAMILY
    ROOT's concrete set, the union is every name the family declares anywhere —
    the domain the sibling rule is about, which is a property of the family and
    not of the position being written.
    """
    return tuple(
        frozenset(position.member_selection.shape.by_name)
        for position in (_entity_view(facet, concrete) for concrete in effective)
    )
