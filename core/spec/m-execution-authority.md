# Execution Authority Contract (`m-execution-authority`)

Status: normative.

This module defines which actor a database operation executes as, how that authority is scoped, and how a joining call proves that it belongs to the active transaction. It does not define provider role syntax, session-reset SQL, authorization policy, or application authentication.

The keywords MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, and MAY are normative.

## Terms

- **Principal** — the application-supplied pairing of one Subject Identity and one Database Authorization.
- **Subject Identity** — the nonempty application subject string read from a Principal and preserved verbatim.
- **Database Login Identity** — the provider-authenticated login captured by an opened Database runtime. Its audit projection uses the reserved `db-login:` prefix.
- **Database Authorization** — an immutable provider-owned value that describes the database privilege context paired by a Principal. Core treats this value as opaque.
- **Execution Actor** — the immutable authority captured by an Execution Scope: either a Subject Identity paired with Database Authorization or a Database Login Identity using the runtime login's existing authority.
- **Execution Scope** — the explicit, runtime-affine capability through which work is invoked. It captures exactly one Execution Actor for its lifetime.
- **Capture** — copying the invoking Execution Scope's immutable Execution Actor into transaction state after begin succeeds.

## Principal contract

A Principal MUST carry one nonempty subject string and one Database Authorization value. Implementations MUST preserve the subject string verbatim for identity equality; they MUST NOT trim, case-fold, normalize, parse, or reinterpret it.

The exact `db-login:` prefix is reserved for Database Login Identity audit projections. A public subject-construction operation MUST reject any supplied subject beginning with that prefix. A Database Login Identity MUST be constructed only from provider-authenticated runtime information; application input MUST NOT choose its value or claim database-login mode by supplying a prefixed subject.

Two Subject Identities are equal exactly when their preserved strings are equal. A subject actor is never equal to a database-login actor, including when an application subject text resembles the login's audit projection.

Scope creation MUST read each Principal component once and retain the captured immutable values rather than the Principal object. Principal object identity MUST NOT be observable in actor equality.

## Database Authorization contract

Database Authorization is an opaque, immutable provider value. Core may retain it, compare it for equality, and pass it back to the provider; core MUST NOT inspect provider syntax or derive privileges from it.

The provider defines how a Database Authorization value is created and how it configures a checked-out connection. A provider MUST bind the value into the session before admitting application work under the associated Subject Principal. Failure to establish that authorization is a begin failure: no application callback runs and no transaction actor is captured.

Two Database Authorization values are equal only under the defining provider's value equality. Values originating from different opened Database runtimes MUST NOT be treated as interchangeable merely because their diagnostic representations match.

The database-login mode carries no caller-supplied Database Authorization. It uses the provider-authenticated login authority already owned by the opened runtime.

## Execution Actor equality

An Execution Actor is equal to another exactly when:

1. their identity modes and identity values are equal; and
2. both use database-login mode, or both carry equal Database Authorization values.

Subject Identity equality alone is insufficient. The same subject operating under two different Database Authorization values is two different Execution Actors. Conversely, two independently created scopes with equal Subject Identities and equal Database Authorization values carry equal actors.

Equality MUST NOT consult mutable session state, ambient process state, thread locals, task locals, or callback nesting.

## Scope creation and use

Every database operation MUST be invoked through an explicit Execution Scope. The API MUST NOT infer a Principal from ambient thread-local, task-local, request-global, or process-global state.

Application callers select subject mode by supplying a Principal when deriving a scope from an opened Database runtime. Its Subject Identity and provider-created Database Authorization are REQUIRED together.

Infrastructure callers MAY explicitly select database-login mode when deriving a scope. The opened runtime supplies the Database Login Identity; the caller supplies neither its identity nor a Database Authorization value.

Omitting a subject does not implicitly mean database-login mode in production. A caller must choose a scope-creation operation or argument that makes the mode explicit. Compatibility case documents may omit their outer selector for historical cases; the language runner interprets that absence by explicitly selecting database-login mode before invoking production code.

An Execution Scope is affine to the opened Database runtime that created it. Using it with another runtime MUST be refused before checkout or callback entry. A scope captures immutable values at creation and MUST NOT observe later mutation of caller-owned inputs.

Closing a Database runtime invalidates its scopes according to the database lifecycle contract. Scope existence does not extend runtime lifetime.

## Transaction capture

