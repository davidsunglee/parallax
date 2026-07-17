"""m-inheritance: family model, effective concrete sets, and descriptor rejection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import inheritance
from parallax.core.descriptor import (
    AsOfAttribute,
    Attribute,
    Entity,
    Inheritance,
    Metamodel,
    NestedValueObject,
    ValueObject,
    ValueObjectAttribute,
    deserialize,
)

pytestmark = pytest.mark.unit

_REPO = case_format.find_repo_root()
_MODELS = corpus_models.load_models(_REPO / "core" / "compatibility" / "models")
_CASES = _REPO / "core" / "compatibility" / "cases"


def _descriptor_rejection_cases() -> list[tuple[str, dict[str, Any], str]]:
    found: list[tuple[str, dict[str, Any], str]] = []
    # `*` (not `0*`): the D-25 root-ownership witnesses (m-inheritance-102/103)
    # are the first `when.model` cases numbered past 099, so the glob must not
    # assume every id stays in the 0xx range.
    for path in sorted(_CASES.glob("m-inheritance-*-rejected-*.yaml")):
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
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
# family-wide property; only the root may declare `asOfAttributes`, and every #
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
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    mid = Entity(
        name="Mid",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
    )
    leaf = Entity(
        name="Leaf",
        table="root_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Mid", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    return Metamodel(entities=(root, mid, leaf))


def test_declaring_entity_resolves_to_the_family_root_from_every_position() -> None:
    meta = _synthetic_temporal_family()
    for name in ("Root", "Mid", "Leaf"):
        declaring = inheritance.declaring_entity(meta, meta.entity(name))
        assert declaring.name == "Root", name
        assert declaring.as_of_attributes == meta.entity("Root").as_of_attributes


def test_declaring_entity_is_the_entity_itself_outside_a_family() -> None:
    # A non-inheritance temporal entity remains unaffected: `declaring_entity`
    # is a strict identity for it (m-inheritance only applies within a family).
    plain = Entity(
        name="Balance",
        table="balance",
        attributes=(Attribute(name="id", type="int64", column="bal_id", primary_key=True),),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
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
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=_minimal_attrs(),
    )
    pet = Entity(
        name="Pet",
        inheritance=Inheritance(role="abstract-subtype", parent="Animal"),
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
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
        as_of_attributes=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )
    deposit = Entity(
        name="DepositRate",
        table="deposit_rate",
        inheritance=Inheritance(role="concrete-subtype", parent="Rate"),
        attributes=(Attribute(name="grade", type="string", column="grade"),),
        as_of_attributes=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
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
        table="animal",
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
    mutability="transactional",
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
                    cardinality="many",
                    attributes=(ValueObjectAttribute(name="cell", type="string"),),
                ),
            ),
        ),
        ValueObject(
            name="tags",
            column="tags",
            cardinality="many",
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
