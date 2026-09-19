# Execution authority is selected once per scope

Execution authority is selected explicitly when a caller derives an immutable execution scope from a resource-owning Database Root. The scope captures one actor and complete transaction-option defaults, owns no connection or runtime, and exposes modeled reads, streams, and unit-of-work entry. A root owns runtime resources, lifecycle installation, one transaction runner, model state, and coordinated close; it exposes authority selection and option derivation but no modeled execution verbs. This supersedes ADR 0034's per-operation Principal argument while preserving its prohibition on ambient or default application identity.

A subject scope reads an application Principal exactly once. The Principal is a structural protocol pairing a nonempty subject string with one provider-owned Database Authorization value. Capture validates the subject, reserves the exact `db-login:` prefix, binds the immutable authorization through the opened runtime, and then retains only the captured subject actor, authorization value, and bound acquisition source. It does not retain the Principal or an ancestor scope. Property exceptions propagate unchanged; only subject validation and a provider's invalid-authorization refusal become the stable invalid-principal error, with their causes preserved.

A database-login scope is a separate explicit choice. It captures the actual authenticated login identity established during runtime readiness, before publication, and projects it for audit as `db-login:` followed by that identity verbatim. Callers supply neither the login identity nor an authorization value. The runtime obtains the identity during its existing startup probe, under the original readiness budget, and records it exactly once. Scope creation performs no query.

Actor identity is a closed union of subject and database-login values. The audit projection is defined once: a subject is its captured string verbatim; a login is the reserved prefix plus its captured authenticated identity verbatim. Queries, predicates, includes, canonical query serialization, and query equality remain authority-free. A future entitlement consumer may receive captured context and enrich an internal query before planning, but does not mutate or identity-key the authored query.

Database Authorization is provider-owned and opaque to core. A provider binding must replace or contain the login's effective privileges for the acquisition; an adapter that cannot provide that guarantee refuses authorization rather than adding privileges. PostgreSQL installs a safely identifier-quoted session-level role before modeled work and restores the configured startup role before reuse. The binding requires session affinity for the acquisition; transaction- or statement-pooling proxies that can switch server sessions inside it are unsupported, and no reliable runtime proxy detector is claimed.

Each outer transaction captures its scope actor once. Retries reuse that capture. A joining call through the same scope inherits it without reevaluation; a call through an independently selected scope compares actor values, not scope or source identity. Equal subject and authorization values join. A different subject, different authorization, or mixed subject/login mode raises the stable transaction-authority error before the joined body. Independent database-login scopes from one root compare equal after root ownership succeeds.

Join preflight order is fixed: validate ordinary call arguments; require the same resource-owning root; require that the active unit of work is not rollback-only; compare captured execution authority; compare only explicitly supplied transaction options against the active resolved record; then enter the joined body. Authority mismatch therefore precedes option conflict. A caught preflight refusal does not doom otherwise healthy outer work, while allowing it to escape still causes the ordinary outer rollback.

ADR 0065's field-wise option rule composes unchanged. Root and scope `with_options` operations apply keyword-only partial patches to one complete immutable `DatabaseOptions` record: omission alone inherits, later explicit values win, and `None` remains invalid. Selecting authority preserves the current options. Options never select, clear, or replace authority, and scope derivation stores no ancestry or patch history.

Every modeled acquisition is created from the capture's bound source. Subject context entry installs authority before application admission; every exit attempts revocation and restoration before release. Unsafe, suspect, or unsuccessfully restored connections are disposed rather than repaired into reuse. Release reports `Returned`, `Invalidated`, or `ReleaseUnconfirmed`; cleanup failure preserves already-settled application outcomes and is never permission to replay.

Provisioning, migration, readiness, fixture loading, runtime shutdown, and other driver-control work remain outside the mandatory modeled scope boundary. They use infrastructure-owned control paths rather than a fabricated application Principal.

Alternatives rejected:

- A Principal argument on every operation reevaluates mutable claims, makes lazy delivery retain application objects, and lets one transaction be presented with several authority values.
- Ambient thread/task/request state hides authority from composition and makes retries and asynchronous delivery inherit by accident.
- A default or optional Principal creates unattributed production work; database-login mode must be selected explicitly instead.
- Authority inside `DatabaseOptions` conflates identity with overridable transaction policy and permits option derivation to switch privilege.
- Per-principal runtimes or pools make scopes resource owners and duplicate model, plan-cache, lifecycle, and shutdown state.
- Transaction-local role changes are insufficient for standalone work and complicate cleanup; session-level installation with restoration brackets the whole acquisition.
- Additive role membership does not establish containment and can silently preserve login privileges the selected Principal should not have.
