from __future__ import annotations

from collections.abc import Mapping, Sequence

from parallax.conformance._actual_wire import ActualWireProjection
from parallax.conformance._mechanism import envelope
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.conformance._mechanism.model_facts import case_entity
from parallax.core import inheritance, storage_layout
from parallax.core.db_port import MappingRow
from parallax.core.dialect import scalar_result
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Multiplicity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import ObjectQueryNode

__all__ = ["flat_rows", "omitted_value_objects"]

type _Member = AttributeMetadata | ValueObjectMetadata
type _MemberColumns = Mapping[str, tuple[tuple[str, _Member], ...]]


def flat_rows(
    model: AcceptedMetamodel,
    query: ObjectQueryNode,
    roots: Sequence[object],
    *,
    value_objects: bool,
) -> list[MappingRow]:
    """Published result positions as the physically keyed rows a case states.

    A read step's ``expectRows`` states every column its projection occupies
    (``value_objects=True``); ``then.rows`` states the scalar columns alone. The
    corpus spells either in the projection's own physical keys while a Wire root
    is keyed by declared member name, so each member's value is re-keyed by the
    column it occupies. It is a rendering of what production published, never a
    second traversal, and it reads nothing about how the roots arrived: an eager
    result and a delivery's concatenated pages render identically.

    An ABSTRACT position publishes one CONCRETE node per row, so the read's own
    projection is the position's fixed superset rather than the addressed
    position's applicable members: each row carries every column the superset
    places, ``null`` where the row's own branch contributes none, plus the
    ``_type`` the node itself publishes (`m-case-format` *Read
    targeting*). Rendering the branch's members alone would DROP what the read
    published; rendering the raw tag column would report a storage value no node
    carries, which is exactly why the format names the variant instead. A concrete
    position states its own members, and that same key where a family participant
    published it.
    """
    columns, family = _read_projection(model, query, value_objects=value_objects)
    superset = (
        dict.fromkeys(column for options in columns.values() for column, _member in options)
        if family
        else None
    )
    projection = ActualWireProjection(model)
    return [
        _projected_row(model, projection, columns, superset, envelope.graph_root(root) or {})
        for root in roots
    ]


def omitted_value_objects(
    model: AcceptedMetamodel, query: ObjectQueryNode
) -> frozenset[ValueObjectIdentity]:
    """The top-level occurrences ``value_objects=False`` leaves out of ``query``'s rows."""
    columns, _abstract = _read_projection(model, query, value_objects=True)
    return frozenset(
        member.identity
        for options in columns.values()
        for _column, member in options
        if not isinstance(member, AttributeMetadata)
    )


def _projected_row(
    model: AcceptedMetamodel,
    projection: ActualWireProjection,
    columns: _MemberColumns,
    superset: Mapping[str, None] | None,
    node: Mapping[str, object],
) -> MappingRow:
    """One published node as its projection's row.

    ``superset`` holds an abstract position's superset columns, each ``null``
    until the node fills it, and is ``None`` for a concrete read. A sibling's
    column reusing a member name renders nothing here: the node's own member
    stands at that name, and it is a Value Object the row leaves out. No member or
    Column can spell the synthetic type key, so a node carrying it is a
    participant's.
    """
    node_type = node.get(inheritance.WIRE_TYPE_KEY)
    selected = _concrete_members(model, node) if superset is not None and node else None
    published: dict[str, object] = {}
    for name, value in node.items():
        options = columns.get(name, ())
        if selected is not None:
            options = tuple(option for option in options if option[1].identity in selected)
        if not options:
            continue
        if len(options) != 1:
            raise UnclassifiedEngineError(
                f"{node_type!r} does not select one declaration for published member {name!r}"
            )
        column, member = options[0]
        if value is None:
            published[column] = None
        elif isinstance(member, AttributeMetadata):
            published[column] = projection.published_scalar(member, value)
        else:
            published[column] = projection.published_value_object(member, value)
    if not node:
        return published
    if superset is not None:
        return {**superset, **published, inheritance.WIRE_TYPE_KEY: node_type}
    if node_type is not None:
        published[inheritance.WIRE_TYPE_KEY] = node_type
    return published


