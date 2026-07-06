# Transaction callbacks return after commit

A transaction callback returns its value only after the transaction has successfully committed; if the transaction rolls back or commit fails, the operation fails instead of returning the callback value as if it were durable. A naive implementation returns the value as soon as the callback finishes, before commit. The rule is normative in `core/spec/m-unit-work.md` §Abort.
