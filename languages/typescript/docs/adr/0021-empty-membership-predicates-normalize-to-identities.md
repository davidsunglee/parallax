# Empty membership predicates normalize to identities

The TypeScript DSL accepts empty arrays for membership predicates and normalizes them before serialization: `attr.in([])` becomes `none`, and `attr.notIn([])` becomes `all`. This avoids invalid SQL and makes dynamically built predicates follow ordinary set semantics.
