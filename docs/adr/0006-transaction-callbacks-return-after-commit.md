# Transaction callback values return after commit

An outermost transaction invocation returns the Transaction Body's value
directly only after the transaction has successfully committed; if rollback or
commit fails, the invocation fails instead of returning the body value as if it
were durable. A joined invocation returns its body value immediately because it
owns no commit boundary, while the outer invocation remains responsible for the
eventual commit or rollback. The durability rule is normative in
`core/spec/m-unit-work.md` §Abort.
