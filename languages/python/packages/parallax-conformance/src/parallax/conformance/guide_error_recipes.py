from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable, Mapping

from parallax.conformance.guide_models import Customer, Price, Shipment
from parallax.core import (
    ConflictError,
    CredentialSource,
    DatabaseError,
    DomainModel,
    EditError,
    Entity,
    InvalidValueError,
    LoggingLifecycleProvider,
    MetamodelValidationError,
    NoResultFound,
    ParallaxError,
    PhysicalIndexName,
    UnsupportedError,
    UsageError,
    WritePreconditionError,
)
from parallax.evolution import SchemaDelta
from parallax.postgres import PoolOptions, PostgresAdapter, PostgresEndpoint, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, TxnContext, WireEntity, connect

__all__ = [
    "add_a_customer_unless_the_id_is_taken",
    "add_a_shipment_unless_its_tracking_number_is_taken",
    "change_a_customer_from_a_form",
    "created_index_name",
    "find_with_a_client_query",
    "http_status_for",
    "open_the_shop_database",
    "price_a_window_unless_it_is_priced",
    "problems_in_a_model",
    "run_or_retry_later",
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
    except DatabaseError as failure:
        if failure.category != "uniqueViolation":
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
    except DatabaseError as failure:
        if failure.category != "uniqueViolation":
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
    except DatabaseError as failure:
        if failure.violated_index != tracking_index:
            raise
        return False
    return True


def http_status_for(error: Exception) -> int:
    """The HTTP status a web API answers with when ``error`` escapes a request."""
    match error:
        case NoResultFound():
            return 404
        case WritePreconditionError():
            return 412
        case ConflictError():
            return 409
        case EditError() | InvalidValueError():
            return 422
        case UnsupportedError():
            return 501
        case ParallaxError(is_transient=True):
            return 503
        case _:
            return 500


def find_with_a_client_query(
    db: ScopedDatabase, document: Mapping[str, object]
) -> tuple[int, list[WireEntity] | dict[str, str]]:
    """Answer a query document a client sent: its results, or why it was refused."""
    try:
        return 200, db.wire.find(document).results()
    except InvalidValueError as refused:
        return 422, {"code": refused.code, "detail": str(refused)}
    except UsageError as refused:
        return 400, {"code": refused.code, "detail": str(refused)}


def run_or_retry_later(
    db: ScopedDatabase, job: Callable[[TxnContext], object], retry_later: Callable[[], object]
) -> None:
    """Run ``job`` in a transaction, or hand it to ``retry_later`` when a later run may succeed."""
    try:
        db.transact(job)
    except ParallaxError as failure:
        if not failure.is_transient:
            raise
        retry_later()


def open_the_shop_database(
    conninfo: str, credentials: CredentialSource, model: DomainModel
) -> Database[PostgresRole]:
    """The process's one root: a bounded pool, room for more read plans, and logging."""
    adapter = PostgresAdapter(
        writer=PostgresEndpoint(conninfo, credentials=credentials, pool=PoolOptions(max_size=20))
    )
    return connect(
        adapter,
        model,
        read_plan_cache_capacity=512,
        lifecycle_provider=LoggingLifecycleProvider(logging.getLogger("shop.database")),
    )
