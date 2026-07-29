"""m-storage-layout: validation-time Table groups and physical collisions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, key, source

from parallax.conformance import case_format
from parallax.core import inheritance, storage_layout
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeLocation,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    EntityLocation,
    ExactEntityReference,
    MetamodelIssue,
    Table,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectIdentity,
    ValueObjectLocation,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    sort_issues,
)
from parallax.core.model_formation import MetamodelValidationError
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

_ROOT = identity("Ledger")
_MID = identity("Journal")
_LEAF = identity("Entry")
_SIBLING = identity("Note")
_SHARED_TABLE: Final = Table("ledger")

_REPO = case_format.find_repo_root()
_CASES = _REPO / "core" / "compatibility" / "cases"


def _shape(name: str = "text") -> ValueObjectShapeDeclaration:
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration(name, type=STRING),),
    )


def _hierarchy(*, attributes: tuple[Any, ...] | None = None) -> Declaration:
    return Declaration(
        identity=_ROOT,
        container=_SHARED_TABLE,
        attributes=(key(_ROOT),) if attributes is None else attributes,
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )


def _concrete(
    entity: EntityIdentity,
    *,
    parent: EntityIdentity = _ROOT,
    tag_value: str = "entry",
    **members: Any,
) -> Declaration:
    return Declaration(
        identity=entity,
        inheritance=ConcreteSubtype(ExactEntityReference(parent), tag_value),
        **members,
    )


def _rule_issues(*declarations: Declaration) -> tuple[MetamodelIssue, ...]:
    candidate = accepted(source(*declarations))
    return sort_issues(storage_layout.RULE_SET.validate(candidate))


def _storage_rejection_cases() -> list[tuple[str, Mapping[str, object], str]]:
    found: list[tuple[str, Mapping[str, object], str]] = []
    for path in sorted(_CASES.glob("m-storage-layout-*-rejected-*.yaml")):
        loaded = case_format.safe_load_yaml(Path(path).read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        document = cast("dict[str, Any]", loaded)
        when = document.get("when")
        if not isinstance(when, dict) or "model" not in when:
            continue
        then_value = document["then"]
        assert isinstance(then_value, dict)
        then = cast("dict[str, Any]", then_value)
        found.append(
            (
                path.stem,
                cast("Mapping[str, object]", when["model"]),
                str(then["rejectedRule"]),
            )
        )
    return found


_REJECTIONS = _storage_rejection_cases()


def test_the_owned_issue_code_set_is_closed() -> None:
    assert (
        frozenset(
            {
                "storage-layout-table-mapping-collision",
                "storage-layout-column-collision",
            }
        )
        == storage_layout.ISSUE_CODES
    )
    assert storage_layout.RULE_SET.owner == storage_layout.STORAGE_LAYOUT_MODULE
    assert storage_layout.RULE_SET.issue_codes == storage_layout.ISSUE_CODES


def test_standalone_attribute_and_document_claims_share_one_column_registry() -> None:
    plain = identity("Plain")
    scalar = attribute(plain, "profileText", type=STRING, column="profile")
    document = ValueObjectOccurrenceDeclaration(
        name="profileDocument", storage=Column("profile"), shape=_shape()
    )
    (issue,) = _rule_issues(
        Declaration(
            identity=plain,
            container=Table("plain"),
            attributes=(key(plain), scalar),
            value_objects=(document,),
        )
    )
    assert issue.code == storage_layout.COLUMN_COLLISION
    assert issue.location == ValueObjectLocation(ValueObjectIdentity(plain, ("profileDocument",)))
    assert issue.related == (AttributeLocation(scalar.identity),)


def test_two_standalone_documents_cannot_claim_one_column() -> None:
    plain = identity("Plain")
    first = ValueObjectOccurrenceDeclaration(
        name="mailingAddress", storage=Column("contact"), shape=_shape("street")
    )
    second = ValueObjectOccurrenceDeclaration(
        name="billingAddress", storage=Column("contact"), shape=_shape("street")
    )
    (issue,) = _rule_issues(
        Declaration(
            identity=plain,
            container=Table("plain"),
            attributes=(key(plain),),
            value_objects=(first, second),
        )
    )
    assert issue.location == ValueObjectLocation(ValueObjectIdentity(plain, ("billingAddress",)))
    assert issue.related == (ValueObjectLocation(ValueObjectIdentity(plain, ("mailingAddress",))),)


def test_tph_siblings_are_contributors_within_one_mapping_owner() -> None:
    groups = inheritance.project_table_groups(
        accepted(
            source(
                _hierarchy(),
                _concrete(
                    _LEAF,
                    attributes=(attribute(_LEAF, "entryLabel", type=STRING, column="label"),),
                ),
                _concrete(
                    _SIBLING,
                    tag_value="note",
                    attributes=(attribute(_SIBLING, "noteLabel", type=STRING, column="label"),),
                ),
            )
        )
    )
    assert len(groups) == 1
    assert groups[0].mapping_owner == _ROOT
    assert groups[0].row_owners == (_LEAF, _SIBLING)
    (issue,) = _rule_issues(
        _hierarchy(),
        _concrete(
            _LEAF,
            attributes=(attribute(_LEAF, "entryLabel", type=STRING, column="label"),),
        ),
        _concrete(
            _SIBLING,
            tag_value="note",
            attributes=(attribute(_SIBLING, "noteLabel", type=STRING, column="label"),),
        ),
    )
    assert issue.code == storage_layout.COLUMN_COLLISION
    assert issue.location == AttributeLocation(
        attribute(_SIBLING, "noteLabel", column="label").identity
    )
    assert issue.related == (
        AttributeLocation(attribute(_LEAF, "entryLabel", column="label").identity),
    )


def test_tph_tag_claim_precedes_remaining_attribute_claims_diagnostically() -> None:
    tag_attribute = attribute(_ROOT, "kind", type=STRING)
    (issue,) = _rule_issues(
        _hierarchy(attributes=(key(_ROOT), tag_attribute)),
        _concrete(_LEAF),
    )
    assert issue.code == storage_layout.COLUMN_COLLISION
    assert issue.location == AttributeLocation(tag_attribute.identity)
    assert issue.related == (EntityLocation(_ROOT),)


def test_tpcs_inherited_and_local_contributors_collide_within_one_concrete_table() -> None:
    document = ValueObjectOccurrenceDeclaration(
        name="accountDocument", storage=Column("account_data"), shape=_shape("name")
    )
    (issue,) = _rule_issues(
        Declaration(
            identity=_ROOT,
            attributes=(key(_ROOT), attribute(_ROOT, "accountRef", column="account_data")),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
        Declaration(
            identity=_LEAF,
            container=Table("entry"),
            value_objects=(document,),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
        ),
    )
    assert issue.code == storage_layout.COLUMN_COLLISION
    assert issue.location == ValueObjectLocation(ValueObjectIdentity(_LEAF, ("accountDocument",)))
    assert issue.related == (
        AttributeLocation(attribute(_ROOT, "accountRef", column="account_data").identity),
    )


def test_distinct_tpcs_tables_may_reuse_a_column_spelling() -> None:
    assert (
        _rule_issues(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=_LEAF,
                container=Table("entry"),
                attributes=(attribute(_LEAF, "entryLabel", type=STRING, column="label"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
            ),
            Declaration(
                identity=_SIBLING,
                container=Table("note"),
                attributes=(attribute(_SIBLING, "noteLabel", type=STRING, column="label"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
            ),
        )
        == ()
    )


def test_later_independent_same_table_owners_relate_to_the_canonical_first_owner() -> None:
    first = identity("First")
    second = identity("Second")
    third = identity("Third")
    declarations = (
        Declaration(
            identity=third,
            container=Table("shared"),
            attributes=(key(third, "thirdId"),),
        ),
        Declaration(
            identity=second,
            container=Table("shared"),
            attributes=(key(second, "secondId"),),
        ),
        Declaration(
            identity=first,
            container=Table("shared"),
            attributes=(key(first, "firstId"),),
        ),
    )
    issues = _rule_issues(*declarations)
    assert [(issue.location, issue.related) for issue in issues] == [
        (EntityLocation(second), (EntityLocation(first),)),
        (EntityLocation(third), (EntityLocation(first),)),
    ]
    assert {issue.code for issue in issues} == {storage_layout.TABLE_MAPPING_COLLISION}


def test_multiply_owned_table_skips_secondary_column_validation() -> None:
    first = identity("First")
    second = identity("Second")
    duplicate = attribute(second, "otherId", column="second_id")
    issues = _rule_issues(
        Declaration(
            identity=first,
            container=Table("shared"),
            attributes=(key(first, "firstId"),),
        ),
        Declaration(
            identity=second,
            container=Table("shared"),
            attributes=(key(second, "secondId"), duplicate),
        ),
    )
    assert [issue.code for issue in issues] == [storage_layout.TABLE_MAPPING_COLLISION]


def test_mapping_collisions_precede_earlier_unique_table_column_collisions() -> None:
    column_owner = identity("AColumnOwner")
    first_table_owner = identity("BFirstTableOwner")
    second_table_owner = identity("CSecondTableOwner")
    third_table_owner = identity("DThirdTableOwner")
    document = ValueObjectOccurrenceDeclaration(
        name="payload",
        storage=Column("value"),
        shape=_shape(),
    )
    candidate = accepted(
        source(
            Declaration(
                identity=column_owner,
                container=Table("column_collision"),
                attributes=(
                    key(column_owner),
                    attribute(column_owner, "value", type=STRING),
                ),
                value_objects=(document,),
            ),
            Declaration(
                identity=first_table_owner,
                container=Table("mapping_collision"),
                attributes=(key(first_table_owner),),
            ),
            Declaration(
                identity=second_table_owner,
                container=Table("mapping_collision"),
                attributes=(key(second_table_owner),),
            ),
            Declaration(
                identity=third_table_owner,
                container=Table("mapping_collision"),
                attributes=(key(third_table_owner),),
            ),
        )
    )
    issues = storage_layout.RULE_SET.validate(candidate)
    assert [issue.code for issue in issues] == [
        storage_layout.TABLE_MAPPING_COLLISION,
        storage_layout.TABLE_MAPPING_COLLISION,
        storage_layout.COLUMN_COLLISION,
    ]
    assert [(issue.location, issue.related) for issue in issues] == [
        (
            EntityLocation(second_table_owner),
            (EntityLocation(first_table_owner),),
        ),
        (
            EntityLocation(third_table_owner),
            (EntityLocation(first_table_owner),),
        ),
        (
            ValueObjectLocation(ValueObjectIdentity(column_owner, ("payload",))),
            (AttributeLocation(attribute(column_owner, "value").identity),),
        ),
    ]


def test_interleaved_two_table_owner_collisions_follow_canonical_owner_order() -> None:
    first_a = identity("AFirst")
    first_b = identity("BFirst")
    later_b = identity("CLaterB")
    later_a = identity("DLaterA")
    issues = _rule_issues(
        Declaration(
            identity=later_a,
            container=Table("table_a"),
            attributes=(key(later_a),),
        ),
        Declaration(
            identity=first_b,
            container=Table("table_b"),
            attributes=(key(first_b),),
        ),
        Declaration(
            identity=later_b,
            container=Table("table_b"),
            attributes=(key(later_b),),
        ),
        Declaration(
            identity=first_a,
            container=Table("table_a"),
            attributes=(key(first_a),),
        ),
    )
    assert [(issue.location, issue.related) for issue in issues] == [
        (EntityLocation(later_b), (EntityLocation(first_b),)),
        (EntityLocation(later_a), (EntityLocation(first_a),)),
    ]


def test_standalone_tph_and_tpcs_owners_compete_in_one_table_claim_stream() -> None:
    standalone = identity("AStandalone")
    tph_root = identity("BHierarchy")
    tph_concrete = identity("BHierarchyRow")
    tpcs_root = identity("CConcreteRoot")
    tpcs_concrete = identity("CConcreteRow")
    issues = _rule_issues(
        Declaration(
            identity=tpcs_concrete,
            container=Table("shared"),
            inheritance=ConcreteSubtype(ExactEntityReference(tpcs_root), None),
        ),
        Declaration(
            identity=tph_concrete,
            inheritance=ConcreteSubtype(ExactEntityReference(tph_root), "row"),
        ),
        Declaration(
            identity=tph_root,
            container=Table("shared"),
            attributes=(key(tph_root),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=standalone,
            container=Table("shared"),
            attributes=(key(standalone),),
        ),
        Declaration(
            identity=tpcs_root,
            attributes=(key(tpcs_root),),
            inheritance=AbstractRoot(TablePerConcreteSubtype()),
        ),
    )
    assert [(issue.location, issue.related) for issue in issues] == [
        (EntityLocation(tph_root), (EntityLocation(standalone),)),
        (EntityLocation(tpcs_concrete), (EntityLocation(standalone),)),
    ]
    assert {issue.code for issue in issues} == {storage_layout.TABLE_MAPPING_COLLISION}


def test_malformed_topology_is_omitted_without_storage_layout_guessing() -> None:
    orphan = identity("Orphan")
    candidate = accepted(
        source(
            Declaration(
                identity=orphan,
                container=Table("orphan"),
                attributes=(key(orphan),),
                inheritance=AbstractSubtype(ExactEntityReference(identity("Plain"))),
            ),
            Declaration(
                identity=identity("Plain"),
                container=Table("plain"),
                attributes=(key(identity("Plain")),),
            ),
        )
    )
    groups = inheritance.project_table_groups(candidate)
    assert [group.mapping_owner for group in groups] == [identity("Plain")]
    assert storage_layout.RULE_SET.validate(candidate) == ()


def test_a_container_less_hierarchy_root_projects_no_table_group() -> None:
    # A table-per-hierarchy family maps its whole family onto the ROOT's own
    # Table, so a root declaring none has no mapping to project at all — the
    # Inheritance rules own that diagnosis, and this projection stays silent
    # rather than inventing a Table for the family's concretes.
    candidate = accepted(
        source(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            _concrete(_LEAF),
        )
    )
    assert inheritance.project_table_groups(candidate) == ()


def test_a_container_less_concrete_subtype_projects_no_table_group() -> None:
    # The table-per-concrete-subtype analogue: each concrete owns its OWN
    # Table, so one declaring none contributes no mapping owner.
    candidate = accepted(
        source(
            Declaration(
                identity=_ROOT,
                attributes=(key(_ROOT),),
                inheritance=AbstractRoot(TablePerConcreteSubtype()),
            ),
            Declaration(
                identity=_LEAF,
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), None),
            ),
        )
    )
    assert inheritance.project_table_groups(candidate) == ()


@pytest.mark.parametrize(
    ("stem", "inline", "expected"),
    _REJECTIONS,
    ids=[item[0] for item in _REJECTIONS],
)
def test_storage_layout_corpus_rejections_form_into_their_owned_issue(
    stem: str, inline: Mapping[str, object], expected: str
) -> None:
    with pytest.raises(MetamodelValidationError) as caught:
        form_metamodel(unresolved_metamodel(parse_document(inline)))
    assert [issue.code for issue in caught.value.issues] == [expected], stem


def test_the_storage_layout_rejection_fixture_set_is_complete() -> None:
    assert [stem.split("-rejected", 1)[0] for stem, _, _ in _REJECTIONS] == [
        "m-storage-layout-001",
        "m-storage-layout-002",
        "m-storage-layout-003",
        "m-storage-layout-004",
        "m-storage-layout-005",
    ]
