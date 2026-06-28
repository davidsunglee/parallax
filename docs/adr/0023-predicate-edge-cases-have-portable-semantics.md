# Predicate edge cases have portable semantics

Predicate edge cases such as null comparisons, empty membership checks, and identity predicates need portable semantics. Language APIs may offer conveniences, but they should not delegate these cases to surprising database defaults.
