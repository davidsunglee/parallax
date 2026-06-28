# Set-based writes target predicates or unresolved results

Set-based update and delete operations may target a predicate or an unresolved result collection. Implementations should preserve set-based execution where possible instead of forcing object materialization.
