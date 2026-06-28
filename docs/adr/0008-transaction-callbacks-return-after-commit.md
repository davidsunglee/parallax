# Transaction callbacks return after commit

A transaction callback returns its value only after the transaction has successfully committed. If the transaction rolls back or commit fails, the operation fails instead of returning the callback value as if it were durable.
