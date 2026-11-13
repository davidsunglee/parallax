# Model evolution

Your model will change after you deploy it. Parallax can switch a running process to a
changed model without a restart, provided the process has the new model's classes or
reads the model from a descriptor. It generates the schema change the new model needs,
but it never changes your database itself. This chapter starts with editions, the
successive models a process serves, and how a transaction uses them. It then describes
a change between two models, generates the migration for it, and rolls the new model out
to running processes, including the window when two editions run against one database.
It ends with changing a [Database Binding](02-modeling.md#database-bindings), which rolls
out the same way unless it moves something the database already holds.

The examples use the shop model from [Modeling](02-modeling.md) and these imports:

<!-- example: model-evolution-imports -->
```python
from collections.abc import Callable
from dataclasses import dataclass

from parallax.core import (
    Attr,
    ConcreteSubtype,
    DomainModel,
    InvalidData,
    InvalidDataError,
    ModelSelection,
    PublicationConflictError,
    ServingModel,
    attr,
    prepare_model,
)
from parallax.descriptor import domain_model_from_yaml, export_yaml
from parallax.evolution import (
    ABSENT,
    CoordinatedEvolution,
    Evolution,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.evolution.operations import SequenceRelocated, TableRelocated
from parallax.postgres import PostgresAdapter, PostgresBinding, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, connect
```
<!-- /example -->

## Model Editions

Each model a root serves is a Model Edition, named by a string you choose, such as a
release number or a commit hash. `connect(adapter, model, binding=binding)`, as in
[Getting started](01-getting-started.md#connect), serves one edition, with a generated
name, for as long as the root is open. To be able to serve a later edition without
reconnecting, prepare the model yourself and hand the root a `ServingModel` that holds
it:

<!-- example: serve-a-model-edition -->
```python
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
```
<!-- /example -->

`prepare_model` returns a `ModelSelection`: the model, its binding and its edition, with
everything Parallax derives from them, such as where each table is and how each entity's
rows are read and its writes planned, worked out in advance. If the model can't be
prepared, it raises there, before anything serves it, rather than on a later request.
The Serving Model holds the one selection the root serves at any moment, and only code
holding the Serving Model can replace it: holding the root doesn't let you change the
model it serves.

Every execution adopts the selection held when it starts, and keeps it to the end:

- A transaction attempt adopts it before it begins, and `tx.edition` names it. A
  publication that lands while the transaction runs changes nothing for it.
- A nested `transact` that joins the transaction keeps the edition it already adopted.
  A retry is a new attempt, so it adopts whatever is held when it starts, which may be a
  newer edition.
- A standalone `find` adopts when it runs, and a stream adopts when you enter its `with`
  block and keeps that edition for every page.

A `Snapshot` and an entered stream carry the edition the work ran under as `edition`,
and a failure that escapes the work carries a note naming it; the entity instances
inside a result don't. Editions are compared
only for equality, never ordered, so a later release doesn't need a "larger" name, but
never give a changed model a name the Serving Model has already served. Parallax doesn't
detect a reused name, and `edition` would then no longer tell the two models apart.

## Describing a change

The shop's second release accepts gift cards. It adds a concrete subtype to the
[payment family](02-modeling.md#inheritance-families), so its model is
`DomainModel(Customer, Order, Payment, CardPayment, BankTransfer, GiftCardPayment)`. A
model lists every class it serves, a family's root included, and a concrete subtype it
leaves out is not part of it, so release 1's model is the same list without
`GiftCardPayment`.
`evolve(earlier, later, earlier_binding=..., later_binding=...)` describes what changes
between two `DomainModel`s, each placed by its binding. It compares their entities,
attributes and relationships, not your Python classes, and where their bindings put each
table and sequence. The earlier model and binding are the ones you deployed last, so keep
a copy of both at each deployment. `export_yaml`, from the `parallax-descriptor`
distribution, writes a model as a descriptor, `domain_model_from_yaml` reads one back,
and a binding's `to_yaml` and `from_yaml` do the same for it:

<!-- example: describe-a-model-change -->
```python
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
```
<!-- /example -->

`Deployed` holds the descriptor's and the binding's YAML text, not file paths.
`domain_model_from_yaml` builds from the descriptor a `DomainModel` with no entity
classes, which is all `evolve` needs.

`evolve` reads only the two models and their bindings. It never looks at a database, so
the description is the same wherever you compute it, for example in a release check
before you deploy. It answers three questions.

**What changes?** `operations` lists each change as an Evolution Operation named in the
terms you modeled in: an entity, an attribute, a relationship, an index. Gift cards are
one operation, `ConcreteSubtypeAdded`, naming `GiftCardPayment`. Declarations are matched
by identity, which is their name, so Parallax never guesses a rename: renaming an
attribute is one removal and one addition.

**Can a live database take it?** The result is one of two types, and the
[classification](../../../../core/spec/m-model-evolution.md#classification) rules decide
which for every kind of change. A
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

`schema_delta(evolution)` turns a `UnilateralEvolution` into the statements, for the
later binding's backend, that bring a database from the earlier model to the later one.
It accepts only a `UnilateralEvolution`, so your type checker refuses a call that might
hand it a Coordinated one. `evolve(ABSENT, ...)` is always unilateral and typed that
way, which is why [Getting started](01-getting-started.md#create-the-tables) passes it
straight in.
Between two models the type is only known at run time, so a release check refuses a
coordinated change first:

<!-- example: generate-the-migration -->
```python
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
```
<!-- /example -->

Under a binding whose default schema is `px`, the gift cards' migration is one
statement, `alter table px.payment add column card_number varchar(19)`, because the
family's subtypes share one table. Provisioning a new database is the same call with
`ABSENT` as the earlier model, as
[Create the tables](01-getting-started.md#create-the-tables) shows.

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
- Forwards only. Parallax produces no inverse delta. To back a release out, publish the
  earlier model again: the migrated schema still serves the earlier edition, as it does
  during the [overlap window](#the-overlap-window), though that edition can't read rows
  only the later model admits.

Creating a unique index checks the rows already stored: if any break the new rule, the
statement fails, and you don't publish the release. The full result of `schema_delta`
also lists each index it creates in `created_indices`, with the physical name a later
uniqueness violation reports, so keep it as a record of what each rollout created.
A temporal table the delta creates carries its named key, interval checks and exclusion
inline, behind the `btree_gist` extension the delta installs first; a delta never adds
them to a table that already exists (see
[Temporal constraints](../postgresql-lifecycle.md#temporal-constraints)).

## Rolling out a new model

A rollout has two parts, in this order. Your deployment migrates the database once, and
then every running process publishes the new edition:

<!-- example: roll-out-a-release -->
```python
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
```
<!-- /example -->

`run_migration` is your migration tool. `migrate` returns what to keep as deployed, the
release's descriptor and binding, only once the migration has run, so the model and
binding you keep are always the ones the database has.

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

A process can only prepare a model from classes it has loaded, so the release's code is
deployed first, still serving release 1: its release-1 model is the list without
`GiftCardPayment`, although the class is loaded. Once the migration has run, `adopt`
switches it to release 2. A model built with `domain_model_from_yaml` needs no classes,
so a process can also publish one it reads at run time. Such a model serves Wire reads
and writes; a Typed read under it is refused, because there is no class to build values
of.

### The overlap window

Each process publishes on its own, so for a while some processes serve release 1 and
others release 2, against one database. That window is Edition Overlap, and draining a
single process doesn't end it. Parallax classifies what can happen in it rather than
preventing it.

Both editions work against the migrated schema, because the evolution was unilateral.
Release 1 never selects `card_number`, and its inserts leave the column empty.
Behavioral Impacts can still make the editions behave differently. For example, a unique
index created for a later release can refuse a write an earlier-edition process makes.
The `DatabaseError` names the index in its `violated_index`, which you can find in
`created_indices`, and Parallax doesn't retry it.
[Errors](08-errors.md#failures-the-database-reports) shows a handler for one such index.

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

## Changing a binding

A selection is prepared from a model and its binding together, so a binding change is
published like a model change, with no restart and no new root, provided nothing the
database already holds moves. These binding changes move nothing:

- a new entity placed by an existing default or namespace entry;
- a new namespace's entry, shipped in the release that adds that namespace's first
  entities;
- a new entry for a new entity or sequence;
- a new default, once every existing table and sequence the old default placed has an
  entry keeping it where it is;
- removing an entity together with its entry, or a namespace's last entity together with
  that namespace's entry, since a binding naming something the model doesn't declare is
  refused.

On their own, the first four are unilateral: `migrate` creates what the new binding
places and `adopt` publishes it. Removing an entity is coordinated with
`AUTHORING_SURFACE_CHANGE_REQUIRED`, because code naming it stops being valid, so
`migration_for` refuses it. It needs no statement, because the removed entity's table
can stay where it is: once no code you run names the entity, `adopt` publishes the
release in each process, and you keep its descriptor and binding as deployed yourself.

Before the migration runs, your deployment creates each schema the new binding names
that doesn't exist yet, and grants your application's role access to it: Parallax
creates no schema and grants nothing. Preparing and publishing check that the binding
places the model, never that a schema or table exists or that your role may use it, so a
release published before its migration is served anyway, and its first statement that
reaches a missing table fails with a `DatabaseError`.

A binding change that puts an existing table in another schema or under another name, or
an existing sequence anywhere else, is a relocation. `evolve` reports each one as a
`TableRelocated` or `SequenceRelocated` operation, whose `earlier` and `later` give both
places, coordinated with `DATABASE_MIGRATION_REQUIRED`, so `migration_for` refuses it. A
release check can report what it moves:

<!-- example: report-what-a-release-moves -->
```python
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
```
<!-- /example -->

`publish` refuses a candidate that relocates anything the selection it replaces holds, with
a `UsageError` whose `code` is `PUBLICATION_RELOCATION_REFUSED` and whose message names
each move, and the held selection keeps serving. It refuses one prepared for another
backend in the same way. Changing an entity's `table=` relocates its table too, unless its
binding entry gives the old physical name: then the change is the model's alone, publishes
like any other, and needs no statement.

Parallax generates nothing that moves or renames a table or copies data. Relocating is a
coordinated migration that you run behind a replacement root:

1. Stop everything serving the old placement, because no process can publish the move.
2. Move the objects, for example with `alter table px.orders set schema sales`, and grant
   your application's role access where they now are.
3. Serve the new binding from new roots, each with a `ServingModel` prepared under it, as
   `connect_serving` does, and keep the new binding as deployed.

A move between schemas that keeps each table's name keeps every name Parallax derives
from the table: those of a temporal table's key, checks and exclusion, and of the indexes
your model declares, which come from the table's own name and never its schema, and which
`set schema` moves with it. A new physical table name changes those derived names. Before
the replacement roots serve, rename each constraint and index the table carries to the name
the new binding derives, which the statements that provision the release from `ABSENT`
under that binding show, and update the records you keep from `created_indices`.
Otherwise a uniqueness violation names an index your records don't know, and Parallax
doesn't recognize a temporal table's overlap as its own conflict, so it stops retrying it.
Renaming the table alone doesn't do this, and neither does an updatable view under the old
name: such a bridge view is a technique your deployment may use while old processes
drain, not something Parallax generates or relies on.

Across a fleet, each process publishes a binding change for itself, as it does an edition,
so every object the new binding places must exist before the first process publishes it.
Until a process publishes, its executions keep the placement its selection carries.

## How it works →

- [Model evolution](../../../../docs/concepts/model-evolution.md) explains, in domain
  terms, editions, adoption, classification and the overlap window.
- [Model evolution](../../../../core/spec/m-model-evolution.md) defines Evolution
  Operations, classification, Behavioral Impacts and Overlap-Visible Operations, and
  [schema delta](../../../../core/spec/m-schema-delta.md) defines the generated
  statements and what an application applying them must do.
- [Database binding](../../../../core/spec/m-database-binding.md#relocation-between-two-resolved-bindings)
  defines relocation, which publication refuses and evolution coordinates, and
  [ADR 0093](../../../../docs/adr/0093-a-database-binding-places-each-prepared-selection-and-publication-never-relocates.md)
  records why a binding changes through publication but never moves what survives.
- [Execution](../../../../core/spec/m-execution.md#model-editions) defines Model
  Editions, the Serving Model and adoption, and the
  [Python execution binding](../../spec/execution.md#models-roots-and-scopes) records
  `prepare_model`, `ServingModel` and `publish`.
- [ADR 0062](../../../../docs/adr/0062-transactions-adopt-one-model-edition-at-open.md)
  and
  [ADR 0063](../../../../docs/adr/0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md)
  record why transactions adopt one edition and why the application applies migrations.
