"""m-inheritance: the accepted-model Rule Set, write-payload validation, and
predicate-write assignment checking."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, key, source

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.base import Decimal as DecimalType
from parallax.core.metamodel import (
    UNRESOLVED_ENTITY_REFERENCE,
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    AttributeLocation,
    AttributeReference,
    Cardinality,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    EntityLocation,
    EntityMetadata,
    ExactEntityReference,
    IssueCode,
    MetamodelIssue,
    PersistenceMode,
    RelationshipIdentity,
    RelationshipLocation,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    ValueObjectAttributeDeclaration,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    sort_issues,
)
from parallax.core.metamodel import AsOfAxisLocation as AxisLocation
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.unit_work import WriteRejectedError, validate_write
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._records import (
    Attribute,
    Entity,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._serde import parse_document

_REPO = case_format.find_repo_root()
_MODELS = corpus_models.load_models(_REPO / "core" / "compatibility" / "models")
_CASES = _REPO / "core" / "compatibility" / "cases"
_MODEL_FILES = sorted((_REPO / "core" / "compatibility" / "models").glob("*.yaml"))


def _descriptor_rejection_cases() -> list[tuple[str, dict[str, Any], str]]:
    found: list[tuple[str, dict[str, Any], str]] = []
    # `*` (not `0*`): the root-ownership witnesses (m-inheritance-102/103)
    # are the first `when.model` cases numbered past 099, so the glob must not
    # assume every id stays in the 0xx range.
    for path in sorted(_CASES.glob("m-inheritance-*-rejected-*.yaml")):
        loaded = case_format.safe_load_yaml(Path(path).read_text(encoding="utf-8"))
        document = cast("dict[str, Any]", loaded)
        when = document.get("when")
        if isinstance(when, dict) and "model" in when:
            model = cast("dict[str, Any]", when["model"])
            then = cast("dict[str, Any]", document["then"])
            found.append((path.stem, model, str(then["rejectedRule"])))
    return found


_REJECTIONS = _descriptor_rejection_cases()


def _metadata(stem: str, name: str) -> EntityMetadata:
    """One corpus Entity's accepted Metadata, formed from its own model file."""
    model = corpus_models.accepted_model(_MODELS[stem])
    metadata = model.entity(EntityIdentity("parallax.compatibility", name))
    assert metadata is not None
    return metadata


_INDEPENDENT_FAMILIES: Final[dict[str, Any]] = {
    "entities": [
        {
            "name": "Payment",
            "table": "payment",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        },
        {
            "name": "CardPayment",
            "inheritance": {"role": "concrete-subtype", "parent": "Payment", "tagValue": "card"},
            "attributes": [{"name": "network", "type": "string", "nullable": True}],
        },
        {
            "name": "Document",
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
        },
        {
            "name": "Invoice",
            "table": "invoice",
            "inheritance": {"role": "concrete-subtype", "parent": "Document"},
            "attributes": [{"name": "total", "type": "int64", "nullable": True}],
        },
    ]
}
"""Two families that share no ancestry, each rooted and each with its own
strategy — the shape a Domain Model assembles from independently declared
families."""


def test_inheritance_error_carries_rule_and_entity() -> None:
    error = inheritance.InheritanceError("inheritance-cycle", "boom", entity="Pet")
    assert error.rule == "inheritance-cycle"
    assert error.entity == "Pet"


# --------------------------------------------------------------------------- #
# `reject_predicate_write`: a predicate-selected                              #
# (set-based) write on ANY inheritance-family entity is unsupported before    #
# any SQL, the SAME classification a keyless keyed write raises.              #
# --------------------------------------------------------------------------- #
def test_reject_predicate_write_raises_for_a_concrete_subtype() -> None:
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.reject_predicate_write(_metadata("animal", "Dog"))
    assert caught.value.rule == "subtype-write-set-based-unsupported"
    assert caught.value.entity == "Dog"


def test_reject_predicate_write_raises_for_the_abstract_root() -> None:
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.reject_predicate_write(_metadata("animal", "Animal"))
    assert caught.value.rule == "subtype-write-set-based-unsupported"


def test_reject_predicate_write_is_a_no_op_for_a_non_participant() -> None:
    inheritance.reject_predicate_write(_metadata("account", "Account"))  # no raise


