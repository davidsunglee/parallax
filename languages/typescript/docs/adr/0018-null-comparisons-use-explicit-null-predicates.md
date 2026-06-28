# Null comparisons use explicit null predicates

The TypeScript DSL rejects `eq(null)` and `notEq(null)` in favor of `isNull()` and `isNotNull()`. SQL equality against `NULL` evaluates to unknown rather than true, so explicit null predicates make the user's intent portable and avoid silently empty result sets.
