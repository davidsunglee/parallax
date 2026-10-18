"""A ``Holder`` family whose relationships reach an abstract subtype with no
concrete descendant. Exported names carry no leading underscore; privacy is
this module's."""

from __future__ import annotations

from typing import Literal

from parallax.conformance.models import accepted_model
from parallax.core.metamodel import Metamodel


def dormant_target_model(strategy: Literal["tph", "tpcs"]) -> Metamodel:
    """``Holder`` relates to ``Empty``, an abstract subtype with no concrete
    descendant beside the concrete sibling ``Leaf``."""
    shared = strategy == "tph"
    root: dict[str, object] = {
        "name": "Thing",
        "namespace": "probe",
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy" if shared else "table-per-concrete-subtype",
            **({"tag": {"column": "kind"}} if shared else {}),
        },
        "attributes": [
            {"name": "id", "type": "int64", "primaryKey": True},
            {"name": "title", "type": "string", "maxLength": 16},
            {"name": "holderId", "type": "int64", "nullable": True},
        ],
        "relationships": [
            {
                "name": "holder",
                "cardinality": "many-to-one",
                "join": {
                    "source": "holderId",
                    "target": {"entity": "probe.Holder", "attribute": "id"},
                },
            }
        ],
        **({"table": "thing"} if shared else {}),
    }
    leaf: dict[str, object] = {
        "name": "Leaf",
        "namespace": "probe",
        "inheritance": {
            "role": "concrete-subtype",
            "parent": "probe.Thing",
            **({"tagValue": "leaf"} if shared else {}),
        },
        **({} if shared else {"table": "leaf"}),
    }
    return accepted_model(
        {
            "entities": [
                root,
                leaf,
                {
                    "name": "Empty",
                    "namespace": "probe",
                    "inheritance": {"role": "abstract-subtype", "parent": "probe.Thing"},
                },
                {
                    "name": "Holder",
                    "namespace": "probe",
                    "table": "holder",
                    "attributes": [
                        {"name": "id", "type": "int64", "primaryKey": True},
                        {"name": "emptyId", "type": "int64", "nullable": True},
                        {"name": "nextId", "type": "int64", "nullable": True},
                    ],
                    "relationships": [
                        {
                            "name": "empties",
                            "cardinality": "one-to-many",
                            "join": {
                                "source": "id",
                                "target": {"entity": "probe.Empty", "attribute": "holderId"},
                            },
                        },
                        {
                            "name": "empty",
                            "cardinality": "many-to-one",
                            "join": {
                                "source": "emptyId",
                                "target": {"entity": "probe.Empty", "attribute": "id"},
                            },
                        },
                        {
                            "name": "next",
                            "cardinality": "many-to-one",
                            "join": {
                                "source": "nextId",
                                "target": {"entity": "probe.Holder", "attribute": "id"},
                            },
                        },
                    ],
                },
            ]
        }
    )
