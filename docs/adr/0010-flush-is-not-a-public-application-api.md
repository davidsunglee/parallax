# Flush is not a public application API

Parallax does not expose flush as a normal application-level write primitive. Implementations may flush internally when needed, but application code should reason in terms of transactions and operation results.
