"""Cross-surface arrangements for keyed write-value provenance cases."""

from __future__ import annotations

from parallax.conformance.vo_models import Customer
from parallax.core.base import PresentDocument
from parallax.core.entity import DomainModel, Entity
from parallax.snapshot import connect
from parallax.snapshot.handle import InvalidData

from .db_port import Read, ScriptedAdapter


def invalid_customer_root(model: DomainModel) -> Entity:
    """Read the hydratable invalid Customer used by ``invalidRoot`` cases."""
    with connect(
        ScriptedAdapter(
            Read(
                rows=[
                    {
                        "id": 6,
                        "name": "Rin",
                        "address": PresentDocument(
                            {
                                "street": "6 Kastanien Allee",
                                "city": "Berlin",
                                "geo": "unknown",
                            }
                        ),
                    }
                ]
            )
        ),
        model,
    ) as _root_db:
        db = _root_db.using_database_login()
        invalid = db.find(Customer.where(Customer.id == 6)).checked().result()
    assert isinstance(invalid, InvalidData)
    assert invalid.data is not None
    return invalid.data
