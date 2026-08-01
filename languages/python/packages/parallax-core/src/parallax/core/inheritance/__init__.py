"""``parallax.core.inheritance`` enforcement scope (m-inheritance).

The closed inheritance-tree model: exactly one abstract ``root``, interior
``abstract-subtype`` nodes, row-owning ``concrete-subtype`` leaves, and the two
strategies (table-per-hierarchy with a tag discriminator,
table-per-concrete-subtype). This scope owns the family invariants a model must
satisfy and the Inheritance Facet that answers, once per formation, every
family-effective question — ancestry, family identity, effective
concrete-subtype sets, member applicability, physical container and tag, and the
root-owned Persistence Mode — so a consumer reads a precomputed family fact
instead of recomputing it. ``m-inheritance`` depends on ``m-metamodel`` and
``m-model-formation``.

It exports :func:`project_table_groups`, the pure Candidate Metamodel projection
the dependent Storage Layout Rule Set validates. Canonical physical column
order, effective nullability, and physical keys belong to
``m-storage-layout``; nothing here answers a physical table's shape.

Consumers reach the facet through :func:`view`, so generic facet retrieval stays
an internal formation seam.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core.inheritance._compile import (
    MODEL_COMPILER,
    InheritanceModelCompiler,
    compile_facet,
    root_metadata,
)
from parallax.core.inheritance._facet import (
    FACET_KEY,
    INHERITANCE_MODULE,
    InheritanceEntityView,
    InheritanceFacet,
    InheritancePositionView,
    view,
)
from parallax.core.inheritance._rules import (
    CONCRETE_WITHOUT_ABSTRACT_ROOT,
    CYCLE,
    DUPLICATE_TAG_VALUE,
    ISSUE_CODES,
    MATERIALIZATION_KEY_COLLISION,
    MEMBER_SHADOWING,
    MISSING_CONCRETE_SUBTYPE,
    MISSING_ROOT,
    MISSING_TAG_VALUE,
    OPTIMISTIC_LOCKING_NOT_ROOT_OWNED,
    PERSISTENCE_NOT_ROOT_OWNED,
    PRIMARY_KEY_MISSING,
    PRIMARY_KEY_MULTIPLE,
    RULE_SET,
    STRATEGY_REDECLARED,
    TAG_ON_CONCRETE_SUBTYPE_STRATEGY,
    TEMPORAL_AXES_NOT_ROOT_OWNED,
    TPCS_ABSTRACT_TABLE_FORBIDDEN,
    TPCS_CONCRETE_TABLE_REQUIRED,
    TPH_DESCENDANT_TABLE_FORBIDDEN,
    TPH_ROOT_TABLE_REQUIRED,
    InheritanceRuleSet,
)
from parallax.core.inheritance._table_groups import (
    AttributeTableContributor,
    InheritanceTableGroup,
    TableGroupContributor,
    TablePerHierarchyTagContributor,
    TopLevelValueObjectTableContributor,
    project_table_groups,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    ConcreteSubtype,
    EntityIdentity,
    EntityMetadata,
    PrimaryKey,
    ValueObjectMetadata,
    WriteAssignmentError,
    judge_assignment,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel

__all__ = [
    "CONCRETE_WITHOUT_ABSTRACT_ROOT",
    "CYCLE",
    "DUPLICATE_TAG_VALUE",
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "ISSUE_CODES",
    "MATERIALIZATION_KEY_COLLISION",
    "MEMBER_SHADOWING",
    "MISSING_CONCRETE_SUBTYPE",
    "MISSING_ROOT",
    "MISSING_TAG_VALUE",
    "MODEL_COMPILER",
    "OPTIMISTIC_LOCKING_NOT_ROOT_OWNED",
    "PERSISTENCE_NOT_ROOT_OWNED",
    "PRIMARY_KEY_MISSING",
    "PRIMARY_KEY_MULTIPLE",
    "RULE_SET",
    "STRATEGY_REDECLARED",
    "TAG_ON_CONCRETE_SUBTYPE_STRATEGY",
    "TEMPORAL_AXES_NOT_ROOT_OWNED",
    "TPCS_ABSTRACT_TABLE_FORBIDDEN",
    "TPCS_CONCRETE_TABLE_REQUIRED",
    "TPH_DESCENDANT_TABLE_FORBIDDEN",
    "TPH_ROOT_TABLE_REQUIRED",
    "AttributeTableContributor",
    "InheritanceEntityView",
    "InheritanceError",
    "InheritanceFacet",
    "InheritanceModelCompiler",
    "InheritancePositionView",
    "InheritanceRuleSet",
    "InheritanceTableGroup",
    "TableGroupContributor",
    "TablePerHierarchyTagContributor",
    "TopLevelValueObjectTableContributor",
    "WriteAssignmentError",
    "compile_facet",
    "family_variant_name",
    "project_table_groups",
    "reject_predicate_write",
    "root_metadata",
    "validate_subtype_write",
    "validate_write_assignment",
    "view",
]


class InheritanceError(ValueError):
    """An inheritance family invariant is violated: either a raw descriptor's
    structural family shape (``parallax.conformance._descriptor_family.validate``)
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


