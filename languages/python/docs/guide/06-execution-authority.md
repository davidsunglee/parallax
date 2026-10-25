# Execution authority

Every read and write runs as someone. Before you run anything, you choose that authority
on the `Database` root, and the scope you get back carries it for as long as you keep the
scope. There are two kinds. A database-login scope runs as the login the adapter
authenticated with. A subject scope runs as an application user, under a database role
you name. This chapter covers both, then how the adapter gets the login's credentials,
and finally what a transaction does with the authority it runs under.

The examples use the shop model from [Modeling](02-modeling.md) and these imports:

<!-- example: execution-authority-imports -->
```python
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from parallax.core.db_port import (
    DRIVER_MANAGED,
    ConnectionAcquisitionError,
    CredentialSource,
    Password,
)
from parallax.core.execution import InvalidPrincipalError, TransactionAuthorityError
from parallax.postgres import PostgresAdapter, PostgresRole
from parallax.snapshot import Database, ScopedDatabase, TxnContext
```
<!-- /example -->

## Database-login scope

`using_database_login()` derives a scope that runs as the login itself:

<!-- example: run-scheduled-work-as-the-login -->
```python
def orders_for_the_nightly_report(database: Database[PostgresRole], day: dt.date) -> list[Order]:
    """Scheduled work with no user behind it runs as the service's own login."""
    db = database.using_database_login()
    return db.find(Order.where(Order.placed_on == day)).results()
```
<!-- /example -->

The runtime records which login it authenticated as once, while it starts, so deriving
the scope makes no query. The scope carries no authorization of its own: its work has
exactly the privileges the login's sessions have.

Use it for work that no application user stands behind, such as scheduled jobs and
reports, and for a service whose database account is the only identity it has. The
choice is always explicit. Parallax has no default scope and never takes an identity
from thread state or anywhere else, so code that has no scope can't reach the database.

## Subject scope

A service that acts for its users can connect as its own login but run each request as
the user who made it. `using_principal(principal)` takes a Principal: any object with a
`subject`, the string that names the user, and a `database_authorization`, the database
privileges the user's work runs under. On PostgreSQL the authorization is a
`PostgresRole`:

<!-- example: run-a-request-as-its-user -->
```python
@dataclass(frozen=True, slots=True)
class ShopUser:
    """An application user as a Principal: who they are, and the role they work under."""

    subject: str
    database_authorization: PostgresRole


def change_an_email_for(
    database: Database[PostgresRole], user: ShopUser, customer_id: int, email: str
) -> None:
    """Run one request as the user who made it."""
    db = database.using_principal(user)

    def change(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(email=email))

    db.transact(change)
```
<!-- /example -->

A request handler builds the user from whatever authenticated the request, for example
`ShopUser("user:42", PostgresRole("shop_clerk"))`, and derives a scope for that request.
Scopes are cheap: a scope holds no connection, and every scope shares its root's pool.

Deriving the scope reads `subject` and `database_authorization` once and keeps their
values, not your object. The subject is kept exactly as given. Parallax never trims,
case-folds or parses it, and two subjects are the same user only when their strings are
equal. An empty subject, or one that starts with `db-login:`, raises
`InvalidPrincipalError`, because that prefix is reserved for the login's own identity.

On each connection the work uses, the PostgreSQL adapter runs `SET ROLE` to the user's
role before any of the work, and `RESET ROLE` before the connection goes back to the
pool. Standalone reads switch role just as transactions do. The role replaces the
login's privileges rather than adding to them, so the work can do exactly what
PostgreSQL grants the role. Two things follow:

- The login must be a member of every role it switches to, for example through
  `GRANT shop_clerk TO shop_service`.
- A statement the role may not run fails. The database's refusal reaches you as the
  `cause` of an `ExecutionFailure`, like any other database error.

