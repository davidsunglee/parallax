# Relationships use references, not promise properties

Instance relationships are represented by explicit relation references such as `order.customer.get()` and managed relationship collections such as `order.lineItems`, rather than Promise-valued properties. This makes lazy I/O visible, gives relationship mutation and loaded-state behavior a home, and avoids making domain properties look like plain JSON objects when they carry Parallax runtime protocol.

To-one relation references expose `get`, `required`, `set`, and `clear`. `get` returns the related object or `null`, `required` throws `ParallaxNotFoundError` when absent, and `set` / `clear` mutate the association rather than the related object's attributes and therefore require an active transaction.