# --------------------------------------------------------------------------- #
# `validate_write_assignment`'s VALUE-OBJECT branch: the corpus/mirror         #
# `Customer.address` shape                                                     #
# (`test_where_verbs.py` / `test_write_instructions.py`) pins the four         #
# mandated shapes (typed/serialized reject/accept) but declares no             #
# non-nullable NESTED value object or `cardinality: many` member, so this      #
# synthetic model -- the SAME "hand-built model" convention                    #
# `test_write_validate.py`'s own `_WIDGET` uses for the sibling scalar walk --  #
# reaches every remaining shared-walk violation reason (`not-a-list`,          #
# `attribute-missing`, `value-object-missing`, a nested `many` element's own   #
# bracket-indexed path) directly against `inheritance.validate_write_          #
# assignment`, never through the typed/serialized frontends.                   #
#                                                                               #
# `code` (non-nullable scalar), `nickname` (nullable scalar), and `core`       #
# (non-nullable TOP-level value object -- `spec`/`tags` above are both         #
# `nullable: true`, so neither exercises a top-level required-VO rejection)    #
# extend this same synthetic model for the nullable-gated `None`-assignment    #
# refusal: a `None` assignment's nullability-aware                             #
# handling, pinned directly against the shared check below.                    #
# --------------------------------------------------------------------------- #
_VO_ENTITY = Entity(
    name="Gadget",
    table="gadget",
    attributes=(
        Attribute(name="id", type="int64", column="id", primary_key=True),
        Attribute(name="code", type="string", column="code"),
        Attribute(name="nickname", type="string", column="nickname", nullable=True),
    ),
    value_objects=(
        ValueObject(
            name="spec",
            column="spec",
            nullable=True,
            attributes=(ValueObjectAttribute(name="note", type="string"),),
            value_objects=(
                NestedValueObject(
                    name="detail",
                    nullable=False,
                    attributes=(ValueObjectAttribute(name="hint", type="string", nullable=True),),
                ),
                NestedValueObject(
                    name="grid",
                    multiplicity="many",
                    attributes=(ValueObjectAttribute(name="cell", type="string"),),
                ),
            ),
        ),
        ValueObject(
            name="tags",
            column="tags",
            multiplicity="many",
            attributes=(ValueObjectAttribute(name="label", type="string"),),
        ),
        ValueObject(
            name="core",
            column="core",
            nullable=False,
            attributes=(ValueObjectAttribute(name="serial", type="string"),),
        ),
    ),
)
_VO_META = Metamodel(entities=(_VO_ENTITY,))


def _require_metadata(model: AcceptedMetamodel, entity: Entity) -> EntityMetadata:
    metadata = model.entity(EntityIdentity(entity.namespace, entity.name))
    assert metadata is not None
    return metadata


_VO_MODEL = corpus_models.accepted_model(_VO_META)
_VO_METADATA = _require_metadata(_VO_MODEL, _VO_ENTITY)


def test_validate_write_assignment_accepts_a_well_formed_nested_value_object() -> None:
    document: dict[str, object] = {
        "note": "n",
        "detail": {"hint": "h"},
        "grid": [{"cell": "a"}],
    }
    inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "spec", document)  # no raise


def test_validate_write_assignment_rejects_a_many_value_object_non_list() -> None:
    with pytest.raises(inheritance.WriteAssignmentError, match="must bind a list of documents"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "tags", "not-a-list")


def test_validate_write_assignment_rejects_a_missing_required_attribute() -> None:
    document: dict[str, object] = {"detail": {"hint": "h"}}
    with pytest.raises(inheritance.WriteAssignmentError, match="required attribute is absent"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "spec", document)


def test_validate_write_assignment_rejects_a_missing_required_nested_value_object() -> None:
    document: dict[str, object] = {"note": "n"}
    with pytest.raises(inheritance.WriteAssignmentError, match="required value object is absent"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "spec", document)


def test_validate_write_assignment_rejects_a_nested_many_element_type_mismatch() -> None:
    # The offending leaf's path threads through a NESTED `cardinality: many`
    # member's own bracket-indexed element (`spec.grid[0].cell`) — the shared
    # walk's (`parallax.core.metamodel._vo_document`) own index-prefixing.
    document: dict[str, object] = {
        "note": "n",
        "detail": {"hint": "h"},
        "grid": [{"cell": 42}],
    }
    with pytest.raises(inheritance.WriteAssignmentError, match=r"spec\.grid\[0\]\.cell"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "spec", document)


def test_validate_write_assignment_rejects_a_top_level_many_element_type_mismatch() -> None:
    # A TOP-level `cardinality: many` member's own element violation paths
    # bracket-first, with no leading dot (`Gadget.tags[0].label`).
    with pytest.raises(inheritance.WriteAssignmentError, match=r"tags\[0\]\.label"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "tags", [{"label": 42}])


