"""m-inheritance: family model, the Rule Set, and descriptor rejection."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, key, source

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.descriptor import (
    AsOfAxisMetadata,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
    deserialize,
    parse_document,
    unresolved_metamodel,
)
from parallax.core.metamodel import (
    MODEL_ROOT,
    UNRESOLVED_ENTITY_REFERENCE,
    AbstractRoot,
    AbstractSubtype,
    AttributeLocation,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    EntityLocation,
    ExactEntityReference,
    IssueCode,
    MetamodelIssue,
    PersistenceMode,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    TemporalDimension,
    ValueObjectAttributeDeclaration,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    sort_issues,
)
from parallax.core.metamodel import AsOfAxisLocation as AxisLocation
from parallax.core.model_formation import MetamodelValidationError

pytestmark = pytest.mark.unit

_REPO = case_format.find_repo_root()
_MODELS = corpus_models.load_models(_REPO / "core" / "compatibility" / "models")
_CASES = _REPO / "core" / "compatibility" / "cases"
_MODEL_FILES = sorted((_REPO / "core" / "compatibility" / "models").glob("*.yaml"))


def _descriptor_rejection_cases() -> list[tuple[str, dict[str, Any], str]]:
    found: list[tuple[str, dict[str, Any], str]] = []
    # `*` (not `0*`): the D-25 root-ownership witnesses (m-inheritance-102/103)
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


def test_every_descriptor_rejection_case_is_covered() -> None:
    # 17 inline-descriptor inheritance rejection cases carry `when.model` (13
    # original + the two temporal-axis root-ownership witnesses,
    # m-inheritance-098/099, + the two optimistic-locking root-ownership
    # witnesses, m-inheritance-102/103).
    assert len(_REJECTIONS) == 17


@pytest.mark.parametrize("stem, model, rule", _REJECTIONS, ids=[r[0] for r in _REJECTIONS])
def test_rejected_descriptor_classifies_with_its_corpus_rule(
    stem: str, model: dict[str, Any], rule: str
) -> None:
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(deserialize(model))
    assert caught.value.rule == rule


def test_valid_inheritance_family_passes_validation() -> None:
    inheritance.validate(_MODELS["animal"])  # no raise
    inheritance.validate(_MODELS["document"])
    inheritance.validate(_MODELS["vehicle"])


def test_non_inheritance_descriptor_validates_trivially() -> None:
    inheritance.validate(_MODELS["account"])  # no participants, no raise


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ("Animal", ("Cat", "Dog", "WildBoar")),
        ("Pet", ("Cat", "Dog")),
        ("Dog", ("Dog",)),
        ("Person", ("Person",)),
    ],
)
def test_effective_concrete_subtypes_is_alphabetical(
    position: str, expected: tuple[str, ...]
) -> None:
    assert inheritance.effective_concrete_subtypes(_MODELS["animal"], position) == expected


def test_family_of_reports_the_single_root_and_strategy() -> None:
    family = inheritance.family_of(_MODELS["animal"])
    assert family.root is not None
    assert family.root.name == "Animal"
    assert family.strategy == "table-per-hierarchy"


def test_family_of_is_empty_without_participants() -> None:
    family = inheritance.family_of(_MODELS["account"])
    assert family.root is None
    assert family.strategy is None
    assert family.participants == ()


def test_inheritance_error_carries_rule_and_entity() -> None:
    error = inheritance.InheritanceError("inheritance-cycle", "boom", entity="Pet")
    assert error.rule == "inheritance-cycle"
    assert error.entity == "Pet"


def test_ancestor_chain_orders_root_first_then_deeper_abstract_nodes() -> None:
    animal = _MODELS["animal"]
    assert [e.name for e in inheritance.ancestor_chain(animal, ("Cat", "Dog"))] == [
        "Animal",
        "Pet",
    ]
    # WildBoar's own chain is just the root (a sibling branch directly under it).
    assert [e.name for e in inheritance.ancestor_chain(animal, ("WildBoar",))] == ["Animal"]


def test_family_attributes_widens_across_the_whole_family() -> None:
    animal = _MODELS["animal"]
    names = {attr.name for attr in inheritance.family_attributes(animal, animal.entity("Dog"))}
    assert names == {"id", "name", "ownerId", "licenseId", "barkVolume", "indoor", "tuskLength"}


def test_family_attributes_is_the_entitys_own_attributes_outside_a_family() -> None:
    account = _MODELS["account"]
    entity = account.entity("Account")
    assert inheritance.family_attributes(account, entity) == entity.attributes


def test_family_root_resolves_the_abstract_root() -> None:
    animal = _MODELS["animal"]
    assert inheritance.family_root(animal, animal.entity("Dog")).name == "Animal"
    assert inheritance.family_root(animal, animal.entity("Animal")).name == "Animal"


def test_family_root_raises_on_a_malformed_ancestry() -> None:
    # A concrete-subtype whose parent chain cycles rather than reaching a root.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    cyclic = Metamodel(
        entities=(
            Entity(
                name="A",
                table="a",
                inheritance=Inheritance(role="concrete-subtype", parent="B"),
                attributes=attrs,
            ),
            Entity(
                name="B",
                table="b",
                inheritance=Inheritance(role="concrete-subtype", parent="A"),
                attributes=attrs,
            ),
        )
    )
    with pytest.raises(ValueError, match="no resolvable inheritance root"):
        inheritance.family_root(cyclic, cyclic.entity("A"))


def test_concrete_descendants_terminates_on_a_cyclic_family() -> None:
    # A malformed (cyclic) family: `concrete_descendants` must still terminate.
    attrs = (Attribute(name="id", type="int64", column="id", primary_key=True),)
    cyclic = Metamodel(
        entities=(
            Entity(
                name="A",
                table="a",
                inheritance=Inheritance(role="concrete-subtype", parent="B"),
                attributes=attrs,
            ),
            Entity(
                name="B",
                table="b",
                inheritance=Inheritance(role="concrete-subtype", parent="A"),
                attributes=attrs,
            ),
        )
    )
    assert inheritance.family_of(cyclic).concrete_descendants("A") == frozenset({"A", "B"})


# --------------------------------------------------------------------------- #
# Binding decision (COR-3 Phase 7 review remediation, P3/P4): temporality is a #
# family-wide property; only the root may declare `asOfAxes`, and every       #
# descendant — abstract-subtype or concrete-subtype — inherits exactly that   #
# set. `declaring_entity` always resolves to the family root; a non-root      #
# participant that declares its own axes is rejected pre-SQL.                 #
# --------------------------------------------------------------------------- #
def _synthetic_temporal_family() -> Metamodel:
    """A THREE-level TPH family — Root (temporal) -> Mid (abstract-subtype) ->
    Leaf (concrete) — proving `declaring_entity` resolves to the root from
    EVERY position in the chain, not just the immediate parent."""
    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="tx_start", type="timestamp", column="in_z"),
            Attribute(name="tx_end", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    mid = Entity(
        name="Mid",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Mid", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, mid, leaf))


def test_declaring_entity_resolves_to_the_family_root_from_every_position() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        declaring = inheritance.declaring_entity(meta, meta.entity(name))
        assert declaring.name == "Root", name
        assert declaring.as_of_axes == meta.entity("Root").as_of_axes


def test_declaring_entity_is_the_entity_itself_outside_a_family() -> None:
    # A non-inheritance temporal entity remains unaffected: `declaring_entity`
    # is a strict identity for it (m-inheritance only applies within a family).
    plain = Entity(
        name="Balance",
        table="balance",
        attributes=(
            Attribute(name="id", type="int64", column="bal_id", primary_key=True),
            Attribute(name="tx_start", type="timestamp", column="in_z"),
            Attribute(name="tx_end", type="timestamp", column="out_z"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    meta = Metamodel(entities=(plain,))
    assert inheritance.declaring_entity(meta, plain) is plain


def _minimal_attrs() -> tuple[Attribute, ...]:
    return (Attribute(name="id", type="int64", column="id", primary_key=True),)


def test_reject_descendant_temporal_axes_under_a_non_temporal_root() -> None:
    # A non-temporal TPH root with an abstract-subtype that declares its own axes.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    dog = Entity(
        name="Dog",
        table="animal",
        inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog"),
        attributes=(Attribute(name="barkVolume", type="int32", column="bark_volume"),),
    )
    meta = Metamodel(entities=(root, pet, dog))
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_temporal_axes_under_a_temporal_root() -> None:
    # A temporal TPCS root whose concrete subtype adds its own second axis.
    root = Entity(
        name="Rate",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=_minimal_attrs(),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
            ),
        ),
    )
    deposit = Entity(
        name="DepositRate",
        table="deposit_rate",
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
        attributes=(Attribute(name="grade", type="string", column="grade"),),
        as_of_axes=(
            AsOfAxisMetadata(
                dimension="validTime", start_attribute="valid_start", end_attribute="valid_end"
            ),
        ),
    )
    meta = Metamodel(entities=(root, deposit))
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-temporal-axes-not-root-owned"
    assert caught.value.entity == "DepositRate"


def test_temporal_root_and_root_owned_axes_still_validate_cleanly() -> None:
    # A well-formed family (axes declared ONLY on the root) passes validation —
    # the new invariant must not reject the corpus's own root-declared families.
    inheritance.validate(_MODELS["rate"])
    inheritance.validate(_MODELS["instrument"])


def test_reject_descendant_optimistic_locking_under_a_non_versioned_root() -> None:
    # D-25 / ADR 0027: a non-versioned TPH root with an abstract-subtype that
    # declares its own optimisticLocking attribute.
    root = Entity(
        name="Animal",
        table="animal",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        attributes=(
            Attribute(name="revision", type="int32", column="revision", optimistic_locking=True),
        ),
    )
    dog = Entity(
        name="Dog",
        inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="dog"),
        attributes=(Attribute(name="barkVolume", type="int32", column="bark_volume"),),
    )
    meta = Metamodel(entities=(root, pet, dog))
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-optimistic-locking-not-root-owned"
    assert caught.value.entity == "Pet"


def test_reject_descendant_optimistic_locking_under_a_versioned_root() -> None:
    # A versioned TPCS root whose concrete subtype adds a SECOND version
    # attribute of its own, under a different name.
    root = Entity(
        name="Appliance",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            *_minimal_attrs(),
            Attribute(name="version", type="int32", column="version", optimistic_locking=True),
        ),
    )
    fridge = Entity(
        name="Fridge",
        table="fridge",
        inheritance=Inheritance(role="concrete-subtype", parent="Appliance"),
        attributes=(
            Attribute(name="revision", type="int32", column="revision", optimistic_locking=True),
        ),
    )
    meta = Metamodel(entities=(root, fridge))
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.validate(meta)
    assert caught.value.rule == "inheritance-optimistic-locking-not-root-owned"
    assert caught.value.entity == "Fridge"


def test_versioned_root_and_root_owned_version_still_validates_cleanly() -> None:
    # A well-formed family (the version declared ONLY on the root) passes
    # validation — the new invariant must not reject the corpus's own
    # root-declared versioned families.
    inheritance.validate(_MODELS["vehicle"])
    inheritance.validate(_MODELS["appliance"])


# --------------------------------------------------------------------------- #
# `reject_predicate_write` (COR-3 Phase 8 increment 5): a predicate-selected  #
# (set-based) write on ANY inheritance-family entity is unsupported before    #
# any SQL, the SAME classification a keyless keyed write raises.              #
# --------------------------------------------------------------------------- #
def test_reject_predicate_write_raises_for_a_concrete_subtype() -> None:
    animal = _MODELS["animal"]
    dog = animal.entity("Dog")
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.reject_predicate_write(dog)
    assert caught.value.rule == "subtype-write-set-based-unsupported"
    assert caught.value.entity == "Dog"


def test_reject_predicate_write_raises_for_the_abstract_root() -> None:
    animal = _MODELS["animal"]
    root = animal.entity("Animal")
    with pytest.raises(inheritance.InheritanceError) as caught:
        inheritance.reject_predicate_write(root)
    assert caught.value.rule == "subtype-write-set-based-unsupported"


def test_reject_predicate_write_is_a_no_op_for_a_non_participant() -> None:
    account = _MODELS["account"].entity("Account")
    inheritance.reject_predicate_write(account)  # no raise


# --------------------------------------------------------------------------- #
# `validate_write_assignment`'s VALUE-OBJECT branch (confirmation-pass         #
# residual P3): the corpus/mirror `Customer.address` shape                     #
# (`test_where_verbs.py` / `test_write_instructions.py`) pins the four         #
# residual-mandated shapes (typed/serialized reject/accept) but declares no    #
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
# extend this same synthetic model for confirmation-pass residual B (round 2,  #
# `inheritance/__init__.py:667`): a `None` assignment's nullability-aware      #
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
                    nullable=True,
                    multiplicity="many",
                    attributes=(ValueObjectAttribute(name="cell", type="string"),),
                ),
            ),
        ),
        ValueObject(
            name="tags",
            column="tags",
            multiplicity="many",
            nullable=True,
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


def test_validate_write_assignment_accepts_a_well_formed_nested_value_object() -> None:
    document: dict[str, object] = {
        "note": "n",
        "detail": {"hint": "h"},
        "grid": [{"cell": "a"}],
    }
    inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "spec", document)  # no raise


def test_validate_write_assignment_rejects_a_many_value_object_non_list() -> None:
    with pytest.raises(inheritance.WriteAssignmentError, match="must bind a list of documents"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "tags", "not-a-list")


def test_validate_write_assignment_rejects_a_missing_required_attribute() -> None:
    document: dict[str, object] = {"detail": {"hint": "h"}}
    with pytest.raises(inheritance.WriteAssignmentError, match="required attribute is absent"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "spec", document)


def test_validate_write_assignment_rejects_a_missing_required_nested_value_object() -> None:
    document: dict[str, object] = {"note": "n"}
    with pytest.raises(inheritance.WriteAssignmentError, match="required value object is absent"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "spec", document)


def test_validate_write_assignment_rejects_a_nested_many_element_type_mismatch() -> None:
    # The offending leaf's path threads through a NESTED `cardinality: many`
    # member's own bracket-indexed element (`spec.grid[0].cell`) — the shared
    # walk's (`parallax.core.descriptor.vo_document`) own index-prefixing.
    document: dict[str, object] = {
        "note": "n",
        "detail": {"hint": "h"},
        "grid": [{"cell": 42}],
    }
    with pytest.raises(inheritance.WriteAssignmentError, match=r"spec\.grid\[0\]\.cell"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "spec", document)


def test_validate_write_assignment_rejects_a_top_level_many_element_type_mismatch() -> None:
    # A TOP-level `cardinality: many` member's own element violation paths
    # bracket-first, with no leading dot (`Gadget.tags[0].label`).
    with pytest.raises(inheritance.WriteAssignmentError, match=r"tags\[0\]\.label"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "tags", [{"label": 42}])


# --------------------------------------------------------------------------- #
# Confirmation-pass residual B (round 2, `inheritance/__init__.py:667`): a     #
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
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "core", None)


def test_validate_write_assignment_accepts_none_for_a_nullable_value_object() -> None:
    # `spec` is `nullable: true` -- an explicit `None` is a legal clearing
    # assignment, never itself a structural violation.
    inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "spec", None)  # no raise


def test_validate_write_assignment_rejects_none_for_a_non_nullable_scalar() -> None:
    # `code` declares no `nullable: true` -- an explicit `None` assignment
    # must be refused too (the scalar branch's own extension of residual B):
    # before the fix, `value is not None and not _type_matches(...)` let a
    # `None` value bypass validation entirely, regardless of nullability.
    with pytest.raises(inheritance.WriteAssignmentError, match="required attribute is absent"):
        inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "code", None)


def test_validate_write_assignment_accepts_none_for_a_nullable_scalar() -> None:
    # `nickname` is `nullable: true` -- an explicit `None` is a legal
    # clearing assignment, mirroring `write_validate`'s own null short-
    # circuit for a nullable attribute.
    inheritance.validate_write_assignment(_VO_META, _VO_ENTITY, "nickname", None)  # no raise


# --------------------------------------------------------------------------- #
# The Model Formation Rule Set. The corpus rejection fixtures above are reused #
# here to drive the rule set, which asserts the structured                     #
# `(code, location, related)` an Issue carries rather than message text.       #
# --------------------------------------------------------------------------- #

_RULE_SET_REJECTIONS: Final[Mapping[str, IssueCode]] = {
    "m-inheritance-021-rejected-cycle": inheritance.CYCLE,
    "m-inheritance-022-rejected-multiple-roots": inheritance.MULTIPLE_ROOTS,
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


def test_the_owned_issue_code_set_is_closed() -> None:
    assert sorted(inheritance.ISSUE_CODES) == [
        "inheritance-concrete-without-abstract-root",
        "inheritance-cycle",
        "inheritance-duplicate-tag-value",
        "inheritance-member-shadowing",
        "inheritance-missing-root",
        "inheritance-missing-tag-value",
        "inheritance-multiple-roots",
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


def test_multiple_roots_is_a_statement_about_the_whole_model() -> None:
    (model,) = [
        inline
        for name, inline, _ in _REJECTIONS
        if name == "m-inheritance-022-rejected-multiple-roots"
    ]
    (issue,) = _formation_error(model).issues
    assert issue.location == MODEL_ROOT
    assert issue.related == (
        EntityLocation(EntityIdentity(None, "Animal")),
        EntityLocation(EntityIdentity(None, "Beast")),
    )


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
    assert [issue.code for issue in issues] == [inheritance.MEMBER_SHADOWING]
    assert issues[0].location == AttributeLocation(attribute(_LEAF, "label").identity)
    assert issues[0].related == (AttributeLocation(attribute(_ROOT, "label").identity),)


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
    assert [issue.code for issue in issues] == [inheritance.MEMBER_SHADOWING]
    assert issues[0].location == ValueObjectLocation(ValueObjectIdentity(_LEAF, ("label",)))
    assert issues[0].related == (AttributeLocation(attribute(_ROOT, "label").identity),)


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
    assert [(issue.location, issue.related) for issue in issues] == [
        (
            AttributeLocation(attribute(_LEAF, "label").identity),
            (AttributeLocation(attribute(_MID, "label").identity),),
        ),
        (
            AttributeLocation(attribute(_MID, "label").identity),
            (AttributeLocation(attribute(_ROOT, "label").identity),),
        ),
    ]


def test_disjoint_sibling_branches_may_reuse_a_name() -> None:
    assert (
        _codes(
            _hierarchy(),
            _concrete(_LEAF, attributes=(attribute(_LEAF, "label", type=STRING),)),
            _concrete(
                _SIBLING,
                tag_value="note",
                attributes=(attribute(_SIBLING, "label", type=STRING),),
            ),
        )
        == []
    )


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
        inheritance.MEMBER_SHADOWING,
    ]
