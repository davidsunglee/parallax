# Nested transactions join the active transaction

Calling `transaction` while a TypeScript transaction is already active joins the existing transaction and unit of work rather than creating an independent nested transaction or savepoint. The inner callback cannot commit independently, and an inner failure rolls back the enclosing transaction, keeping the first transaction model simple.
