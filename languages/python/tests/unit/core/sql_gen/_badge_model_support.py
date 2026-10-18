"""Holder/Badge models whose one-to-one target is proven only by a unique key.

A holder reaches its badge by the badge's nullable ``holderId``, not by the
badge's own key, so whether the hop reaches at most one row depends on the
declared ``badge_holder`` index alone. Exported names carry no leading
underscore; privacy is this module's.
"""

from __future__ import annotations

from parallax.core.metamodel import Metamodel
from parallax.descriptor._ingest import ingest_document
from parallax.descriptor._records import (
    Attribute,
    DefiningRelationship,
    Entity,
    Index,
    RelationshipJoin,
    RelationshipTarget,
)
from parallax.descriptor._records import Metamodel as Records
from tests.unit._corpus_model_support import formed


def badge_model(*, unique: bool) -> Metamodel:
    holder = Entity(
        name="Holder",
        table="holder",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        relationships=(
            DefiningRelationship(
                name="badge",
                cardinality="one-to-one",
                join=RelationshipJoin(
                    source="id", target=RelationshipTarget(entity="Badge", attribute="holderId")
                ),
            ),
        ),
    )
    badge = Entity(
        name="Badge",
        table="badge",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="holderId", type="int64", column="holder_id", nullable=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="badge_holder", attributes=("holderId",), unique=unique),),
    )
    return formed(Records(entities=(holder, badge)))


def temporal_badge_model(*, unique: bool) -> Metamodel:
    """:func:`badge_model` with a bitemporal badge, whose logical key the
    holder's correlation does not fix."""
    key = {"name": "id", "type": "int64", "primaryKey": True}
    return formed(
        ingest_document(
            {
                "entities": [
                    {
                        "name": "Holder",
                        "table": "holder",
                        "attributes": [key],
                        "relationships": [
                            {
                                "name": "badge",
                                "cardinality": "one-to-one",
                                "join": {
                                    "source": "id",
                                    "target": {"entity": "Badge", "attribute": "holderId"},
                                },
                            }
                        ],
                    },
                    {
                        "name": "Badge",
                        "table": "badge",
                        "temporality": "bitemporal",
                        "attributes": [
                            key,
                            {"name": "holderId", "type": "int64", "nullable": True},
                        ],
                        "indices": [
                            {"name": "badge_holder", "attributes": ["holderId"], "unique": unique}
                        ],
                    },
                ]
            }
        )
    )
