from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.core import (
    Attr,
    Bitemporal,
    DomainModel,
    MetamodelValidationError,
    TxTemporal,
    attr,
    index,
)
from parallax.core.internal.metamodel import AttributeLocation, IndexLocation
from parallax.core.introspection import AttributeIdentity, EntityIdentity, IndexIdentity
from parallax.descriptor import domain_model_from_document

_TARIFF = EntityIdentity("tariffs", "Tariff")


def _transaction_time_model(component: str) -> DomainModel:
    class Tariff(
        TxTemporal,
        namespace="tariffs",
        table="tariff",
        indices=(index("tariff_audit", "code", component),),
    ):
        id: Attr[int] = attr(primary_key=True)
        code: Attr[str] = attr(max_length=32)
        rate: Attr[Decimal] = attr(precision=12, scale=2)

    return DomainModel(Tariff)


def _bitemporal_model(component: str) -> DomainModel:
    class Tariff(
        Bitemporal,
        namespace="tariffs",
        table="tariff",
        indices=(index("tariff_audit", "code", component),),
    ):
        id: Attr[int] = attr(primary_key=True)
        code: Attr[str] = attr(max_length=32)
        rate: Attr[Decimal] = attr(precision=12, scale=2)

    return DomainModel(Tariff)


def _document_model(profile: str, component: str) -> DomainModel:
    return domain_model_from_document(
        {
            "entity": {
                "namespace": "tariffs",
                "name": "Tariff",
                "table": "tariff",
                "temporality": profile,
                "attributes": [
                    {"name": "id", "type": "int64", "primaryKey": True},
                    {"name": "code", "type": "string", "maxLength": 32},
                    {"name": "rate", "type": "numeric(12,2)"},
                ],
                "indices": [{"name": "tariff_audit", "attributes": ["code", component]}],
            }
        }
    )


@pytest.mark.parametrize(
    ("class_model", "profile", "python_name", "endpoint"),
    [
        (_transaction_time_model, "transaction-time", "tx_start", "txStart"),
        (_transaction_time_model, "transaction-time", "tx_end", "txEnd"),
        (_bitemporal_model, "bitemporal", "valid_start", "validStart"),
        (_bitemporal_model, "bitemporal", "valid_end", "validEnd"),
    ],
)
def test_both_frontends_refuse_an_authored_index_naming_an_axis_endpoint(
    class_model: Callable[[str], DomainModel], profile: str, python_name: str, endpoint: str
) -> None:
    builds: tuple[Callable[[], DomainModel], ...] = (
        lambda: class_model(python_name),
        lambda: _document_model(profile, endpoint),
    )
    for build in builds:
        with pytest.raises(MetamodelValidationError) as failure:
            build()
        (issue,) = failure.value.issues
        assert issue.code == "metamodel-index-temporal-attribute"
        assert issue.location == IndexLocation(IndexIdentity(_TARIFF, "tariff_audit"))
        assert issue.related == (AttributeLocation(AttributeIdentity(_TARIFF, endpoint)),)
