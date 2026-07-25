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

It also owns :func:`column_order`, the canonical physical column order of an
Entity's table: the order is family-effective, and the table-per-hierarchy tag
is the one physical column no declared Attribute backs.

Consumers reach the facet through :func:`view`, so generic facet retrieval stays
an internal formation seam.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.core.base import coerce_neutral_input, matches_neutral_type
from parallax.core.inheritance._columns import column_order
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
    MEMBER_SHADOWING,
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
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    ConcreteSubtype,
    EntityIdentity,
    EntityMetadata,
    PrimaryKey,
    VoDocumentViolation,
    vo_document_violation,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel

__all__ = [
    "CONCRETE_WITHOUT_ABSTRACT_ROOT",
    "CYCLE",
    "DUPLICATE_TAG_VALUE",
    "FACET_KEY",
    "INHERITANCE_MODULE",
    "ISSUE_CODES",
    "MEMBER_SHADOWING",
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
    "InheritanceEntityView",
    "InheritanceError",
    "InheritanceFacet",
    "InheritanceModelCompiler",
    "InheritancePositionView",
    "InheritanceRuleSet",
    "WriteAssignmentError",
    "column_order",
    "compile_facet",
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
    :func:`validate_subtype_write`'s own branch — both the developer-facing
    ``_where`` verb family (`python.md` §5) and the conformance engine's
    predicate-write translation call this SAME function, so the two callers
    can never classify an inheritance-family predicate write differently. A
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


class WriteAssignmentError(ValueError):
    """A predicate-write assignment (`.set(...)`-built or case-authored) names
    an unassignable target or an ill-typed value (`python.md:667-676`;
    `m-case-format.md:700`/`:711` "framework-owned/unassignable assignments").
    ``rule`` is the shared classification both callers reuse verbatim in their
    own error text."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def validate_write_assignment(
    model: AcceptedMetamodel, entity: EntityMetadata, name: str, value: object
) -> None:
    """The ONE predicate-write assignment check every caller applies to one
    `{attr, value}` pair (`m-opt-lock` "Version values are framework-owned";
    `python.md` §5 "each field may be assigned at most once"): mirroring
    `model_copy`'s own assignability rule (`parallax.core.entity._entity.
    _validate_copy_keys`), a primary-key or optimistic-locking (version)
    target is rejected outright — a family's version/key columns are declared
    only on the root, so this walk reads the Inheritance Facet's FAMILY-EFFECTIVE
    applicable members, exactly like every other write-side member-name
    resolution. Neither `entity._expressions.AttributeExpr.set` (the typed path,
    `parallax.core.entity`) nor `unit_work.instructions.validate_instruction`
    (the case-authored engine/serialized path, `parallax.core.unit_work`) may
    import the other (`core/spec/modules.md` §7 DAG), so this classification
    lives here, the ONE scope both already depend on — the "one validator, two
    callers" pattern (`parallax.core.op_algebra.validate_operation` /
    `parallax.core.unit_work.write_validate.validate_write`'s own precedent)
    extended across a DAG boundary neither scope alone can bridge.

    For an ordinary scalar attribute, a non-``None`` ``value`` MUST also
    conform to its declared `m-core` neutral type (`matches_neutral_type` over
    the input-policy-coerced value, `~parallax.core.base.coerce_neutral_input`
    — the SAME exact scalar-value policy `write_validate` applies to a keyed
    write row). A ``None`` value is a legal CLEARING
    assignment ONLY when the attribute is declared ``nullable`` (mirroring
    `write_validate`'s own null short-circuit, which is likewise
    nullable-gated, `_check_entity_attribute`) — a NON-nullable scalar assigned
    ``None`` is rejected with the SAME `"required attribute is absent (or
    null)"` wording `write_validate`'s own required-attribute check uses
    (`None` is an explicit clearing attempt here, never an omitted/sparse
    member the way an absent keyed-write row key is, so this check is
    UNCONDITIONAL — there is no mutation-aware sparseness concept at the
    assignment boundary, every named assignment is "present" by construction).

    A ``name`` naming a VALUE-OBJECT member instead (FAMILY-EFFECTIVE through the
    same facet view) is likewise validated: a non-``None`` ``value`` MUST be a
    well-formed document against the member's declared composite — the SAME
    error-neutral structural walk `write_validate`'s own declared-composite
    check reuses (`parallax.core.metamodel.vo_document_violation`), so a
    non-document value (e.g. ``Customer.address.set(42)``, typed or the
    equivalent serialized ``PredicateWrite`` assignment) is rejected with this
    function's OWN established wording style; a well-formed document is accepted
    — assigning a value object is not itself rejected (the combination is
    structurally accepted). A ``None`` value is likewise a legal clearing
    assignment ONLY when the value object is declared ``nullable``
    (`m-value-object` "A `nullable: false` value object MUST be present at write
    time") — a NON-nullable value object assigned ``None`` is rejected reusing
    `vo_document_violation`'s own ``"value-object-missing"`` rendering
    (`_vo_assignment_error`, the SAME `"required value object is absent (or
    null)"` wording a nested required-VO violation already renders) rather than
    forking new text. A ``name`` this family declares NEITHER a scalar attribute
    NOR a value object for (one `validate_instruction`'s own
    member-name-honesty gate already rejects as wholly undeclared) is out of
    this function's scope — it returns silently, leaving that classification to
    its own owning check.
    """
    position = _entity_view(view(model), entity.identity)
    owner = entity.identity.name
    for attribute in position.applicable_attributes:
        if attribute.identity.name != name:
            continue
        if isinstance(attribute.primary_key, PrimaryKey):
            raise WriteAssignmentError(
                "primary-key", f"{owner}.{name}: primary-key fields may not be assigned"
            )
        if attribute.optimistic_locking:
            raise WriteAssignmentError(
                "optimistic-locking",
                f"{owner}.{name}: framework-owned fields (the version column) may not be assigned",
            )
        if value is None:
            if not attribute.nullable:
                raise WriteAssignmentError(
                    "value-type-mismatch",
                    f"{owner}.{name}: required attribute is absent (or null)",
                )
            return
        if not matches_neutral_type(coerce_neutral_input(value, attribute.type), attribute.type):
            raise WriteAssignmentError(
                "value-type-mismatch",
                f"{owner}.{name}: value {value!r} does not match the declared type "
                f"{attribute.type!r}",
            )
        return
    for value_object in position.applicable_value_objects:
        if value_object.identity.path[-1] != name:
            continue
        if value is None:
            if not value_object.nullable:
                raise _vo_assignment_error(
                    owner, name, VoDocumentViolation("", "value-object-missing")
                )
            return
        violation = vo_document_violation(value_object, value)
        if violation is not None:
            raise _vo_assignment_error(owner, name, violation)
        return


def _vo_assignment_error(
    entity_name: str, name: str, violation: VoDocumentViolation
) -> WriteAssignmentError:
    """Render :func:`validate_write_assignment`'s OWN rule vocabulary and
    message text (the ``"value-type-mismatch"`` rule, the SAME one a scalar
    mismatch raises — a malformed value-object assignment is, from this
    function's own vocabulary, just another shape of "the value does not
    match the declared type") from a shared, error-neutral
    ``parallax.core.metamodel._vo_document`` violation — that module owns no
    text of its own, see its own docstring."""
    path = _joined(f"{entity_name}.{name}", violation.path)
    if violation.reason == "not-a-list":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — a `many` "
            "value object must bind a list of documents",
        )
    if violation.reason == "not-a-document":
        return WriteAssignmentError(
            "value-type-mismatch",
            f"{path}: value {violation.value!r} does not match the declared type — expected a "
            "document (mapping)",
        )
    if violation.reason == "attribute-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required attribute is absent (or null)"
        )
    if violation.reason == "value-object-missing":
        return WriteAssignmentError(
            "value-type-mismatch", f"{path}: required value object is absent (or null)"
        )
    return WriteAssignmentError(
        "value-type-mismatch",
        f"{path}: value {violation.value!r} does not match the declared type "
        f"{violation.declared_type!r}",
    )


def _joined(base: str, path: str) -> str:
    """``base`` plus a shared-walk violation's own relative ``path`` — a nested
    member dot-joins, a ``many`` element index attaches bracket-first (no dot,
    mirroring `write_validate`'s own owner-string convention, e.g.
    ``"Customer.address.phones[0].number"``)."""
    if not path:
        return base
    if path.startswith("["):
        return f"{base}{path}"
    return f"{base}.{path}"


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