# --------------------------------------------------------------------------- #
# Concrete-subtype write protocol (m-inheritance "Concrete-subtype writes"):  #
# the payload-shape rules a model-aware write                                 #
# validator MUST enforce before the target-validity rule, pre-SQL. `entity`   #
# is the write's resolved target (a concrete subtype for an idiomatic keyed   #
# verb; the family root by the rejected lane's own "no explicit handle"       #
# default, `m-op-algebra`'s target-resolution convention reused for writes)   #
# -- an abstract `entity` is itself the LAST-checked defect, never short-     #
# circuited ahead of the more specific payload-shape rules.                   #
# --------------------------------------------------------------------------- #
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
    single concrete subtype in ``entity``'s effective set accepts every field
    ``row`` carries), then **target-validity**
    (``abstract-write-target`` -- ``entity`` itself is not a concrete subtype).
    A payload tripping more than one defect pins the earliest, most specific one.
    """
    if entity.inheritance is None:
        return
    facet = view(model)
    position = _entity_view(facet, entity.identity)
    root = _entity_view(facet, position.root)
    pk_names = frozenset(
        attribute.identity.name
        for attribute in root.applicable_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    )
    name = entity.identity.name
    if not pk_names & row.keys():
        raise InheritanceError(
            "subtype-write-set-based-unsupported",
            f"{name}: write carries none of the family's primary-key attribute(s) "
            f"{sorted(pk_names)} -- a keyless payload denotes an unsupported set-based "
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
    candidate_fields = frozenset(row)
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
    :func:`validate_subtype_write`'s own branch. The build-time caller is
    :func:`~parallax.core.unit_work.instructions.validate_instruction`, which
    the developer-facing ``_where`` verb family (`python.md` §5) and the
    conformance engine's predicate-write translation both run before they
    buffer, so no ingress can classify an inheritance-family predicate write
    differently; :mod:`~parallax.core.unit_work.write_planner` calls it again at
    flush as the structural refusal before SQL. A
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


def validate_write_assignment(
    model: AcceptedMetamodel, entity: EntityMetadata, name: str, value: object
) -> None:
    """The ONE predicate-write assignment check every caller applies to one
    `{attr, value}` pair, resolved family-effectively and then judged.

    Resolution is this scope's half: a family's version and key columns are
    declared only on the root, so ``name`` is matched against the Inheritance
    Facet's FAMILY-EFFECTIVE applicable members, exactly like every other
    write-side member-name resolution. The verdict itself — assignability,
    nullability, declared-type conformance, and Value Object document shape — is
    :func:`~parallax.core.metamodel.judge_assignment`'s, the one judgement the
    typed ``.set(...)`` path and ``Entity.model_copy(update=...)`` both reach
    without a model at all. Only the resolution in front of it differs between
    the three callers, never the rule.

    The judgement names the member relative to its own owner, so this caller
    prefixes the addressed Entity: an assignment reported here reads
    ``Order.total: …`` however deep in a Value Object the violation was found.

    A ``name`` this family declares NEITHER a scalar attribute NOR a value object
    for (one `validate_instruction`'s own member-name-honesty gate already
    rejects as wholly undeclared) is out of this function's scope — it returns
    silently, leaving that classification to its own owning check.
    """
    position = _entity_view(view(model), entity.identity)
    owner = entity.identity.name
    for attribute in position.applicable_attributes:
        if attribute.identity.name == name:
            _judged(owner, attribute, value)
            return
    for value_object in position.applicable_value_objects:
        if value_object.identity.path[-1] == name:
            _judged(owner, value_object, value)
            return


def _judged(owner: str, member: AttributeMetadata | ValueObjectMetadata, value: object) -> None:
    """Judge ``member`` against ``value``, re-raising owner-qualified."""
    try:
        judge_assignment(member, value)
    except WriteAssignmentError as error:
        raise WriteAssignmentError(error.rule, f"{owner}.{error}") from error


def _concrete_accepted_field_names(
    facet: InheritanceFacet, effective: Sequence[EntityIdentity]
) -> tuple[frozenset[str], ...]:
    """Each concrete subtype in ``effective`` mapped to its OWN accepted field set.

    A concrete position's applicable members are exactly its own ancestry chain's
    declarations, which is the set a write targeting it may name; a sibling
    branch's member is absent from every one of them.
    """
    return tuple(
        frozenset(
            {member.identity.name for member in position.applicable_attributes}
            | {member.identity.path[-1] for member in position.applicable_value_objects}
        )
        for position in (_entity_view(facet, concrete) for concrete in effective)
    )