If the role can't be set, the work doesn't start. If it can't be reset, the connection
is discarded rather than reused. Because the role belongs to the session, a connection
has to stay on one server session from `SET ROLE` to `RESET ROLE`, which rules out
transaction-pooling and statement-pooling proxies. The
[lifecycle guide](../postgresql-lifecycle.md#execution-authority-and-session-affinity)
covers these PostgreSQL details.

## Credentials

The adapter's credentials prove who the login is. The scope then decides what the work
runs as. The two are separate steps: the credential authenticates the login before a
connection exists, and a role is chosen on the connection afterwards.

`credentials=` takes `Password(...)` for a constant secret, `DRIVER_MANAGED` to leave
authentication to libpq, or a credential source: any object whose `resolve()` method
returns a `Password`. That type is `CredentialSource`, and a `Password` is one too,
returning itself. Parallax asks the source each time it opens a physical connection,
whether the pool is filling, growing or replacing one, and never when it reuses a
connection it already holds. So a source that reads a mounted secret file picks up a
rotated password for every connection opened after the rotation:

<!-- example: resolve-a-password-per-connection -->
```python
@dataclass(frozen=True, slots=True)
class SecretFile:
    """A credential source that reads the password each time a connection is made."""

    path: Path

    def resolve(self) -> Password:
        return Password(self.path.read_text(encoding="utf-8").strip())


def configure_with_a_secret_file(conninfo: str, path: Path) -> PostgresAdapter:
    """A rotated secret reaches every connection opened after the rotation."""
    return PostgresAdapter(conninfo, credentials=SecretFile(path))
```
<!-- /example -->

A connection that's already open stays open when the secret that opened it changes or
expires. `resolve()` can run on one of the pool's threads or on yours, so it must bound
its own I/O. If it raises, no connection is made: once the pool is running, the work
that needed the connection fails with `ConnectionAcquisitionError`, whose `reason` is
`"credentials_refused"`, and at startup `connect` fails instead.

For Amazon RDS and Aurora, `parallax-aws` supplies `RdsIamCredentials`, a source that
signs a fresh IAM token for each new connection, and `rds_postgres`, which builds the
whole adapter. The lifecycle guide covers
[both](../postgresql-lifecycle.md#rds-and-aurora-authenticated-by-iam), along with
[the three credential forms](../postgresql-lifecycle.md#where-the-password-lives) and what
you get when a source fails.

## One actor per transaction

The authority a scope carries is its Execution Actor: either a user's subject together
with their database authorization, or the login. A transaction captures its scope's actor
once, when it begins, and keeps it until it ends. A retry sets up the same actor again on
its new connection, so a re-run can't pick up a different user.

A nested `transact` joins the running transaction only when it runs as the same actor. A
scope derived again from equal values carries the same actor, so a helper can derive its
own scope and still join. A different user, or the same user under another role, is
refused with `TransactionAuthorityError` before its callback runs:

<!-- example: keep-one-actor-per-transaction -->
```python
def rename_a_customer(db: ScopedDatabase, customer_id: int, name: str) -> None:
    """Joins the transaction already running on this thread, when there is one."""

    def rename(tx: TxnContext) -> None:
        customer = tx.find(Customer.where(Customer.id == customer_id)).result()
        tx.amend(customer.edit(name=name))

    db.transact(rename)


def another_user_can_join(
    database: Database[PostgresRole], user: ShopUser, other: ShopUser, customer_id: int
) -> bool:
    """Whether work for ``other`` can join a transaction that ``user`` began."""

    def request(_: TxnContext) -> bool:
        rename_a_customer(database.using_principal(user), customer_id, "Ada King")
        try:
            rename_a_customer(database.using_principal(other), customer_id, "Ada Lovelace")
        except TransactionAuthorityError:
            return False
        return True

    return database.using_principal(user).transact(request)
```
<!-- /example -->

Given the same user twice, `another_user_can_join` returns `True`: both renames run in
one transaction. Given two different users, it returns `False`, and the first rename
still commits, because catching the refusal leaves the transaction usable. Letting the
refusal escape the callback rolls the whole transaction back. To act for someone else,
start a new transaction after this one ends.

On the database side, the role a subject scope sets is the session's `current_user`
while the work runs, and the login stays its `session_user`, so your own triggers and
policies can read either. Parallax itself records no audit provenance today: it doesn't
write the actor into your rows or anywhere else.
[Execution authority and audit](../../../../docs/concepts/execution-authority-and-audit.md#audit-provenance)
describes the audit design.

## How it works →

- [Execution authority and audit](../../../../docs/concepts/execution-authority-and-audit.md)
  explains, in domain terms, why authority is chosen once per scope and how it reaches
  the database.
- [Execution authority](../../../../core/spec/m-execution-authority.md) defines the
  Principal, the Execution Actor, transaction capture and the join rule, and
  [the database port](../../../../core/spec/m-db-port.md#configuration-runtime-and-one-connection-at-a-time)
  defines credential sources.
- The [Python execution binding](../../spec/execution.md#models-roots-and-scopes) records
  `using_principal` and `using_database_login`, and its
  [failure boundaries](../../spec/execution.md#transactions-and-failure-boundaries)
  record the join refusals.
- The [PostgreSQL lifecycle guide](../postgresql-lifecycle.md) covers credentials, RDS
  IAM, and role switching in production.
