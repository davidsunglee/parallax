"""m-inheritance: the validation-time table-group projection's declaration streams."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from parallax.core import inheritance
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.inheritance import (
    AttributeTableContributor,
    InheritanceTableGroup,
    TableGroupContributor,
    TopLevelValueObjectTableContributor,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    ValueObjectMetadata,
)
from tests.unit._metamodel_support import (
    Declaration,
    Source,
    accepted,
    attribute,
    identity,
    key,
    source,
)
from tests.unit.core._dormant_family_support import (
    DORMANT,
    DORMANT_CHILD,
    LIVE,
    ROOT,
    dormant_family,
)

type _Entry = tuple[str, EntityIdentity, str]

_TAG: Final[_Entry] = ("tag", ROOT, "kind")


def _group(model: Source, owner: EntityIdentity) -> InheritanceTableGroup:
    (group,) = (
        group
        for group in inheritance.project_table_groups(accepted(model))
        if group.mapping_owner == owner
    )
    return group


def _entry(contributor: TableGroupContributor) -> _Entry:
    match contributor:
        case AttributeTableContributor(attribute):
            kind = "key" if isinstance(attribute.primary_key, PrimaryKey) else "attribute"
            return (kind, attribute.identity.entity, attribute.identity.name)
        case TopLevelValueObjectTableContributor(value_object, _):
            return ("document", value_object.entity, value_object.path[-1])
        case _:
            return ("tag", contributor.root, contributor.column.name)


def _category_passes(
    attributes: Sequence[AttributeMetadata], value_objects: Sequence[ValueObjectMetadata]
) -> list[_Entry]:
    """The diagnostic category passes over a compiled family stream."""
    keyed = [
        ("key", member.identity.entity, member.identity.name)
        for member in attributes
        if isinstance(member.primary_key, PrimaryKey)
    ]
    rest = [
        ("attribute", member.identity.entity, member.identity.name)
        for member in attributes
        if not isinstance(member.primary_key, PrimaryKey)
    ]
    documents = [
        ("document", member.identity.entity, member.identity.path[-1]) for member in value_objects
    ]
    return [*keyed, _TAG, *rest, *documents]


def test_a_shared_table_group_passes_over_the_compiled_family_stream() -> None:
    model = dormant_family("tph")
    group = _group(model, ROOT)
    family = inheritance.view(form_metamodel(model)).family(ROOT)
    assert family is not None
    expected: list[_Entry] = [
        ("key", ROOT, "id"),
        _TAG,
        ("attribute", ROOT, "title"),
        ("attribute", LIVE, "liveValue"),
        ("attribute", DORMANT_CHILD, "childZeta"),
        ("attribute", DORMANT_CHILD, "childAlpha"),
        ("attribute", DORMANT, "dormantValue"),
        ("document", ROOT, "summary"),
        ("document", LIVE, "liveDetail"),
        ("document", DORMANT_CHILD, "childDetail"),
        ("document", DORMANT, "dormantDetail"),
    ]
    assert group.row_owners == (LIVE,)
    assert [_entry(contributor) for contributor in group.declaration_contributors] == expected
    assert _category_passes(family.attributes, family.value_objects) == expected


def test_a_candidate_family_without_a_concrete_streams_its_root_first() -> None:
    dormant = identity("ADormant")
    group = _group(
        source(
            Declaration(
                identity=ROOT,
                container=Table("record"),
                attributes=(key(ROOT), attribute(ROOT, "title", type=STRING)),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=dormant,
                attributes=(attribute(dormant, "dormantValue", type=STRING),),
                inheritance=AbstractSubtype(ExactEntityReference(ROOT)),
            ),
        ),
        ROOT,
    )
    assert group.row_owners == ()
    assert [_entry(contributor) for contributor in group.declaration_contributors] == [
        ("key", ROOT, "id"),
        _TAG,
        ("attribute", ROOT, "title"),
        ("attribute", dormant, "dormantValue"),
    ]


def test_a_concrete_with_a_concrete_child_contributes_once() -> None:
    child = identity("LiveChild")
    group = _group(
        source(
            Declaration(
                identity=ROOT,
                container=Table("record"),
                attributes=(key(ROOT),),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=LIVE,
                attributes=(attribute(LIVE, "liveValue", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(ROOT), "live"),
            ),
            Declaration(
                identity=child,
                attributes=(attribute(child, "childValue", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(LIVE), "child"),
            ),
        ),
        ROOT,
    )
    assert group.row_owners == (LIVE, child)
    assert [_entry(contributor) for contributor in group.declaration_contributors] == [
        ("key", ROOT, "id"),
        _TAG,
        ("attribute", LIVE, "liveValue"),
        ("attribute", child, "childValue"),
    ]
