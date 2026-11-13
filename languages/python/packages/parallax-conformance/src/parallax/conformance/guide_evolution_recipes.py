from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from parallax.conformance.guide_models import Payment
from parallax.core import (
    Attr,
    ConcreteSubtype,
    DomainModel,
    InvalidData,
    ServingModel,
    attr,
    prepare_model,
)
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import CoordinatedEvolution, Evolution, evolve, schema_delta
from parallax.evolution.operations import SequenceRelocated, TableRelocated
from parallax.postgres import PostgresAdapter, PostgresBinding, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, connect

__all__ = [
    "CoordinationRequiredError",
    "Deployed",
    "GiftCardPayment",
    "adopt",
    "changes_since",
    "connect_serving",
    "edition_of_a_transaction",
    "migrate",
    "migration_for",
    "moves_in",
    "payments_this_edition_can_read",
]


def connect_serving(
    adapter: PostgresAdapter, model: DomainModel, binding: PostgresBinding, edition: str
) -> tuple[Database[PostgresRole], ServingModel]:
    """A root serving ``edition`` of ``model`` placed by ``binding``, through a
    Serving Model that can serve the next."""
    serving = ServingModel(prepare_model(model, binding=binding, edition=edition))
    return connect(adapter, serving), serving


def edition_of_a_transaction(db: ScopedDatabase) -> str:
    """The edition a transaction adopted when it opened."""
    return db.transact(lambda tx: tx.edition)


class GiftCardPayment(Payment, inheritance=ConcreteSubtype(tag_value="gift-card")):
    card_number: Attr[str] = attr(max_length=19)


@dataclass(frozen=True)
class Deployed:
    """What a database was last migrated to, kept beside it as text: the model's
    descriptor and its binding's YAML."""

    model: str
    binding: str


def changes_since(deployed: Deployed, release: DomainModel, binding: PostgresBinding) -> Evolution:
    """What changes between the model and binding deployed last and ``release``,
    placed by ``binding``."""
    return evolve(
        domain_model_from_yaml(deployed.model),
        release,
        earlier_binding=PostgresBinding.from_yaml(deployed.binding),
        later_binding=binding,
    )


class CoordinationRequiredError(Exception):
    """A release whose change a live database can't take without coordinated work."""


def migration_for(
    deployed: Deployed, release: DomainModel, binding: PostgresBinding
) -> tuple[str, ...]:
    """The statements that bring the database from the deployed model to ``release``."""
    evolution = changes_since(deployed, release, binding)
    if isinstance(evolution, CoordinatedEvolution):
        raise CoordinationRequiredError(evolution.coordination_requirements)
    return schema_delta(evolution).statements


def migrate(
    deployed: Deployed,
    release: DomainModel,
    binding: PostgresBinding,
    run_migration: Callable[[tuple[str, ...]], None],
) -> Deployed:
    """Once per database: migrate it to ``release``, and return what to keep as deployed."""
    run_migration(migration_for(deployed, release, binding))
    return Deployed(export_yaml(release), binding.to_yaml())


def adopt(
    serving: ServingModel, release: DomainModel, binding: PostgresBinding, edition: str
) -> None:
    """In every running process, once the migration has run: serve ``release`` from now on."""
    current = serving.current()
    serving.publish(prepare_model(release, binding=binding, edition=edition), expected=current)


def moves_in(evolution: Evolution) -> list[str]:
    """Each table and sequence a release moves, from where to where."""
    moves: list[str] = []
    for operation in evolution.operations:
        if isinstance(operation, TableRelocated):
            moved = operation.mapping_owner.canonical
        elif isinstance(operation, SequenceRelocated):
            moved = f"sequence {operation.allocator}"
        else:
            continue
        earlier, later = (
            ".".join((*placed.qualifier, placed.name))
            for placed in (operation.earlier, operation.later)
        )
        moves.append(f"{moved}: {earlier} -> {later}")
    return moves


def payments_this_edition_can_read(db: ScopedDatabase, order_id: int) -> list[Payment]:
    """An order's payments, leaving out rows a later edition wrote that this one can't read."""
    found = db.find(Payment.where(Payment.order_id == order_id)).checked().results()
    return [payment for payment in found if not isinstance(payment, InvalidData)]