# --------------------------------------------------------------------------- #
# The nullable-gated `None`-assignment refusal: a                             #
# `None` assignment's nullability-aware handling, direct against the shared   #
# check (`test_where_verbs.py` / `test_write_instructions.py` pin the same    #
# fix through the typed and serialized callers respectively).                 #
# --------------------------------------------------------------------------- #
def test_validate_write_assignment_rejects_none_for_a_non_nullable_value_object() -> None:
    # `core` is `nullable: false` (unlike `spec`/`tags` above) -- an explicit
    # `None` assignment must be refused the SAME way a missing required value
    # object is, reusing `vo_document_violation`'s own `"value-object-
    # missing"` wording rather than forking new text.
    with pytest.raises(inheritance.WriteAssignmentError, match="required value object is absent"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "core", None)


def test_validate_write_assignment_accepts_none_for_a_nullable_value_object() -> None:
    # `spec` is `nullable: true` -- an explicit `None` is a legal clearing
    # assignment, never itself a structural violation.
    inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "spec", None)  # no raise


def test_validate_write_assignment_rejects_none_for_a_non_nullable_scalar() -> None:
    # `code` declares no `nullable: true` -- an explicit `None` assignment
    # must be refused too (the scalar branch's own analogue): a guard of
    # `value is not None and not _type_matches(...)` would let a
    # `None` value bypass validation entirely, regardless of nullability.
    with pytest.raises(inheritance.WriteAssignmentError, match="required attribute is absent"):
        inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "code", None)


def test_validate_write_assignment_accepts_none_for_a_nullable_scalar() -> None:
    # `nickname` is `nullable: true` -- an explicit `None` is a legal
    # clearing assignment, mirroring `write_validate`'s own null short-
    # circuit for a nullable attribute.
    inheritance.validate_write_assignment(_VO_MODEL, _VO_METADATA, "nickname", None)  # no raise


# --------------------------------------------------------------------------- #
# The predicate-write assignment check and the keyed-write-row check enforce   #
# ONE scalar value contract: exact `m-core` logical membership, not a          #
# category guess. A `Decimal` carrying more fractional digits than a           #
# `decimal(p,s)` position can represent is a non-member both entry points      #
# reject, and a representable one both accept.                                  #
# --------------------------------------------------------------------------- #
_INVOICE = identity("Invoice")
_INVOICE_ENTITY = Entity(
    name="Invoice",
    table="invoice",
    attributes=(
        Attribute(name="id", type="int64", column="id", primary_key=True),
        Attribute(name="amount", type="decimal(18,2)", column="amount"),
    ),
)
_INVOICE_DESCRIPTOR = Metamodel(entities=(_INVOICE_ENTITY,))
_INVOICE_MODEL = corpus_models.accepted_model(_INVOICE_DESCRIPTOR)
_INVOICE_METADATA = _require_metadata(_INVOICE_MODEL, _INVOICE_ENTITY)
_INVOICE_ACCEPTED = form_metamodel(
    source(
        Declaration(
            identity=_INVOICE,
            container=Table("invoice"),
            attributes=(key(_INVOICE), attribute(_INVOICE, "amount", type=DecimalType(18, 2))),
        )
    )
)


def _assignment_rejects(value: object) -> bool:
    try:
        inheritance.validate_write_assignment(_INVOICE_MODEL, _INVOICE_METADATA, "amount", value)
    except inheritance.WriteAssignmentError:
        return True
    return False


def _row_rejects(value: object) -> bool:
    metadata = _INVOICE_ACCEPTED.entity(_INVOICE)
    assert metadata is not None
    try:
        validate_write(metadata, {"id": 1, "amount": value}, _INVOICE_ACCEPTED, mutation="insert")
    except WriteRejectedError:
        return True
    return False


@pytest.mark.parametrize(
    ("value", "rejected"),
    [(Decimal("1.005"), True), (Decimal("1.00"), False)],
)
def test_both_write_entry_points_share_the_exact_scalar_type_contract(
    value: object, rejected: bool
) -> None:
    assert _assignment_rejects(value) is rejected
    assert _row_rejects(value) is rejected


# --------------------------------------------------------------------------- #
# The Model Formation Rule Set. The corpus rejection fixtures above are reused #
# here to drive the rule set, which asserts the structured                     #
# `(code, location, related)` an Issue carries rather than message text.       #
# --------------------------------------------------------------------------- #

