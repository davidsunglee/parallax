# Errors

Parallax refuses a problem as early as it can. A mistake in a class, a model, a query
or an edit is refused where you make it, before anything reaches the database. Stored
data that breaks the model is refused when you ask for the result that holds it.
Conflicts and database failures come out of a transaction once Parallax has decided
whether running it again could help. Each error carries structured fields, such as a
code, a location or a category, so your code can branch on them rather than on the
wording of a message.

This chapter starts with where an error reaches you. It then takes each kind in turn:
mistakes in what you wrote, stored data that breaks the model, conflicts and failed
preconditions, and failures the database reports. It ends with what each error asks you
to do.

Parallax has no common base exception, so catch the specific class. Each error is
exported by the module of the part of Parallax that raises it, so they are spread over
several modules. The imports below give the path of every error this chapter names, and
the [Python binding](../../spec/python.md#8-deployable-artifact-topology) lists every
module's exports. The examples use the shop model from [Modeling](02-modeling.md) and
these imports:

<!-- example: errors-imports -->
```python
from collections.abc import Mapping

from pydantic import ValidationError

from parallax.core import EditError, EntityDefinitionError, QueryDefinitionError
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.core.entity import UnloadedRelationshipError
from parallax.core.execution import (
    ExecutionFailure,
    InvalidPrincipalError,
    KeyedWriteValueError,
    PublicationConflictError,
    QueryTargetError,
    TransactionAccessModeError,
    TransactionAuthorityError,
    TransactionOptionConflictError,
    TransactionRollbackError,
    TransactionTimePinReadOnlyError,
)
from parallax.core.metamodel import MetamodelIssue
from parallax.core.read_delivery import InvalidData, InvalidDataError, StreamStateError
from parallax.core.unit_work import (
    InstructionRejectedError,
    OptimisticLockConflictError,
    RollbackOnlyError,
    WriteEvidenceError,
    WriteInstructionError,
    WritePreconditionError,
)
from parallax.snapshot import (
    NoResultFound,
    ScopedDatabase,
    TooManyResultsFound,
    TxnContext,
    is_view_loaded,
)
```
<!-- /example -->

## Where an error reaches you

Two rules decide where you catch an error.

**A refusal raised before any work runs reaches you as itself.** Creating an entity
class, building a `DomainModel`, building a query and editing a value each check what
you wrote on the spot. A standalone read also checks its query against the model before
it reads: `db.find` raises `QueryTargetError` itself when the model declares no entity
for the query's target.

**Anything that escapes a transaction, or fails while a read runs against the database,
reaches you as an `ExecutionFailure`.** Its `cause` is the original error, which is also
its `__cause__`, and its `edition` names the model edition the work ran under. Inside a
callback, a verb raises its own error where you call it, and you can catch it there.
Once the error leaves the callback, `transact` wraps it. So a handler around `transact`,
`read_only` or a standalone read looks at `failure.cause`, as the examples below do.

Catching an error inside the callback doesn't always leave the transaction usable. A
refusal a verb raises before anything is sent, such as `WriteEvidenceError`, does. A
failure while the transaction sends its writes, or a failure that escapes a joined call,
makes the transaction rollback-only: every later read or write raises
`RollbackOnlyError`, and the transaction rolls back however the callback returns.
[Transactions](05-transactions.md#a-failed-joined-call-dooms-the-transaction) shows both
cases.

## Mistakes in what you wrote

Most errors you meet while developing refuse something you wrote. Parallax checks each
thing when you make it. Where one check can find several problems, it reports them all
at once, each with a stable code and a location, so you can fix them in one pass and a
tool can report them without parsing messages.

- **A class.** Creating an entity class checks its declaration. An unknown class-header
  option or a reserved member name raises `EntityDefinitionError`, whose `code` names
  the rule. Constructing an instance validates its values as any Pydantic model does,
  and raises Pydantic's own `ValidationError`.
- **A model.** `DomainModel(...)` checks the classes as a whole. As
  [Modeling](02-modeling.md) explains, a model that breaks a rule raises a `ValueError`
  that lists every problem in its `issues`. Each one is a `MetamodelIssue` with a
  `code`, a `location` in the model and a `message`. Catch it as a `ValueError` and read
  its `issues`.
- **A query.** Building a query checks each expression and clause, and
  `QueryDefinitionError` refuses one it can't accept, with a `code` naming the rule.
  `Customer.name == 3` compares text with a number, a `Decimal` with more places than
  its attribute declares can't be compared with it, `limit(-1)` isn't positive, and
  `as_of(...)` on `Customer` asks for history that `Customer` doesn't keep. Whether the
  model declares the query's target can only be checked when the query runs, so that
  refusal, `QueryTargetError`, comes before anything is read.
- **A write.** A write verb checks what it is handed before it buffers anything.
  `WriteEvidenceError` means the value carries no licence this attempt can use (see
  [No blind writes](05-transactions.md#no-blind-writes)). `KeyedWriteValueError` means
  the verb was handed a value it can't take, and its message names the verb that does:
  `tx.amend` of a value you constructed rather than read names `tx.insert`, and
  `tx.insert` of a value a read returned names `tx.amend`. `WriteInstructionError` means
  the write breaks a rule, such as `tx.delete` on a temporal entity, whose message names
  `terminate`, or a target write on an entity with no revision. Its subtype
  `InstructionRejectedError` names the rule in its `rule`, such as a
  [predicate write](04-writing.md#predicate-writes) on a versioned entity.
  `TransactionTimePinReadOnlyError` means the value was read as of a past Transaction
  Time, which [can't be rewritten](04-writing.md#correct-the-past).

An edit shows the accumulation best. `edit(...)` checks every change against the model,
and one `EditError` reports every rule the changes break. Only once they all pass do
validators you declared run, and a validator's refusal raises Pydantic's
`ValidationError`, as it does on construction. Each of its `violations` has a
`code`, a `member_name` and a `message`, so a form can show every refused field at once.
`member_name` is `None` only for a refusal that concerns no single member:

<!-- example: report-every-refused-field -->
```python
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
```
<!-- /example -->

Given `{"name": None, "email": 5}`, this function amends nothing and returns two
messages, keyed by `"name"` and `"email"`: a name is required, and an email is text.
Given valid values, it amends the customer and returns an empty mapping. `edit` raises
before anything is written, so catching its error leaves the transaction usable.

**What to do:** fix the code that built the request, or, when the values came from a
user, report the issues back to them. The same request fails the same way every time,
so Parallax never retries one.

## Stored data that breaks the model

Data written outside Parallax can contradict the model you read it with.
[Result shapes](03-reading.md#result-shapes) shows how a read reports it. `find` itself
succeeds, and the accessor you call, such as `.results()`, raises `InvalidDataError`
when a result it would return breaks the model. The error's `invalid_data` holds one
`InvalidData` record for each affected result, in result order. Each record has the
`issues` found, and as much of the value as Parallax could build without inventing
anything. `checked()` hands you the same records in their place among the results
instead of raising.

The accessor raises after the read has finished. Outside a transaction, you catch
`InvalidDataError` itself; inside a callback that lets it escape, it becomes the `cause`
of an `ExecutionFailure` like any other error.

**What to do:** repair the stored data. The request isn't at fault, and reading again
returns the same verdict until the data changes. Where a report or a batch job should
carry on past damaged rows, read with `checked()` and set the records aside.

## Conflicts, failed preconditions and exhausted retries

These errors arise when other transactions change the rows yours depends on.
[Retries](05-transactions.md#retries) explains which of them Parallax retries; this
section covers the ones that reach you.

- **An optimistic lock conflict** means a version or Transaction-Time start that a read
  in this attempt observed has moved. Parallax retries it, so an
  `OptimisticLockConflictError` reaches you as a `cause` only when retries are off or
  used up.
- **A deadlock or a serialization failure** is retried the same way. It is a database
  error, so it reaches you as a cause whose `category` is `"deadlock"`
  ([below](#failures-the-database-reports)).
- **Retries run out** when every attempt fails with something retryable. You then get the
  last attempt's failure as the `cause`, with a note naming the count, such as
  `bounded retry exhausted after 11 attempts (retries=10)`.
- **A failed precondition** means the revision a target write stated no longer matches,
  so the write raises `WritePreconditionError`. Its `expected` holds the revision you
  stated. Parallax never retries it, because a re-run would state the same revision
  again.

A failed precondition is the one a caller most often handles. This function from
[Writing](04-writing.md#target-writes) cancels the orders a user reviewed and reports
those that changed since:

<!-- example: cancel-reviewed-orders -->
```python
def cancel_reviewed_orders(db: ScopedDatabase, reviewed: list[Order]) -> list[int]:
    """Cancel each order in a transaction of its own; return the ones that changed."""
    return [order.id for order in reviewed if not cancel_unless_changed(db, order)]


def cancel_unless_changed(db: ScopedDatabase, order: Order) -> bool:
    """Cancel ``order`` unless it changed since it was read; answer whether it was cancelled."""
    try:
        db.transact(lambda tx: tx.delete_if(Order, key=order.id, version=order.version))
    except ExecutionFailure as failure:
        if not isinstance(failure.cause, WritePreconditionError):
            raise
        return False
    return True
```
<!-- /example -->

**What to do:** after a failed precondition, the caller's view is out of date. Read the
current value, show it, and let the user decide again, as `cancel_reviewed_orders`
returns the orders that changed. Retries that run out mean the rows are contended: many
transactions write them at once. Run the work again later, shorten the transactions
that write those rows, or
[prefer locking](05-transactions.md#optimistic-and-locking-concurrency) for them, so that
writers wait for each other instead of re-running.

## Failures the database reports

A failure the database reports, such as a duplicate key, reaches you as the `cause` of
an `ExecutionFailure`. The cause's type isn't part of the public API, so read its
attributes rather than testing its class:

- `category` says what kind of failure it is, in Parallax's portable vocabulary:
  `"uniqueViolation"` for a duplicate key, `"deadlock"` for a deadlock or a
  serialization failure, `"lockWaitTimeout"` for a lock waited on past the database's
  limit, and `None` for anything else, such as a check or foreign-key constraint, a
  missing table, or a privilege the role lacks.
- `native_code` is the database's own code, PostgreSQL's SQLSTATE, such as `"23505"`
  for a duplicate key.
- `message` is the database's message.

A duplicate key usually means the object already exists. This function adds a customer,
and answers `False` instead of failing when the id is taken:

<!-- example: add-a-customer-unless-the-id-is-taken -->
```python
def add_a_customer_unless_the_id_is_taken(db: ScopedDatabase, customer: Customer) -> bool:
    """Insert ``customer``, or answer False when another customer already has its id."""
    try:
        db.transact(lambda tx: tx.insert(customer))
    except ExecutionFailure as failure:
        if getattr(failure.cause, "category", None) != "uniqueViolation":
            raise
        return False
    return True
```
<!-- /example -->

The insert is buffered and sent when the transaction commits, so the duplicate surfaces
there, and the transaction rolls back. Any other failure passes through. Reading first
to check whether the id is free wouldn't make this unnecessary: two calls can both find
it free and both insert, and only the database's unique index decides which one wins.
`getattr` reads the category because the cause has no exported type to narrow it to.

Of the categories, Parallax retries only `"deadlock"`, so you see one only once retries
run out. A `"uniqueViolation"` asks you to choose another key or treat the object as
already there. A `"lockWaitTimeout"` means another transaction held a lock for too long:
try again later, or find what holds it. For a failure with no category, `native_code`
and `message` say what happened. A missing table or column usually means the schema
doesn't match the model (see [Model evolution](07-model-evolution.md)), and a refused
privilege belongs to the role the work runs as (see
[Execution authority](06-execution-authority.md)).

Two more failures fall outside the categories, and each also reaches you as the `cause`
of an `ExecutionFailure`:

- **No connection.** `ConnectionAcquisitionError` means Parallax couldn't get a
  connection, and its `reason` says why, such as `"timeout"` or `"closed"`. It isn't
  retried, because no attempt began. The
  [PostgreSQL lifecycle guide](../postgresql-lifecycle.md#timeouts) covers the pool and
  the timeouts behind it.
- **A failed rollback.** When rolling back after a failure fails too, you get
  `TransactionRollbackError`, which holds both as `triggering_error` and
  `rollback_error`.

## What each error asks of you

| Error | Raised | Retried? | What to do |
| -- | -- | -- | -- |
| A refused class, model, query, edit or write, such as `EntityDefinitionError`, `QueryDefinitionError`, `QueryTargetError`, `EditError`, `WriteEvidenceError`, `KeyedWriteValueError` or `WriteInstructionError`, or a model's `ValueError` | where you make the request | No | Fix the request, or report its issues to whoever supplied it |
| `NoResultFound` or `TooManyResultsFound` | by `.result()` or `.result_or_none()`, after the read | No | Use the accessor for the shape you expect, or treat the absence as an answer |
| `UnloadedRelationshipError` | when you touch a relationship the read didn't include | No | Include it in the read, or test it with `is_view_loaded` |
| `StreamStateError` | when a stream is used outside its `with` block, entered twice or iterated twice | No | Consume each stream once, inside its `with` block |
| `InvalidDataError` | by the accessor, after the read | No | Repair the stored data; read with `checked()` to carry on past it |
| `TransactionAccessModeError`, `TransactionOptionConflictError` or `TransactionAuthorityError` | when a nested call can't join the running transaction, before its callback runs | No | Call the matching kind of transaction, name the same options or none, or run as the same actor |
| `InvalidPrincipalError` | when you derive a scope from a principal | No | Supply a nonempty subject that doesn't start with `db-login:` |
| `RollbackOnlyError` | at any read or write after a failure doomed the transaction | On the original failure's terms | Let the original failure escape; the transaction can only roll back |
| `PublicationConflictError` | when `publish` finds another selection held than the one it expected | No | Read the current selection and decide whether to publish again |
| `OptimisticLockConflictError`, or a `"deadlock"` category | when the transaction sends its writes, or at the statement | Yes, up to `max_retries` | If retries run out: try later, shorten the transactions, or prefer locking |
| `WritePreconditionError` | when the transaction sends its writes, or at the call under locking | No | Read the current value and let the user decide again |
| A `"uniqueViolation"` category | when the insert is sent, usually at commit | No | Choose another key, or treat the object as already there |
| A `"lockWaitTimeout"` category, or none | at the statement | No | Read `native_code` and `message`; fix the schema or privilege, or try later |
| `ConnectionAcquisitionError` | before an attempt begins | No | Check the database and the pool |
| `TransactionRollbackError` | when the rollback after a failure fails too | No | Read `triggering_error` for the failure, and `rollback_error` for the rollback's |

## How it works →

- [Transactions, concurrency and retry](../../../../docs/concepts/transactions.md)
  explains, in domain terms, [retry](../../../../docs/concepts/transactions.md#retry) and
  [joining and rollback-only](../../../../docs/concepts/transactions.md#joining-and-rollback-only),
  and [the read flow](../../../../docs/concepts/read-flow.md#judged-page) shows where
  stored data is judged.
- [Metamodel issues](../../../../core/spec/m-metamodel.md#issues-and-locations) and
  [model formation](../../../../core/spec/m-model-formation.md#validation-and-contract-errors)
  define how a model's problems are reported, and
  [ADR 0001](../../../../docs/adr/0001-validation-errors-accumulate-structured-issues.md)
  records why validation errors accumulate structured issues.
- [Read delivery](../../../../core/spec/m-read-delivery.md#invalid-stored-data) defines
  the stored-data issues, and
  [ADR 0056](../../../../docs/adr/0056-stored-data-violations-are-classified-at-the-result-root.md)
  records why a read classifies them per result.
- The [unit of work](../../../../core/spec/m-unit-work.md) defines
  [abort](../../../../core/spec/m-unit-work.md#abort),
  [target writes](../../../../core/spec/m-unit-work.md#target-writes) and
  [the errors a write's effect raises](../../../../core/spec/m-unit-work.md#affected-row-enforcement).
  [Automatic retry](../../../../core/spec/m-auto-retry.md) defines which failures are
  retried.
- [Database error classification](../../../../core/spec/m-db-error.md) defines the
  categories and how each database's codes map to them, and the
  [database port](../../../../core/spec/m-db-port.md) defines connection acquisition.
- The Python binding records the
  [failure boundaries](../../spec/execution.md#transactions-and-failure-boundaries),
  [query authoring refusals](../../spec/queries-and-results.md#authoring),
  [result accessors](../../spec/queries-and-results.md#eager-results) and
  [editing](../../spec/declarations.md#editing-presence-and-serialization).
