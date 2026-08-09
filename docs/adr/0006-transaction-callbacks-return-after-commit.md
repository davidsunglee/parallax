# Transaction results return after commit

An outermost transaction invocation returns a Transaction Result containing the
Transaction Body's value and Execution Log only after the transaction has
successfully committed; if rollback or commit fails, the invocation fails
instead of returning the body value as if it were durable. A joined invocation
still returns its body value immediately because it owns no commit boundary,
but its result shares the outer transaction's live read-only Execution Log and
cannot expose a committed execution until that outer boundary commits. The
durability rule is normative in `core/spec/m-unit-work.md` §Abort.
