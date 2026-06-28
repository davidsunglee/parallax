# Negation is postfix with explicit notExists

The TypeScript predicate DSL exposes postfix `.not()` on predicates and explicit `notExists` on to-many relationships. Equivalent spellings such as `attr.eq(value).not()` and `attr.notEq(value)` are both allowed because the former is compositional and the latter is convenient, while both serialize to the canonical operation algebra.
