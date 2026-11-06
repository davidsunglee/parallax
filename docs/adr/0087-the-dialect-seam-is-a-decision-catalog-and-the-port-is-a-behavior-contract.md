# The dialect seam is a decision catalog and the port is a behavior contract

The database-dialect seam is now a catalog of decisions judged by the output each
dialect's answers produce, and `m-db-port` is a behavior contract each language
spells in its own public port. Neither fixes a signature. The overview names them
that way, and a binding documents its own port: Python's is in
`languages/python/spec/execution.md`.

The alternative was to treat both as literal interfaces. That would have held every
binding to one set of signatures and withdrawn `m-sql`'s permission to lower through
an external query representation. Nothing observes a signature: conformance grades
emitted SQL, binds, results, and failures. Python's dialect already differed from the
interface as written, and its port had stopped owning its carriers.

Parsing follows the same line. A dialect states the rule for what its cells spell,
and the adapter applies it, because a compiled loader on the read path is the right
place for that work and no observer can tell where the code sits. The cost is that
this rule no longer proves a value's precision by reading the dialect, so that proof
is owed explicitly by the provider smoke contract.

`bytes` is the one cell that crosses the port undecoded. The port carries no per-cell
type, so the cell arrives as projected text and is decoded above the port, and a
caller always receives decoded bytes. That text is the dialect's hexadecimal spelling
rather than Wire text, so it decodes in either case while Wire itself stays strict.
This was not a matter of wording. MariaDB 12.3.3 returns `0A1B` from `hex()`, Python
decoded the cell as strict Wire and reported a valid value as undecodable, and the
reference harness compared the text verbatim. `m-core-011` is the witness on both
dialects. The harness folds the observed cell, so an authored value stays strict.

Two other answers for `bytes` were rejected. Having the port carry which cells are
encoded would have added a per-cell type to a boundary that deliberately has none.
Projecting `bytes` natively would have changed the existing goldens to suit a
question about decoding.
