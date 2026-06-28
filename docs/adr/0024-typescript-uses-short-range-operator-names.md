# TypeScript uses short range operator names

The TypeScript predicate DSL uses `gt`, `gte`, `lt`, and `lte` for range comparisons, while keeping clearer names such as `eq`, `notEq`, `isNull`, `isNotNull`, `in`, and `notIn` for other predicates. These names are compact, familiar in TypeScript query APIs, and still map directly to the canonical Parallax operation names.