def _concrete_members(
    model: AcceptedMetamodel, node: Mapping[str, object]
) -> frozenset[MemberIdentity]:
    node_type = node.get(inheritance.WIRE_TYPE_KEY)
    if not isinstance(node_type, str):
        raise UnclassifiedEngineError(
            "an abstract-position read publishes a concrete node carrying "
            f"`_type`; this one published {sorted(node)}"
        )
    entity = case_entity(model, node_type)
    view = inheritance.inheritance_facet_of(model).entity(entity.identity)
    if view is None:  # pragma: no cover - every accepted Entity has a view
        raise UnclassifiedEngineError(f"{entity.identity.canonical}: no inheritance position")
    return frozenset(
        member.identity for member in (*view.applicable_attributes, *view.applicable_value_objects)
    )


def _read_projection(
    model: AcceptedMetamodel, query: ObjectQueryNode, *, value_objects: bool
) -> tuple[_MemberColumns, bool]:
    """The columns ``query`` projects, and whether it reads an abstract position.

    Abstractness is the ADDRESSED position's own role, exactly as it is where
    production decides to project the discriminator, while the column set follows
    the query's resolved narrowing: narrowing an abstract read shrinks its
    superset without making the read concrete.
    """
    facet = inheritance.inheritance_facet_of(model)
    entity = case_entity(model, query.target.canonical)
    view = facet.entity(entity.identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}, False
    if not isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype)):
        return (
            _member_columns(
                model,
                (entity.identity,),
                view.applicable_attributes,
                view.applicable_value_objects if value_objects else (),
            ),
            False,
        )
    position: inheritance.InheritancePositionView = view
    if query.narrow_to:
        narrowed = facet.position(
            [case_entity(model, spelling).identity for spelling in query.narrow_to]
        )
        if narrowed is None:  # pragma: no cover - a read whose roots exist resolved it
            raise UnclassifiedEngineError(
                f"narrowing {query.target.canonical!r} to {list(query.narrow_to)} resolves "
                "no position of one inheritance family"
            )
        position = narrowed
    return (
        _member_columns(
            model,
            position.concrete_subtypes,
            position.superset_attributes,
            position.superset_value_objects if value_objects else (),
        ),
        True,
    )


def _member_columns(
    model: AcceptedMetamodel,
    concretes: Sequence[EntityIdentity],
    attributes: Sequence[AttributeMetadata],
    value_objects: Sequence[ValueObjectMetadata],
) -> _MemberColumns:
    """Each member name paired with its own column, in projection order."""
    columns: dict[str, dict[MemberIdentity, tuple[str, _Member]]] = {}
    for attribute in attributes:
        columns.setdefault(attribute.identity.name, {})[attribute.identity] = (
            _attribute_column(model, concretes, attribute),
            attribute,
        )
    for occurrence in value_objects:
        columns.setdefault(occurrence.identity.path[-1], {})[occurrence.identity] = (
            occurrence.storage.name,
            occurrence,
        )
    return {name: tuple(options.values()) for name, options in columns.items()}


def _attribute_column(
    model: AcceptedMetamodel, concretes: Sequence[EntityIdentity], attribute: AttributeMetadata
) -> str:
    """The key ``attribute`` is stated under.

    A scalar in a Column of its own takes that Column's result spelling, the one
    the read's own select list states for it. A collection and a document-resident
    member have no scalar result cell to take one from, so they keep the member's
    storage name whatever their type.
    """
    name = attribute.storage.name
    if attribute.multiplicity is Multiplicity.MANY or not _in_own_column(
        model, concretes, attribute
    ):
        return name
    return scalar_result(name, attribute.type).publication_key


def _in_own_column(
    model: AcceptedMetamodel, concretes: Sequence[EntityIdentity], attribute: AttributeMetadata
) -> bool:
    facet = storage_layout.storage_layout_facet_of(model)
    return any(
        isinstance(view.layout.placement(attribute.identity), storage_layout.DirectColumn)
        for concrete in concretes
        if (view := facet.entity(concrete)) is not None
    )
