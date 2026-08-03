"""One Relational Document Layout model, and its member-for-member `Columns` twin.

Both are compiled from Declarations and accepted directly, which is the idiom every
sql_gen and lowering unit suite uses: it installs exactly the facets the lane under
test reads and nothing else, so a failure names the seam rather than whole-model
formation. The corpus carries the end-to-end proof (`models/document-layout.yaml`).

The two models declare the SAME members with the same names, types, and columns
and differ only in the root's `layout`, which is what lets a suite assert the one
property the layout exists to preserve: identical logical output.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from _metamodel_support import Declaration, accepted, identity, key, source

from parallax.core import inheritance, opt_lock, relationship, storage_layout, temporal_read
from parallax.core.base import DATE, INT64, STRING, NeutralType
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Column,
    Document,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    StorageLayout,
    Table,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
    accept_metamodel,
    compile_metadata,
)

PERSON: EntityIdentity = identity("Person")
MARKER: EntityIdentity = identity("Marker")


def _nullable(name: str, neutral_type: NeutralType, column: str) -> AttributeMetadata:
    return AttributeMetadata(
        identity=AttributeIdentity(PERSON, name),
        type=neutral_type,
        storage=Column(column),
        nullable=True,
    )


_ADDRESS = ValueObjectShapeDeclaration(
    key=ValueObjectShapeKey(),
    attributes=(ValueObjectAttributeDeclaration("city", type=STRING, nullable=True),),
    value_objects=(
        NestedValueObjectOccurrenceDeclaration(
            name="geo",
            shape=ValueObjectShapeDeclaration(
                key=ValueObjectShapeKey(),
                attributes=(
                    ValueObjectAttributeDeclaration("country", type=STRING, nullable=True),
                ),
            ),
            nullable=True,
        ),
    ),
)

_TAG = ValueObjectShapeDeclaration(
    key=ValueObjectShapeKey(),
    attributes=(ValueObjectAttributeDeclaration("label", type=STRING, nullable=True),),
)


def _declarations(layout: StorageLayout | None) -> tuple[Declaration, ...]:
    return (
        Declaration(
            identity=MARKER,
            container=Table("marker"),
            layout=layout,
            attributes=(key(MARKER),),
        ),
        Declaration(
            identity=PERSON,
            container=Table("person"),
            layout=layout,
            attributes=(
                key(PERSON),
                _nullable("displayName", STRING, "display_name"),
                _nullable("score", INT64, "score"),
                _nullable("joinedOn", DATE, "joined_on"),
            ),
            value_objects=(
                ValueObjectOccurrenceDeclaration(
                    name="address", storage=Column("address"), shape=_ADDRESS, nullable=True
                ),
                ValueObjectOccurrenceDeclaration(
                    name="tags",
                    storage=Column("tags"),
                    shape=_TAG,
                    multiplicity=Multiplicity.MANY,
                ),
            ),
        ),
    )


def _accept(layout: StorageLayout | None) -> Metamodel:
    metadata = compile_metadata(accepted(source(*_declarations(layout))))
    inheritance_facet = inheritance.compile_facet(metadata)
    relationship_facet = relationship.compile_facet(metadata)
    temporal_facet = temporal_read.compile_facet(metadata, inheritance_facet)
    return accept_metamodel(
        metadata,
        {
            inheritance.FACET_KEY: inheritance_facet,
            relationship.FACET_KEY: relationship_facet,
            temporal_read.FACET_KEY: temporal_facet,
            opt_lock.FACET_KEY: opt_lock.compile_facet(metadata, inheritance_facet, temporal_facet),
            storage_layout.FACET_KEY: storage_layout.compile_facet(
                metadata, inheritance_facet, relationship_facet
            ),
        },
    )


def document_model() -> Metamodel:
    """`Person` and `Marker` under `Document` layout, both sharing the column `payload`."""
    return _accept(Document(Column("payload")))


def columns_model() -> Metamodel:
    """The same two Entities under conventional `Columns` layout."""
    return _accept(None)


def entity(model: Metamodel, name: str) -> EntityMetadata:
    """The Entity ``name`` denotes in ``model``, named as a corpus case names it."""
    for declared in model.entities:
        if declared.identity.name == name:
            return declared
    raise KeyError(name)
