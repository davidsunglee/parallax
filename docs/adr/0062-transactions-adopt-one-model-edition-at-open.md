# Transactions adopt one Model Edition at open

A Parallax Handle obtains the accepted Metamodel it serves through a Metamodel
Provider rather than holding one for the life of the process, so a running
service can take up an evolved model without restarting. The provider answers
every request with the current model and its Model Edition, an opaque
equality-only token, or raises; how and when it re-reads its own source is its
private policy, and the handle never falls back to a previously served edition
on its behalf. Each Parallax Transaction adopts exactly one edition when it
opens and serves it until commit or rollback: a joining nested transaction
inherits it, a retried attempt chooses afresh, and a standalone read is its own
adoption. The handle keeps one slot — the current edition with the derived
state compiled against it — and rebuilds that slot only when the provider's
token differs, so an unchanged model costs one comparison per open and an
in-flight transaction keeps the edition it started with. Every read result,
stream page, and wire snapshot is stamped with the edition it was served
under, and the first activity to meet a new edition reports the adoption
through the execution lifecycle.

Edition Overlap is classified, not prevented. Only a Unilateral Evolution may be
applied to a live tenant, and publication of an edition asserts that the
physical schema already satisfies it, so a transaction on the earlier edition
retains a valid model-facing operation surface even where behavior or enforcement
differs. Some unilateral operations are nevertheless Overlap-Visible: an
attribute widened to nullable, a string length widened, or a concrete subtype
added to a shared table-per-hierarchy family can put rows in the database that
the earlier edition's model does not admit, and a read on that edition then
reports them as stored data violating its model, at the result root, exactly as
any other stored-data violation is reported. The stamped edition lets the
caller distinguish a stale edition from corrupt data and re-run the
transaction, which adopts the current edition. No in-process barrier could do
better: a tenant runs many processes whose providers move independently, so
the overlap window is inherent to rollout and a single-process drain would
stall one process without closing it.

Failure reporting follows the same boundary without turning rollout policy into
transaction policy. The database boundary preserves neutral failure facts,
including the violated Physical Index Name when the database supplies one, and
the transaction surface pairs a failure escaping an adopted transaction with
its Adopted Edition while preserving the database failure as its cause. It does
not consult the provider on the failure path and does not make a unique-index
violation automatically retriable. The host may correlate those facts with its
own rollout state and decide whether replaying the whole use case is safe.

The alternatives were restarting the process per model change, which is fine
for rare batched changes but not for many teams editing one tenant's model
interactively; resolving the model per operation, which lets one transaction
compile its reads and writes against different models; and a push-based
provider that delivers models into the handle, which trades a token comparison
for threading, a mutable handle, and a delivery obligation on every provider.
The provider is deliberately a seam and not a module: its interface is one
method, the framework ships only the constant adapter, and it lives in the
metamodel module with the edition token because every result-producing module
must be able to name an edition.
