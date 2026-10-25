# Execution authority and audit

Every database operation runs as someone: the service's own database login, or an
application user working under database privileges chosen for them. Parallax makes that
choice explicit, makes it once, and carries it unchanged to every connection the work
uses. This page explains how authority is chosen, what it captures, how it reaches the
database, how the login itself authenticates, and what audit provenance is reserved to
record.

Each section names the specification that owns it. This page explains and links; when
it and a specification seem to disagree, the specification is right.

## Authority is chosen once, per scope

A Database Root owns the runtime: its connections, its model and its option defaults.
It runs no modeled work itself. To read or write, a caller first derives an Execution
Scope from the root by choosing an authority, and the scope captures exactly one
Execution Actor for as long as it exists
([scope creation and use](../../core/spec/m-execution-authority.md#scope-creation-and-use)):

```text
 Database Root (runtime, connections, option defaults; no modeled work)
   │
   ├─ choose the database login ───→ Execution Scope   actor: the Database Login Identity
   │
   └─ supply a Principal ──────────→ Execution Scope   actor: Subject Identity
                                          │                    + Database Authorization
                                          │
                                          ├─ standalone read → runs under the actor
                                          └─ transaction     → captures the actor once;
                                                               every attempt runs under it
```

The choice is never implicit. There is no ambient identity taken from thread, task or
request state, and no default Principal. Leaving the subject out doesn't select the
database login either: the caller picks one of the two explicitly. A scope captures
values when it is created and ignores later changes to what the caller passed in, and a
scope works only with the runtime that created it.

Choosing once per scope, rather than passing a Principal to every operation, means one
transaction can't be handed several authorities, a retry can't re-read identity that has
changed since, and delivery that runs later doesn't keep application objects alive. The
decision and the alternatives it rejected are recorded in
[ADR 0066](../adr/0066-execution-authority-is-selected-once-per-scope.md).

## Principal and Execution Actor

The two terms separate what the application hands in from what Parallax keeps
([terms](../../core/spec/m-execution-authority.md#terms)):

|  | Principal | Execution Actor |
| -- | -- | -- |
| What it is | the application's input: a Subject Identity paired with a Database Authorization | the authority a scope captured: a subject with its authorization, or the database login |
| Who makes it | the application, from whatever authenticated its user | the scope, when it is derived |
| Lifetime | read once, when the scope is derived, and not retained | immutable for the scope's lifetime, and for every transaction it begins |

A **Subject Identity** is a nonempty string preserved verbatim: never trimmed,
case-folded or parsed. Two subjects are equal exactly when their strings are equal
([Principal contract](../../core/spec/m-execution-authority.md#principal-contract)).
A **Database Authorization** is an opaque value owned by the database provider; on
PostgreSQL it names a role. Core compares it for equality and hands it back to the
provider, but never inspects it
([Database Authorization contract](../../core/spec/m-execution-authority.md#database-authorization-contract)).

Two actors are equal when their identities are equal and, for subjects, their
authorizations are equal too
([actor equality](../../core/spec/m-execution-authority.md#execution-actor-equality)).
The same subject under two different authorizations is two actors. A subject never
equals the database login, even when the strings look alike, and the `db-login:` prefix
is reserved so that no subject can pose as the login.

## Two kinds of scope

|  | Database-login scope | Subject scope |
| -- | -- | -- |
| The caller supplies | nothing but the choice | a Principal |
| Identity | the login the runtime authenticated, recorded once while the runtime starts | the Principal's Subject Identity |
| Privileges | the login's own | replaced, or contained, by the Database Authorization for each connection |
| Typical work | scheduled jobs, reports, a service whose database account is its only identity | requests made on behalf of an application user |

A database-login scope makes no query when it is derived, because the runtime already
knows its authenticated login. Neither kind of scope holds a connection: every scope
derived from a root shares that root's runtime.

## How authority reaches the database

Authority is applied per connection, around each piece of work
([provider binding and revocation](../../core/spec/m-execution-authority.md#provider-binding-and-revocation)):

```text
 acquire a connection
   │
   ├ subject scope: install the Database Authorization     fails → the work never starts
   ▼
 run the work: a standalone read, or one transaction attempt
   │
   ├ subject scope: revoke the authorization                fails → the connection is not returned
   ▼
 release: returned | invalidated | release-unconfirmed
```

Revocation is attempted on every exit path: commit, rollback, a failed callback, a
retry, cancellation, and the end of a standalone read. A connection whose revocation
fails is never returned for ordinary reuse: it is discarded, or its release is reported
as unconfirmed
([what releasing a connection establishes](../../core/spec/m-db-port.md#what-releasing-a-connection-establishes)).

The authorization replaces or contains the login's privileges; it never adds to them.
On PostgreSQL the provider sets the role for the session before the work and resets it
afterwards, so the work can do only what the database grants that role. The login must
be allowed to assume the role, and the connection must stay on one server session
throughout, which is why proxies that move a session's statements between server
sessions are unsupported.

Diagnostics may say which mode an operation ran in, but they never carry the Database
Authorization, credentials or the role-setting commands
([diagnostics and confidentiality](../../core/spec/m-execution-authority.md#diagnostics-and-confidentiality)).

## Transactions keep one actor

A transaction captures its scope's actor once its first attempt has begun, and keeps it
for its whole life
([transaction capture](../../core/spec/m-execution-authority.md#transaction-capture)).
Each retry installs the same actor again on the new attempt's connection and never
re-reads identity from anywhere else.

A nested call joins the running transaction only when its actor equals the captured one
([join authority](../../core/spec/m-execution-authority.md#join-authority)). Equality is
by value, so a scope derived again from equal inputs joins, while a different subject,
a different authorization or a switch between subject and login is refused before the
nested work starts. Authority is checked before access mode and options, so an authority
mismatch is the error reported when several things differ. Switching authority inside a
transaction is never allowed: work for someone else starts its own transaction after
this one settles.

## Credentials are resolved per physical connection

A credential proves who the database login is; it is not a Database Authorization. One
authenticates the login before a connection exists, and the other is applied to a
connection afterwards. Adapter configuration therefore carries two things: where the
database is, and how the login authenticates
([configuration and credentials](../../core/spec/m-db-port.md#configuration-runtime-and-one-connection-at-a-time)).

A **Credential Source** is asked for a credential each time a physical connection is
established: when a pool fills, grows or replaces a connection, or when an on-demand
connection is opened. Reusing a connection that is already open asks nothing, and an
open connection is never dropped because the credential that opened it has expired. So
short-lived secrets work with long-lived pools: a cloud token signed for each new
connection authenticates the service login, and a Principal then selects a role that
login may assume. **Driver-Managed Credentials** instead declares that the driver's own
mechanisms authenticate the login. The rationale is recorded in
[ADR 0067](../adr/0067-database-login-credentials-are-resolved-per-physical-connection.md).

## Audit provenance

Execution authority is also what audit provenance would record. A transaction hands its
captured actor to write planning as an
[Actor Identity](../../core/spec/m-unit-work.md#actor-identity): a subject verbatim, or
`db-login:` followed by the login. The specification reserves that input so provenance
can later be added inside planning without changing its interface. Until then, planning
must ignore it, and no implementation records audit provenance in stored rows.

## Common use cases

- **A service with one database account.** Derive one database-login scope at startup
  and share it.
- **A multi-user application that relies on database privileges.** Connect as the
  service's login, and derive a subject scope per request with the role that user's
  work should have. Grants and row-level security policies then apply to that role.
- **Rotating secrets and cloud identity tokens.** Supply a Credential Source; each new
  connection gets a current credential, and open connections are left alone.
- **Helpers that join the caller's transaction.** Pass the scope down, or derive an equal
  one; equal actors join.
- **Acting for another user.** Finish the current transaction, then begin a new one from
  that user's scope.

## Do it →

- [Database-login scope](../../languages/python/docs/guide/06-execution-authority.md#database-login-scope)
- [Subject scope](../../languages/python/docs/guide/06-execution-authority.md#subject-scope)
- [Credentials](../../languages/python/docs/guide/06-execution-authority.md#credentials)
- [Who the work is recorded as](../../languages/python/docs/guide/06-execution-authority.md#who-the-work-is-recorded-as)
