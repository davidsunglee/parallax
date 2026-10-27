from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Mapping

from parallax.conformance.guide_models import Customer, Price, Shipment
from parallax.core import DomainModel, EditError, Entity, MetamodelValidationError
from parallax.core.db_error import DatabaseError, PhysicalIndexName
from parallax.core.db_port import CredentialSource
from parallax.core.execution import ExecutionFailure
from parallax.core.execution_lifecycle import LoggingLifecycleProvider
from parallax.evolution import SchemaDelta
from parallax.postgres import PoolOptions, PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, TxnContext, connect

__all__ = [
    "add_a_customer_unless_the_id_is_taken",
    "add_a_shipment_unless_its_tracking_number_is_taken",
    "change_a_customer_from_a_form",
    "created_index_name",
    "open_the_shop_database",
    "price_a_window_unless_it_is_priced",
    "problems_in_a_model",
]


def problems_in_a_model(*classes: type[Entity]) -> list[str]:
    """Each problem ``DomainModel`` finds in ``classes``, by code and message."""
    try:
        DomainModel(*classes)
    except MetamodelValidationError as rejected:
        return [f"{issue.code}: {issue.message}" for issue in rejected.issues]
    return []


def change_a_customer_from_a_form(
    db: ScopedDatabase, customer_id: int, form: Mapping[str, object]
) -> dict[str | None, str]:
    """Apply a form's changes, or answer every field the model refuses, by member name."""

    def change(tx: TxnContext) -> dict[str | None, str]:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        try:
            edited = customer.edit(**form)
        except EditError as refused:
            return {violation.member_name: violation.message for violation in refused.violations}
        tx.amend(edited)
        return {}

    return db.transact(change)


def add_a_customer_unless_the_id_is_taken(db: ScopedDatabase, customer: Customer) -> bool:
    """Insert ``customer``, or answer False when another customer already has its id."""
    try:
        db.transact(lambda tx: tx.insert(customer))
    except ExecutionFailure as failure:
        cause = failure.cause
        if not (isinstance(cause, DatabaseError) and cause.category == "uniqueViolation"):
            raise
        return False
    return True


def price_a_window_unless_it_is_priced(
    db: ScopedDatabase, price: Price, start: dt.datetime, end: dt.datetime
) -> bool:
    """Price ``price.sku`` over ``[start, end)``, or answer False where it already has one."""

    def price_unless_priced(tx: TxnContext) -> bool:
        priced = Price.where(Price.sku == price.sku).as_of_range(valid_time=(start, end))
        if tx.find(priced).results():
            return False
        tx.insert(price, valid_from=start, until=end)
        return True

    try:
        return db.transact(price_unless_priced)
    except ExecutionFailure as failure:
        cause = failure.cause
        if not (isinstance(cause, DatabaseError) and cause.category == "uniqueViolation"):
            raise
        return False


def created_index_name(rollout: SchemaDelta, entity: str, index: str) -> PhysicalIndexName:
    """The physical name ``rollout`` gave the index it created as ``index`` on ``entity``."""
    (name,) = (
        created.physical_index_name
        for created in rollout.created_indices
        if created.logical_index_identity.entity.canonical == entity
        and created.logical_index_identity.name == index
    )
    return name


def add_a_shipment_unless_its_tracking_number_is_taken(
    db: ScopedDatabase, shipment: Shipment, tracking_index: PhysicalIndexName
) -> bool:
    """Insert ``shipment``, or answer False when another shipment has its tracking number."""
    try:
        db.transact(lambda tx: tx.insert(shipment))
    except ExecutionFailure as failure:
        cause = failure.cause
        if not (
            isinstance(cause, DatabaseError)
            and cause.category == "uniqueViolation"
            and cause.violated_index == tracking_index
        ):
            raise
        return False
    return True


def open_the_shop_database(
    conninfo: str, credentials: CredentialSource, model: DomainModel
) -> Database[PostgresRole]:
    """The process's one root: a bounded pool, room for more read plans, and logging."""
    adapter = PostgresAdapter(conninfo, credentials=credentials, pool=PoolOptions(max_size=20))
    return connect(
        adapter,
        model,
        read_plan_cache_capacity=512,
        lifecycle_provider=LoggingLifecycleProvider(logging.getLogger("shop.database")),
    )
