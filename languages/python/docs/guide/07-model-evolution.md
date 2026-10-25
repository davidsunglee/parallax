# Model evolution

Your model will change after you deploy it. Parallax can switch a running process to a
changed model without a restart, and it generates the schema change the new model needs,
but it never changes your database itself. This chapter starts with editions, the
successive models a process serves, and how a transaction uses them. It then describes
a change between two models, generates the migration for it, and rolls the new model out
to running processes, including the window when two editions run against one database.

The examples use the shop model from [Modeling](02-modeling.md) and these imports:

<!-- example: model-evolution-imports -->
```python
from collections.abc import Callable

from parallax.core import Attr, ConcreteSubtype, DomainModel, attr
from parallax.core.dialect import POSTGRES
from parallax.core.entity import model_of
from parallax.core.execution import PublicationConflictError, ServingModel, prepare_model
from parallax.core.read_delivery import InvalidData, InvalidDataError
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import (
    CoordinatedEvolution,
    Evolution,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, connect
```
<!-- /example -->

## Model Editions

Each model a root serves is a Model Edition, named by a string you choose, such as a
release number or a commit hash. `connect(adapter, model)`, as in
[Getting started](01-getting-started.md#connect), serves one edition, with a generated
name, for as long as the root is open. To be able to serve a later edition without
reconnecting, prepare the model yourself and hand the root a `ServingModel` that holds
it:

<!-- example: serve-a-model-edition -->
```python
def connect_serving(
    adapter: PostgresAdapter, model: DomainModel, edition: str
) -> tuple[Database[PostgresRole], ServingModel]:
    """A root serving ``edition`` of ``model``, through a Serving Model that can serve the next."""
    serving = ServingModel(prepare_model(model, edition=edition))
    return connect(adapter, serving), serving


def edition_of_a_transaction(db: ScopedDatabase) -> str:
    """The edition a transaction adopted when it opened."""
    return db.transact(lambda tx: tx.edition)
```
<!-- /example -->

`prepare_model` returns a `ModelSelection`: the model and its edition, with everything
Parallax derives from the model, such as how each entity's rows are read and how its
writes are planned, worked out in advance. If the model can't be prepared, it raises
there, before anything serves it, rather than on a later request. The Serving Model holds
the one selection the root serves at any moment, and only code holding the Serving Model
can replace it: holding the root doesn't let you change the model it serves.

Every execution adopts the selection held when it starts, and keeps it to the end:

- A transaction attempt adopts it before it begins, and `tx.edition` names it. A
  publication that lands while the transaction runs changes nothing for it.
- A nested `transact` that joins the transaction keeps the edition it already adopted.
  A retry is a new attempt, so it adopts whatever is held when it starts, which may be a
  newer edition.
- A standalone `find` adopts when it runs, and a stream adopts when you enter its `with`
  block and keeps that edition for every page.

Results carry the edition they were read under as `edition`, and so does an
`ExecutionFailure`. Editions are compared only for equality, never ordered, so a later
release doesn't need a "larger" name, but never give a changed model a name the Serving
Model has already served.

## Describing a change

The shop's second release accepts gift cards. It adds a concrete subtype to the
[payment family](02-modeling.md#inheritance-families), so its model is
`DomainModel(Customer, Order, Payment, CardPayment, BankTransfer, GiftCardPayment)`.
`evolve(earlier, later)` describes what changes between two models. It compares the
checked, language-neutral form of each, which `model_of` takes out of a `DomainModel`.
The earlier model is the one you deployed last, so keep a copy of it at each deployment.
`export_yaml`, from the `parallax-descriptor` distribution, writes a model as a descriptor,
and `domain_model_from_yaml` reads one back:

<!-- example: describe-a-model-change -->
```python
class GiftCardPayment(Payment, inheritance=ConcreteSubtype(tag_value="gift-card")):
    card_number: Attr[str] = attr(max_length=19)


def changes_since(deployed: str, release: DomainModel) -> Evolution:
    """What changes between the model deployed last, kept as a descriptor, and ``release``."""
    return evolve(model_of(domain_model_from_yaml(deployed)), model_of(release))
```
<!-- /example -->

`evolve` reads only the two models. It never looks at a database, so the description is
the same wherever you compute it, for example in a release check before you deploy. It
answers three questions.

**What changes?** `operations` lists each change as an Evolution Operation named in the
terms you modeled in: an entity, an attribute, a relationship, an index. Gift cards are
one operation, `ConcreteSubtypeAdded`, naming `GiftCardPayment`. Declarations are matched
by identity, which is their name, so Parallax never guesses a rename: renaming an
attribute is one removal and one addition.

**Can a live database take it?** The result is one of two types. A
`UnilateralEvolution` keeps every query and write that was valid under the earlier
model valid under the later one, and needs no destructive change to stored data or to
the schema, so it can be applied while the earlier edition keeps running. Gift cards
are unilateral. A `CoordinatedEvolution` needs more than that. Had the release also
dropped `BankTransfer` from the model, `evolve` would return one, because a query naming
`BankTransfer` would stop being valid. Its `coordination_requirements` lists each
operation that needs coordination with its reasons, each a `CoordinationReason`:
`AUTHORING_SURFACE_CHANGE_REQUIRED` when code written against the earlier model has to
change, and `DATABASE_MIGRATION_REQUIRED` when no schema change can carry the database
across without transforming stored data or staging the change. A Coordinated Evolution
is a complete description, not an error, but Parallax generates no migration for it and
prescribes no procedure: how you stage that change is your decision.

**What behaves differently?** `behavioral_impacts` lists what changes behind a surface
that stays valid. Gift cards cause one `QueryResultMembershipChanged`, on `Payment`: a
query over `Payment` can now return gift-card payments. Impacts also cover which values
an attribute admits, uniqueness, delete propagation, concurrency control, result
ordering and write capability. Each names the operations that caused it, and appears
whenever the models differ in that respect, even if no stored row would show it.

A `UnilateralEvolution` also lists `overlap_visible_operations`: the changes that let the
later edition store a value the earlier model doesn't admit. They include making an
attribute nullable, raising or removing a maximum length, and adding a subtype to a
family stored in one table. Gift cards are one, because every payment shares the
`payment` table; [Rolling out a new model](#rolling-out-a-new-model) shows what an
earlier edition does with such a row.

## Generating the schema change

`schema_delta(evolution, POSTGRES)` turns a `UnilateralEvolution` into the PostgreSQL
statements that bring a database from the earlier model to the later one. It accepts
only a `UnilateralEvolution`, so your type checker refuses a call that might hand it a
Coordinated one. A release check therefore refuses a coordinated change first:

<!-- example: generate-the-migration -->
```python
class CoordinationRequiredError(Exception):
    """A release whose change a live database can't take without coordinated work."""


def migration_for(deployed: str, release: DomainModel) -> tuple[str, ...]:
    """The statements that bring the database from the deployed model to ``release``."""
    evolution = changes_since(deployed, release)
    if isinstance(evolution, CoordinatedEvolution):
        raise CoordinationRequiredError(evolution.coordination_requirements)
    return schema_delta(evolution, POSTGRES).statements
```
<!-- /example -->

For gift cards the migration is one statement,
`alter table payment add column card_number varchar(19)`, because the family's subtypes
share one table. Provisioning a new database is the same call with `ABSENT` as the
earlier model, as [Create the tables](01-getting-started.md#create-the-tables) shows.

Parallax never runs these statements. You run them with whatever already runs your
migrations, for three reasons: generating them stays a pure computation, schema changes
aren't transactional on every database, and many processes serve one database, so
letting each root migrate on its own would have them race to change it while serving
requests. Run the statements as given:

- In the order returned, stopping at the first failure. Every prefix of that order is
  safe to apply to a database at the earlier edition, so a migration that stops partway
  leaves a database the earlier edition still works against.
- Without reordering, skipping or deduplicating them, and without adding
  `IF NOT EXISTS`. A delta describes the change from a known edition, so it is deliberately not
  idempotent: a statement that quietly did nothing would leave the later edition served
  over a schema that never received it.
- Forwards only. Parallax produces no inverse delta.

Creating a unique index checks the rows already stored: if any break the new rule, the
statement fails, and you don't publish the release. The full result of `schema_delta`
also lists each index it creates in `created_indices`, with the physical name a later
uniqueness violation reports, so keep it as a record of what each rollout created.

## Rolling out a new model

A rollout has two parts, in this order. Your deployment migrates the database once, and
then every running process publishes the new edition:

<!-- example: roll-out-a-release -->
```python
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
```
<!-- /example -->

`run_migration` is your migration tool. `migrate` returns the release's descriptor only
once the migration has run, so the model you keep as deployed is always the one the
database has.

`adopt` prepares the release before it publishes anything, so a release that can't be
prepared raises with the earlier edition still serving. `publish` replaces the held
selection only if it is still the one `adopt` found, compared as the same object rather
than by edition. If another publisher replaced it in the meantime, `publish` raises
`PublicationConflictError`, naming the selection it expected and the one it found held,
and replaces nothing; Parallax never retries a publication for you. Publishing asserts
that the database already has the schema the release needs, which is why it comes after
the migration. How each process learns that the migration has run is up to your
deployment: Parallax coordinates nothing between processes.

Once `adopt` returns, the next transaction adopts the new edition. Transactions already
running keep theirs, and the process neither restarts nor reconnects.

### The overlap window

Each process publishes on its own, so for a while some processes serve release 1 and
others release 2, against one database. That window is Edition Overlap, and draining a
single process doesn't end it. Parallax classifies what can happen in it rather than
preventing it.

Both editions work against the migrated schema, because the evolution was unilateral.
Release 1 never selects `card_number`, and its inserts leave the column empty.
Behavioral Impacts can still make the editions behave differently. For example, a
unique index created for a later release can refuse a write an earlier-edition process
makes; the database error names the index, which you can find in `created_indices`, and
Parallax doesn't retry it.

An overlap-visible change goes further: release 2 can store a row release 1 can't read.
Here, a release-1 read through `Payment` that reaches a gift-card row finds a tag naming
no subtype it knows. Release 1 treats that row as invalid stored data, so `.results()`
raises `InvalidDataError`, whose `edition` names the edition that couldn't read it. A
read that can live without such rows uses `checked()`, as
[Result shapes](03-reading.md#result-shapes) explains, and sets them aside:

<!-- example: read-through-the-overlap-window -->
```python
def payments_this_edition_can_read(db: ScopedDatabase, order_id: int) -> list[Payment]:
    """An order's payments, leaving out rows a later edition wrote that this one can't read."""
    found = db.find(Payment.where(Payment.order_id == order_id)).checked().results()
    return [payment for payment in found if not isinstance(payment, InvalidData)]
```
<!-- /example -->

A read of `CardPayment` alone never reaches a gift-card row, because it selects only rows
tagged `card`. Once the process adopts release 2, the same read through `Payment` returns
the gift card as a `GiftCardPayment`.

## How it works →

- [Model evolution](../../../../docs/concepts/model-evolution.md) explains, in domain
  terms, editions, adoption, classification and the overlap window.
- [Model evolution](../../../../core/spec/m-model-evolution.md) defines Evolution
  Operations, classification, Behavioral Impacts and Overlap-Visible Operations, and
  [schema delta](../../../../core/spec/m-schema-delta.md) defines the generated
  statements and what an application applying them must do.
- [Execution](../../../../core/spec/m-execution.md#model-editions) defines Model
  Editions, the Serving Model and adoption, and the
  [Python execution binding](../../spec/execution.md#models-roots-and-scopes) records
  `prepare_model`, `ServingModel` and `publish`.
- [ADR 0062](../../../../docs/adr/0062-transactions-adopt-one-model-edition-at-open.md)
  and
  [ADR 0063](../../../../docs/adr/0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md)
  record why transactions adopt one edition and why the application applies migrations.
