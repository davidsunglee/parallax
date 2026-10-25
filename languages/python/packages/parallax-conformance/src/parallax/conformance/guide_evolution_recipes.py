from __future__ import annotations

from collections.abc import Callable

from parallax.conformance.guide_models import Payment
from parallax.core import Attr, ConcreteSubtype, DomainModel, attr
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import ServingModel, prepare_model
from parallax.core.read_delivery import InvalidData
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import CoordinatedEvolution, Evolution, evolve, schema_delta
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, connect

__all__ = [
    "CoordinationRequiredError",
    "GiftCardPayment",
    "adopt",
    "changes_since",
    "connect_serving",
    "edition_of_a_transaction",
    "migrate",
    "migration_for",
    "payments_this_edition_can_read",
]


def connect_serving(
    adapter: PostgresAdapter, model: DomainModel, edition: str
) -> tuple[Database[PostgresRole], ServingModel]:
    """A root serving ``edition`` of ``model``, through a Serving Model that can serve the next."""
    serving = ServingModel(prepare_model(model, edition=edition))
    return connect(adapter, serving), serving


def edition_of_a_transaction(db: ScopedDatabase) -> str:
    """The edition a transaction adopted when it opened."""
    return db.transact(lambda tx: tx.edition)


class GiftCardPayment(Payment, inheritance=ConcreteSubtype(tag_value="gift-card")):
    card_number: Attr[str] = attr(max_length=19)


def changes_since(deployed: str, release: DomainModel) -> Evolution:
    """What changes between the model deployed last, kept as a descriptor, and ``release``."""
    return evolve(model_of(domain_model_from_yaml(deployed)), model_of(release))


class CoordinationRequiredError(Exception):
    """A release whose change a live database can't take without coordinated work."""


def migration_for(deployed: str, release: DomainModel) -> tuple[str, ...]:
    """The statements that bring the database from the deployed model to ``release``."""
    evolution = changes_since(deployed, release)
    if isinstance(evolution, CoordinatedEvolution):
        raise CoordinationRequiredError(evolution.coordination_requirements)
    return schema_delta(evolution, POSTGRES).statements


def migrate(
    deployed: str, release: DomainModel, run_migration: Callable[[tuple[str, ...]], None]
) -> str:
    """Once per database: migrate it to ``release``, and return the descriptor to keep."""
    run_migration(migration_for(deployed, release))
    return export_yaml(release)


def adopt(serving: ServingModel, release: DomainModel, edition: str) -> None:
    """In every running process, once the migration has run: serve ``release`` from now on."""
    current = serving.current()
    serving.publish(prepare_model(release, edition=edition), expected=current)


def payments_this_edition_can_read(db: ScopedDatabase, order_id: int) -> list[Payment]:
    """An order's payments, leaving out rows a later edition wrote that this one can't read."""
    found = db.find(Payment.where(Payment.order_id == order_id)).checked().results()
    return [payment for payment in found if not isinstance(payment, InvalidData)]
