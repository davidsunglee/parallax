---
status: superseded in part by ADR-0030
---

# Transaction reads lock by default

Reads performed through a transaction use the transaction's correctness semantics, including locking where required by the implementation and dialect. Parallax does not make weaker transaction reads the default optimization path.