_RULE_SET_REJECTIONS: Final[Mapping[str, IssueCode]] = {
    "m-inheritance-021-rejected-cycle": inheritance.CYCLE,
    "m-inheritance-023-rejected-concrete-without-abstract-root": (
        inheritance.CONCRETE_WITHOUT_ABSTRACT_ROOT
    ),
    "m-inheritance-024-rejected-abstract-root-with-table": (
        inheritance.TPCS_ABSTRACT_TABLE_FORBIDDEN
    ),
    "m-inheritance-026-rejected-tpcs-concrete-tag-value": (
        inheritance.TAG_ON_CONCRETE_SUBTYPE_STRATEGY
    ),
    "m-inheritance-027-rejected-duplicate-tag-value": inheritance.DUPLICATE_TAG_VALUE,
    "m-inheritance-028-rejected-inconsistent-hierarchy-table": (
        inheritance.TPH_DESCENDANT_TABLE_FORBIDDEN
    ),
    "m-inheritance-029-rejected-abstract-subtype-with-table": (
        inheritance.TPH_DESCENDANT_TABLE_FORBIDDEN
    ),
    "m-inheritance-031-rejected-tph-missing-tag-value": inheritance.MISSING_TAG_VALUE,
    "m-inheritance-032-rejected-missing-root": inheritance.MISSING_ROOT,
    "m-inheritance-121-rejected-missing-concrete-subtype": inheritance.MISSING_CONCRETE_SUBTYPE,
    "m-inheritance-098-rejected-temporal-axes-on-abstract-subtype": (
        inheritance.TEMPORAL_AXES_NOT_ROOT_OWNED
    ),
    "m-inheritance-099-rejected-temporal-axes-redeclared-on-concrete": (
        inheritance.TEMPORAL_AXES_NOT_ROOT_OWNED
    ),
    "m-inheritance-102-rejected-optlock-declaring-descendant": (
        inheritance.OPTIMISTIC_LOCKING_NOT_ROOT_OWNED
    ),
    "m-inheritance-103-rejected-optlock-second-version": (
        inheritance.OPTIMISTIC_LOCKING_NOT_ROOT_OWNED
    ),
    "m-inheritance-115-rejected-attribute-relationship-materialization-key-collision": (
        inheritance.MATERIALIZATION_KEY_COLLISION
    ),
    "m-inheritance-116-rejected-narrowed-view-materialization-key-collision": (
        inheritance.MATERIALIZATION_KEY_COLLISION
    ),
    "m-inheritance-117-rejected-family-variant-materialization-key-collision": (
        inheritance.MATERIALIZATION_KEY_COLLISION
    ),
}
"""The fixtures this module's Rule Set rejects, with the one code each yields."""

_RESOLVER_REJECTIONS: Final[Mapping[str, IssueCode]] = {
    "m-inheritance-020-rejected-unknown-parent": UNRESOLVED_ENTITY_REFERENCE,
}
"""An unknown parent is foundational reference resolution's answer, so the
model never reaches a Rule Set and no inheritance-owned code duplicates it."""

_UNREPRESENTABLE: Final[tuple[str, ...]] = (
    "m-inheritance-025-rejected-strategy-redeclared",
    "m-inheritance-030-rejected-tpcs-root-tag",
)
"""The fixtures the accepted inheritance algebra makes unconstructible: the
strategy lives on the root variant alone and the tag column lives on the
table-per-hierarchy strategy alone, so neither spelling survives adaptation and
neither reaches formation as a model to reject."""


def _formation_error(model: dict[str, Any]) -> MetamodelValidationError:
    with pytest.raises(MetamodelValidationError) as caught:
        form_metamodel(unresolved_metamodel(parse_document(model)))
    return caught.value


def _rule_issues(*declarations: Declaration) -> tuple[MetamodelIssue, ...]:
    """The inheritance issues a resolvable model is rejected with."""
    return sort_issues(inheritance.RULE_SET.validate(accepted(source(*declarations))))


def _codes(*declarations: Declaration) -> list[IssueCode]:
    return [issue.code for issue in _rule_issues(*declarations)]


def _shape(*names: str) -> ValueObjectShapeDeclaration:
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=tuple(ValueObjectAttributeDeclaration(name, type=STRING) for name in names),
    )


def _relationship(
    source: EntityIdentity, target: EntityIdentity, name: str = "details"
) -> UnresolvedDefiningRelationshipDeclaration:
    return UnresolvedDefiningRelationshipDeclaration(
        identity=RelationshipIdentity(source, name),
        cardinality=Cardinality.MANY_TO_ONE,
        join=UnresolvedRelationshipJoin(
            source=AttributeIdentity(source, "targetId"),
            target=AttributeReference(ExactEntityReference(target), "id"),
        ),
    )


def test_the_owned_issue_code_set_is_closed() -> None:
    assert sorted(inheritance.ISSUE_CODES) == [
        "inheritance-concrete-without-abstract-root",
        "inheritance-cycle",
        "inheritance-duplicate-tag-value",
        "inheritance-materialization-key-collision",
        "inheritance-member-shadowing",
        "inheritance-missing-concrete-subtype",
        "inheritance-missing-root",
        "inheritance-missing-tag-value",
        "inheritance-optimistic-locking-not-root-owned",
        "inheritance-persistence-not-root-owned",
        "inheritance-primary-key-missing",
        "inheritance-primary-key-multiple",
        "inheritance-strategy-redeclared",
        "inheritance-tag-on-concrete-subtype-strategy",
        "inheritance-temporal-axes-not-root-owned",
        "inheritance-tpcs-abstract-table-forbidden",
        "inheritance-tpcs-concrete-table-required",
        "inheritance-tph-descendant-table-forbidden",
        "inheritance-tph-root-table-required",
    ]
    assert inheritance.RULE_SET.owner == inheritance.INHERITANCE_MODULE
    assert inheritance.RULE_SET.issue_codes == inheritance.ISSUE_CODES


