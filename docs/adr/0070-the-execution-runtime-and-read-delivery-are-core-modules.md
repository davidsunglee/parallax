# The execution runtime and read delivery are core modules

Everything a managed-object lifecycle would need unchanged belongs to the common
runtime, and two behavioral modules now own it. `m-read-delivery` turns a
validated, adopted read into a judged, identity-first Page and delivers it whole
or streamed: read planning and its reusable plan cache, effective read-lock
derivation, statement execution and Page assembly, stored-data judgement and its
public issue vocabulary, and the eager and streamed delivery contracts.
`m-execution` is the runtime over the database port: the Database Root and the
Execution Scopes derived from it, transaction-option resolution and join
comparison, Model Edition serving and adoption, the Attempt that runs one
physical transaction attempt, flush execution, and the row reads a write needs.
`m-snapshot-read` keeps Snapshot publication alone — Root View and projection
conflicts, root classification, Typed and Wire values, envelopes, and the
whole-graph pin.

This refines ADR 0022. That decision required a lifecycle-neutral common runtime
but left the runtime's execution half inside the Snapshot extension, because the
only place a behavioral module could compose SQL generation, the unit of work,
and the port was a "composition root" — a term the catalog reserves for
application wiring, not behavior. That wording, in `m-unit-work` and in the
Python topology's behavioral composition scope, is superseded: the unit of work
declares the ports it needs (flush execution, write-batch opening, and row
acquisition), `m-execution` implements them, and the composition root is again
only the application's selection of a lifecycle and an adapter.

Two seams carry the lifecycle difference, and both are invoked by the runtime
rather than returned to it. A read's **Publication** turns a Page's judged
states into a lifecycle's values inside the read's own activity, so no Page
leaves delivery and a stream's connection is still released before its roots
are published. A transaction's lifecycle surface is constructed from a fully
wired **Attempt**, so an application callback never sees an Attempt whose unit
of work is not ready; a join reuses it and a retry constructs a fresh one. A
lifecycle supplies those two and the values it turns into write instructions;
it opens no activity, owns no connection, and adopts no model.

Writes that read go through one row-acquisition port the unit of work declares.
Selection, target, and coverage reads describe what to read; the unit of work
consumes the judged rows inside the acquisition and owns routing, evidence,
cardinality, and binding. The one behavioral change this brings is target
precedence: a Locking target's acquisition decides cardinality before judging
any row, so excess rows are reported with their count rather than masked by an
invalid one among them. The portable stream activity is renamed from
`snapshot-stream` to `stream`, since the activity belongs to delivery rather than
to Snapshot; representation values stay `typed`, `wire`, and `rows`.

The graph gains `m-read-delivery`'s edges, including `m-read-lock` and
`m-opt-lock` for the lock a fetch takes, and `m-execution`'s, including
`m-batch-write` for the collapse eligibility model preparation wires into the
Write Planner. `m-snapshot-read` depends on both runtime modules, and neither
depends on a lifecycle.

Alternatives rejected:

- A third write-execution module would own almost no contract and serve one
  caller; write execution stays with the runtime that runs it.
- A behavioral composition-root module inside core would bend a term reserved
  for application wiring.
- `m-unit-work --> m-sql` would create a cycle and end the unit of work's
  SQL-free testability.
- Returning a Page for a lifecycle to publish would move the Read activity's end
  and a stream's connection release into every lifecycle, and let a Page escape
  its owner.
- Supplying model preparation from the lifecycle instead of an
  `m-execution --> m-batch-write` edge would make each lifecycle own model
  preparation; the unit of work cannot take that edge, because batch write
  already depends on it.

The contracts live in [`m-read-delivery`](../../core/spec/m-read-delivery.md)
and [`m-execution`](../../core/spec/m-execution.md); Snapshot publication
remains in [`m-snapshot-read`](../../core/spec/m-snapshot-read.md).