On each outer unit-of-work attempt, the runtime MUST establish the selected authorization before beginning application work. Once transaction begin succeeds, the transaction captures the invoking scope's Execution Actor.

The captured actor is immutable for the transaction's lifetime, including retries. Each retry attempt re-establishes the same captured actor on its newly acquired connection. A retry MUST NOT re-read ambient or caller-mutated identity state.

No transaction actor exists when checkout, authorization setup, or transaction begin fails. Such a failure remains the existing boundary-begin failure and MUST NOT be reported as an authority mismatch.

Standalone operations execute under their invoking scope's actor for their acquisition. They MUST apply the same provider authorization setup and cleanup obligations as transactional operations, but they do not create joinable transaction state.

## Join authority

An unqualified join is a call made through the active Execution Scope without independently selecting another scope. It reuses the enclosing transaction actor by construction.

An explicitly scoped joining call retains its own captured scope actor even when it enters code already inside a transaction. Implementations MUST NOT overwrite that selected actor with the active transaction actor before checking equality.

A joining call is admitted only if its selected actor equals the transaction's captured actor. Equal values from independently derived scopes MUST be accepted; object identity and scope identity are not authority criteria.

The mandatory join refusal order is:

1. verify that the active transaction may be joined by the current execution owner under `m-unit-work`;
2. verify that the active transaction is not rollback-only under `m-unit-work`;
3. compare the joining Execution Actor with the transaction's captured actor and refuse unequal actors as **authority mismatch**;
4. compare transaction options and apply the existing option-conflict rule; and
5. enter the joined body.

Authority mismatch MUST therefore win over option conflict when both differ. It MUST be detected before the joined body starts and before any database operation for that body. The active transaction remains the enclosing caller's transaction; refusing the nested body does not itself replace its actor or invent a second transaction.

Switching Principal or Database Authorization inside an active transaction is forbidden. A caller that needs different authority must use a non-joining outer boundary after the current transaction settles.

## Provider binding and revocation

A provider MUST apply subject authorization after checkout and before transaction begin or standalone application work. It MUST scope that authorization to the single acquisition.

On every exit path, the provider MUST attempt to revoke subject authorization before releasing the connection. This includes successful commit, rollback, callback failure, retry, begin failure after authorization setup, cancellation, and standalone-operation completion.

Cleanup has exactly the portable terminal results defined by `m-db-port`:

- **returned** — revocation and ordinary cleanup completed and the connection was returned;
- **invalidated** — safe reuse was not established and the connection was deliberately discarded; or
- **release-unconfirmed** — release was attempted but at least one cleanup condition prevented the runtime from confirming return or invalidation.

An authorization-revocation failure MUST prevent an ordinary return. The provider SHOULD invalidate the connection; if invalidation also cannot be confirmed, the result is release-unconfirmed. Cleanup failure does not rewrite an already settled application outcome, but it is observable through lifecycle diagnostics.

The verbs **release** and **released** name the operation and lifecycle observation.

## Diagnostics and confidentiality

Lifecycle diagnostics MAY identify Principal mode and a safe Principal representation. They MUST NOT serialize Database Authorization values, provider credentials, role-setting SQL, authentication tokens, or secrets.

Providers SHOULD expose stable, non-secret reason categories for authorization setup and revocation failures. Diagnostic rendering MUST NOT be used for Execution Actor equality.

## Compatibility case selectors

Boundary cases select authority independently from transaction options through `when.actorIdentity` and, for subject mode, `when.databaseAuthorization`. A joining boundary action may carry the same pair to select its own scope. Absence on a joining action means reuse of the enclosing scope.

The case selector `{kind: subject, value: S}` requires a nonempty sibling `databaseAuthorization` fixture name. `{kind: database-login}` carries neither a value nor an authorization. The fixture name is provider-neutral test vocabulary; each provider owns its concrete Database Authorization values.

The canonical authority cases prove:

- an unqualified join and an independently scoped equal actor both join successfully;
- equal authorization with a different Principal is refused;
- equal Principal with different authorization is refused;
- subject mode and database-login mode are never equal; and
- independently selected database-login scopes for one runtime compare equal.

## Non-goals

This module does not define application authentication, user directories, permission policy, row-level-security rules, provider role names, credential rotation, connection-pool implementation, or logging redaction beyond the confidentiality boundary above. It defines the portable authority values and lifecycle invariants those mechanisms must respect.