def test_every_corpus_rejection_fixture_is_classified() -> None:
    classified = {*_RULE_SET_REJECTIONS, *_RESOLVER_REJECTIONS, *_UNREPRESENTABLE}
    assert classified == {stem for stem, _, _ in _REJECTIONS}


@pytest.mark.parametrize(
    ("stem", "code"),
    sorted({**_RULE_SET_REJECTIONS, **_RESOLVER_REJECTIONS}.items()),
)
def test_a_rejection_fixture_forms_into_its_one_issue(stem: str, code: IssueCode) -> None:
    (model,) = [inline for name, inline, _ in _REJECTIONS if name == stem]
    assert [issue.code for issue in _formation_error(model).issues] == [code]


@pytest.mark.parametrize("stem", _UNREPRESENTABLE)
def test_an_unrepresentable_fixture_carries_no_declaration_to_reject(stem: str) -> None:
    (model,) = [inline for name, inline, _ in _REJECTIONS if name == stem]
    formed = form_metamodel(unresolved_metamodel(parse_document(model)))
    for entity in formed.entities:
        match entity.inheritance:
            case AbstractRoot(strategy):
                # A root's strategy is the only place one exists, and the
                # table-per-concrete-subtype variant carries no tag column.
                assert isinstance(strategy, TablePerConcreteSubtype | TablePerHierarchy)
            case ConcreteSubtype() | AbstractSubtype():
                assert not hasattr(entity.inheritance, "strategy")
            case None:
                pass


@pytest.mark.parametrize("path", _MODEL_FILES, ids=lambda path: cast("Path", path).stem)
def test_every_corpus_model_satisfies_the_family_invariants(path: Path) -> None:
    document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    candidate = parse_document(cast("dict[str, object]", document))
    formed = form_metamodel(unresolved_metamodel(candidate))
    assert inheritance.view(formed).entity(formed.entities[0].identity) is not None


def test_a_cycle_is_reported_once_from_its_canonically_first_member() -> None:
    (model,) = [
        inline for name, inline, _ in _REJECTIONS if name == "m-inheritance-021-rejected-cycle"
    ]
    (issue,) = _formation_error(model).issues
    assert issue.location == EntityLocation(EntityIdentity(None, "Paw"))
    assert issue.related == (EntityLocation(EntityIdentity(None, "Pet")),)


def test_independent_families_coexist_in_one_model() -> None:
    formed = form_metamodel(unresolved_metamodel(parse_document(_INDEPENDENT_FAMILIES)))
    facet = inheritance.view(formed)
    views = {
        entity.identity.name: found
        for entity in formed.entities
        if (found := facet.entity(entity.identity)) is not None
    }
    assert {name: view.root.name for name, view in views.items()} == {
        "Payment": "Payment",
        "CardPayment": "Payment",
        "Document": "Document",
        "Invoice": "Document",
    }
    assert views["CardPayment"].strategy == TablePerHierarchy("kind")
    assert views["Invoice"].strategy == TablePerConcreteSubtype()


def test_a_rootless_family_is_reported_beside_a_rooted_one() -> None:
    model: dict[str, Any] = {
        "entities": [
            *_INDEPENDENT_FAMILIES["entities"],
            {
                "name": "Folder",
                "table": "folder",
                "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
            },
            {
                "name": "Archive",
                "inheritance": {"role": "abstract-subtype", "parent": "Folder"},
                "attributes": [{"name": "label", "type": "string", "nullable": True}],
            },
            {
                "name": "Receipt",
                "table": "receipt",
                "inheritance": {"role": "concrete-subtype", "parent": "Folder"},
                "attributes": [{"name": "scan", "type": "string", "nullable": True}],
            },
        ]
    }
    assert sorted(issue.code for issue in _formation_error(model).issues) == [
        inheritance.CONCRETE_WITHOUT_ABSTRACT_ROOT,
        inheritance.MISSING_ROOT,
    ]


def test_a_descendant_axis_is_located_at_the_axis_it_declares() -> None:
    (model,) = [
        inline
        for name, inline, _ in _REJECTIONS
        if name == "m-inheritance-098-rejected-temporal-axes-on-abstract-subtype"
    ]
    (issue,) = _formation_error(model).issues
    assert issue.location == AxisLocation(
        EntityIdentity(None, "Pet"), TemporalDimension.TRANSACTION_TIME
    )
    assert issue.related == (EntityLocation(EntityIdentity(None, "Animal")),)


