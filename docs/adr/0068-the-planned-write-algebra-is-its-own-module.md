# The Planned Write algebra is its own module

The Planned Write algebra, the Write Observation vocabulary, and the predecessor evidence a temporal write retains form one behavioral module, `m-write-plan`, beneath both the unit of work that produces them and the SQL generation that lowers them. Before, `m-unit-work` owned them together with transactions, write instructions, buffering, claims, and the Write Planner, so `m-sql` took an edge to the whole unit of work in order to read the finalized steps it compiles, and any owner of write-settlement rules had to sit inside the unit of work or depend on all of it.

The new module holds what a finalized plan is made of and nothing that decides one: the closed Planned Write variants and their Insert Origin, Close Cause, rows, assignments, Write Target, Write Gate, and Affected Rows Policy; the Object Key and Observed State Key that address evidence; and the Write Observation and the Predecessor Row it retains, together with the compact positional evidence a materialized group carries. Resolving an authored row into planned member cells, including the refusal of a database-computed marker in a position that cannot express it, also lives here, because every producer of a planned row needs it and none of them should reach planning instructions to get it. The prepared assignment that operation consumes is declared here for the same reason; the unit of work still produces it.

`m-unit-work` keeps everything that buffers, plans, claims, executes, and publishes: write instructions and their preparation, coalescing and ordering, Write Settlement, the lifetime of observations, the affected-row enforcer, and the deferred-binding and completion machinery. `m-sql` now depends on `m-write-plan` instead of `m-unit-work`. The module states its direct dependencies on `m-core`, `m-metamodel`, `m-predicate`, `m-inheritance`, `m-document-codec`, and `m-temporal-read` even where another edge already implies one, as the lower catalogue entries do, so a reader sees what the algebra is stated in.

The split adds no isolation the Python binding did not already have for SQL generation: `m-sql` still reaches the unit of work through `m-deep-fetch`. Its value is ownership. The algebra has one owner that names no transaction or SQL construct, and a later owner of temporal settlement rules can depend on it without depending on the unit of work.

Alternatives rejected:

- Leaving the algebra in `m-unit-work` keeps SQL generation depending on transactional machinery for a vocabulary of values, and forces any separate settlement-rule owner to import the unit of work or be absorbed by it.
- Leaving planned-row resolution and its marker refusal in the unit of work while moving the algebra would make every other producer of planned rows import planning instructions.
- Naming only the edges the transitive closure requires would leave the module's real vocabulary implicit; the enforced closure is identical either way.
- Re-exporting the moved names from the unit-of-work package would keep two import paths for one owner.

The contract lives in [`m-write-plan`](../../core/spec/m-write-plan.md); write finalization remains in [`m-unit-work`](../../core/spec/m-unit-work.md).