def test_a_model_without_participants_reports_nothing() -> None:
    plain = identity("Plain")
    assert _codes(Declaration(identity=plain, attributes=(key(plain),))) == []


# --------------------------------------------------------------------------- #
# Family invariants the corpus carries no inline-model fixture for.            #
# --------------------------------------------------------------------------- #

_ROOT = identity("Ledger")
_MID = identity("Journal")
_LEAF = identity("Entry")
_SIBLING = identity("Note")
_SHARED_TABLE: Final = Table("ledger")


def _hierarchy(
    *,
    root_container: Table | None = _SHARED_TABLE,
    root_attributes: tuple[Any, ...] | None = None,
) -> Declaration:
    return Declaration(
        identity=_ROOT,
        container=root_container,
        attributes=(key(_ROOT),) if root_attributes is None else root_attributes,
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )


def _concrete(
    entity: EntityIdentity,
    *,
    parent: EntityIdentity = _ROOT,
    tag_value: str | None = "entry",
    **members: Any,
) -> Declaration:
    return Declaration(
        identity=entity,
        inheritance=ConcreteSubtype(ExactEntityReference(parent), tag_value),
        **members,
    )


def test_a_table_per_hierarchy_root_declares_the_shared_container() -> None:
    issues = _rule_issues(_hierarchy(root_container=None), _concrete(_LEAF))
    assert [issue.code for issue in issues] == [inheritance.TPH_ROOT_TABLE_REQUIRED]
    assert issues[0].location == EntityLocation(_ROOT)


def test_a_table_per_concrete_subtype_concrete_declares_its_own_container() -> None:
    issues = _rule_issues(
        Declaration(
            identity=_ROOT,
            attributes=(key(_ROOT),),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        _concrete(_LEAF, tag_value=None),
    )
    assert [issue.code for issue in issues] == [inheritance.TPCS_CONCRETE_TABLE_REQUIRED]
    assert issues[0].location == EntityLocation(_LEAF)


def test_a_family_of_abstract_positions_alone_owns_no_rows() -> None:
    # Every other family rule passes — one root, a resolvable parent, the shared
    # container on the root, and no concrete subtype to want a tag value. Only
    # concrete subtypes own rows, so this family's every position resolves over the
    # empty effective concrete set, and the defect is reported at its root.
    issues = _rule_issues(
        _hierarchy(),
        Declaration(identity=_LEAF, inheritance=AbstractSubtype(ExactEntityReference(_ROOT))),
    )
    assert [issue.code for issue in issues] == [inheritance.MISSING_CONCRETE_SUBTYPE]
    assert issues[0].location == EntityLocation(_ROOT)


def test_a_family_keeps_one_concrete_and_says_nothing() -> None:
    # The partial-family boundary: composing SOME of a family's concrete leaves is
    # legal, so one concrete beside an abstract subtype is an accepted model.
    assert (
        _codes(
            _hierarchy(),
            Declaration(identity=_LEAF, inheritance=AbstractSubtype(ExactEntityReference(_ROOT))),
            _concrete(identity("Twig"), parent=_LEAF),
        )
        == []
    )


def test_each_family_answers_the_concrete_membership_rule_for_itself() -> None:
    # A complete neighbour does not answer for a concrete-less family, exactly as it
    # does not answer for a rootless one.
    other_root = identity("Journal")
    issues = _rule_issues(
        _hierarchy(),
        _concrete(_LEAF),
        Declaration(
            identity=other_root,
            attributes=(key(other_root),),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
    )
    assert [issue.code for issue in issues] == [inheritance.MISSING_CONCRETE_SUBTYPE]
    assert issues[0].location == EntityLocation(other_root)


def test_a_family_without_a_primary_key_is_unidentifiable_at_every_position() -> None:
    issues = _rule_issues(_hierarchy(root_attributes=()), _concrete(_LEAF))
    assert [issue.code for issue in issues] == [inheritance.PRIMARY_KEY_MISSING] * 2
    assert [issue.location for issue in issues] == [
        EntityLocation(_LEAF),
        EntityLocation(_ROOT),
    ]


def test_a_descendant_key_makes_its_own_chain_carry_two() -> None:
    issues = _rule_issues(_hierarchy(), _concrete(_LEAF, attributes=(key(_LEAF, "entryId"),)))
    assert [issue.code for issue in issues] == [inheritance.PRIMARY_KEY_MULTIPLE]
    assert issues[0].location == EntityLocation(_LEAF)
    assert issues[0].related == (
        AttributeLocation(key(_ROOT).identity),
        AttributeLocation(key(_LEAF, "entryId").identity),
    )


def test_a_descendant_declares_no_persistence_mode() -> None:
    issues = _rule_issues(_hierarchy(), _concrete(_LEAF, persistence=PersistenceMode.READ_ONLY))
    assert [issue.code for issue in issues] == [inheritance.PERSISTENCE_NOT_ROOT_OWNED]
    assert issues[0].location == EntityLocation(_LEAF)
    assert issues[0].related == (EntityLocation(_ROOT),)


def test_a_root_declared_persistence_mode_is_accepted() -> None:
    assert (
        _codes(
            Declaration(
                identity=_ROOT,
                container=Table("ledger"),
                persistence=PersistenceMode.READ_ONLY,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            _concrete(_LEAF),
        )
        == []
    )


def test_a_descendant_may_not_redeclare_an_ancestor_member() -> None:
    issues = _rule_issues(
        _hierarchy(root_attributes=(key(_ROOT), attribute(_ROOT, "label", type=STRING))),
        _concrete(_LEAF, attributes=(attribute(_LEAF, "label", type=STRING),)),
    )
    assert [issue.code for issue in issues] == [
        inheritance.MATERIALIZATION_KEY_COLLISION,
        inheritance.MEMBER_SHADOWING,
    ]
    shadowing = next(issue for issue in issues if issue.code == inheritance.MEMBER_SHADOWING)
    assert shadowing.location == AttributeLocation(attribute(_LEAF, "label").identity)
    assert shadowing.related == (AttributeLocation(attribute(_ROOT, "label").identity),)


def test_shadowing_crosses_member_categories() -> None:
    issues = _rule_issues(
        _hierarchy(root_attributes=(key(_ROOT), attribute(_ROOT, "label", type=STRING))),
        _concrete(
            _LEAF,
            value_objects=(
                ValueObjectOccurrenceDeclaration(
                    name="label", storage=Column("label"), shape=_shape("text")
                ),
            ),
        ),
    )
    assert [issue.code for issue in issues] == [
        inheritance.MATERIALIZATION_KEY_COLLISION,
        inheritance.MEMBER_SHADOWING,
    ]
    shadowing = next(issue for issue in issues if issue.code == inheritance.MEMBER_SHADOWING)
    assert shadowing.location == ValueObjectLocation(ValueObjectIdentity(_LEAF, ("label",)))
    assert shadowing.related == (AttributeLocation(attribute(_ROOT, "label").identity),)


def test_shadowing_names_the_nearest_ancestor_that_declares_the_member() -> None:
    issues = _rule_issues(
        _hierarchy(root_attributes=(key(_ROOT), attribute(_ROOT, "label", type=STRING))),
        Declaration(
            identity=_MID,
            attributes=(attribute(_MID, "label", type=STRING),),
            inheritance=AbstractSubtype(ExactEntityReference(_ROOT)),
        ),
        _concrete(_LEAF, parent=_MID, attributes=(attribute(_LEAF, "label", type=STRING),)),
    )
    assert [(issue.code, issue.location, issue.related) for issue in issues] == [
        (
            inheritance.MATERIALIZATION_KEY_COLLISION,
            AttributeLocation(attribute(_LEAF, "label").identity),
            (AttributeLocation(attribute(_ROOT, "label").identity),),
        ),
        (
            inheritance.MEMBER_SHADOWING,
            AttributeLocation(attribute(_LEAF, "label").identity),
            (AttributeLocation(attribute(_MID, "label").identity),),
        ),
        (
            inheritance.MATERIALIZATION_KEY_COLLISION,
            AttributeLocation(attribute(_MID, "label").identity),
            (AttributeLocation(attribute(_ROOT, "label").identity),),
        ),
        (
            inheritance.MEMBER_SHADOWING,
            AttributeLocation(attribute(_MID, "label").identity),
            (AttributeLocation(attribute(_ROOT, "label").identity),),
        ),
    ]


def test_disjoint_sibling_branches_may_reuse_a_name() -> None:
    assert (
        _codes(
            _hierarchy(),
            _concrete(
                _LEAF,
                attributes=(attribute(_LEAF, "label", type=STRING, column="entry_label"),),
            ),
            _concrete(
                _SIBLING,
                tag_value="note",
                attributes=(attribute(_SIBLING, "label", type=STRING, column="note_label"),),
            ),
        )
        == []
    )


def test_table_per_concrete_subtype_siblings_may_reuse_a_physical_column() -> None:
    assert (
        _codes(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=_LEAF,
                container=Table("entry"),
                attributes=(attribute(_LEAF, "label", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
            ),
            Declaration(
                identity=_SIBLING,
                container=Table("note"),
                attributes=(attribute(_SIBLING, "label", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
            ),
        )
        == []
    )


def test_value_object_storage_may_match_a_relationship_rendered_name() -> None:
    owner = identity("Owner")
    target = identity("Target")
    profile = ValueObjectOccurrenceDeclaration(
        name="profile", storage=Column("details"), shape=_shape("label")
    )
    assert (
        _codes(
            Declaration(
                identity=owner,
                attributes=(key(owner), attribute(owner, "targetId")),
                relationships=(_relationship(owner, target),),
                value_objects=(profile,),
            ),
            Declaration(identity=target, attributes=(key(target),)),
        )
        == []
    )


def test_attribute_column_cannot_match_a_relationship_rendered_name() -> None:
    owner = identity("Owner")
    target = identity("Target")
    details = attribute(owner, "detailsText", type=STRING, column="details")
    issues = _rule_issues(
        Declaration(
            identity=owner,
            attributes=(key(owner), attribute(owner, "targetId"), details),
            relationships=(_relationship(owner, target),),
        ),
        Declaration(identity=target, attributes=(key(target),)),
    )
    assert [issue.code for issue in issues] == [inheritance.MATERIALIZATION_KEY_COLLISION]
    assert issues[0].location == RelationshipLocation(RelationshipIdentity(owner, "details"))
    assert issues[0].related == (AttributeLocation(details.identity),)


def test_attribute_column_cannot_occupy_a_narrowed_relationship_namespace() -> None:
    owner = identity("Owner")
    target = identity("Target")
    narrowed_key = attribute(owner, "dogDetails", type=STRING, column="details[Dog]")
    issues = _rule_issues(
        Declaration(
            identity=owner,
            attributes=(key(owner), attribute(owner, "targetId"), narrowed_key),
            relationships=(_relationship(owner, target),),
        ),
        Declaration(identity=target, attributes=(key(target),)),
    )
    assert [issue.code for issue in issues] == [inheritance.MATERIALIZATION_KEY_COLLISION]
    assert issues[0].location == AttributeLocation(narrowed_key.identity)
    assert issues[0].related == (RelationshipLocation(RelationshipIdentity(owner, "details")),)


def test_value_object_storage_may_match_the_synthetic_family_variant_key() -> None:
    profile = ValueObjectOccurrenceDeclaration(
        name="profile", storage=Column("familyVariant"), shape=_shape("label")
    )
    assert (
        _codes(
            Declaration(
                identity=_ROOT,
                container=Table("ledger"),
                attributes=(key(_ROOT),),
                value_objects=(profile,),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            _concrete(_LEAF),
        )
        == []
    )


def test_family_variant_is_reserved_from_rendered_member_names() -> None:
    profile = ValueObjectOccurrenceDeclaration(
        name="familyVariant", storage=Column("profile"), shape=_shape("label")
    )
    issues = _rule_issues(
        Declaration(
            identity=_ROOT,
            container=Table("ledger"),
            attributes=(key(_ROOT),),
            value_objects=(profile,),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        _concrete(_LEAF),
    )
    assert [issue.code for issue in issues] == [inheritance.MATERIALIZATION_KEY_COLLISION]
    assert issues[0].location == ValueObjectLocation(ValueObjectIdentity(_ROOT, ("familyVariant",)))
    assert issues[0].related == (EntityLocation(_ROOT),)


def test_a_shared_tag_value_is_reported_against_the_later_claimant() -> None:
    issues = _rule_issues(
        _hierarchy(),
        _concrete(_LEAF, tag_value="same"),
        _concrete(_SIBLING, tag_value="same"),
    )
    assert [issue.code for issue in issues] == [inheritance.DUPLICATE_TAG_VALUE]
    assert issues[0].location == EntityLocation(_SIBLING)
    assert issues[0].related == (EntityLocation(_LEAF),)


def test_the_report_is_the_same_whichever_order_a_frontend_enumerates() -> None:
    root = _hierarchy(root_attributes=(key(_ROOT), attribute(_ROOT, "label", type=STRING)))
    leaf = _concrete(
        _LEAF,
        attributes=(attribute(_LEAF, "label", type=STRING), key(_LEAF, "entryId")),
        persistence=PersistenceMode.READ_ONLY,
    )
    sibling = _concrete(_SIBLING, tag_value="note")
    orders = (
        (root, leaf, sibling),
        (sibling, leaf, root),
        (leaf, root, sibling),
    )
    reports = {tuple(_rule_issues(*permutation)) for permutation in orders}
    assert len(reports) == 1
    assert [issue.code for issue in next(iter(reports))] == [
        inheritance.PERSISTENCE_NOT_ROOT_OWNED,
        inheritance.PRIMARY_KEY_MULTIPLE,
        inheritance.MATERIALIZATION_KEY_COLLISION,
        inheritance.MEMBER_SHADOWING,
    ]
