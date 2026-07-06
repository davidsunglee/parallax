# TypeScript uses one fluent expression DSL

The TypeScript API uses one generated, type-safe fluent expression DSL for predicates and assignments instead of supporting both Prisma-style object filters and expression-builder filters. This keeps autocomplete strong, avoids two query languages, and maps directly to the canonical Parallax operation algebra.

The DSL bundles these surface decisions (each with its rejected alternative):

- Entity symbols expose `all()` and `none()` constructors for the identity predicates, and `find()` without a predicate is shorthand for `find(Entity.all())`; keeping these on the entity symbol makes dynamic predicate construction explicit without adding global helpers.
- Boolean chaining with `.and(...)` and `.or(...)` is left-associative, and explicit precedence uses postfix `.group()` on a predicate. A prefix helper would make grouping visually clearer, but postfix keeps the operation discoverable through autocomplete and avoids an extra import.
- Negation is postfix `.not()` on predicates, with explicit `notExists` on to-many relationships. Equivalent spellings such as `attr.eq(value).not()` and `attr.notEq(value)` are both allowed — the former is compositional, the latter convenient — and both serialize to the canonical operation algebra.
- The DSL rejects `eq(null)` and `notEq(null)` in favor of `isNull()` and `isNotNull()`: SQL equality against `NULL` evaluates to unknown rather than true, so explicit null predicates make intent portable and avoid silently empty result sets.
- Range comparisons use the short names `gt`, `gte`, `lt`, and `lte`, while other predicates keep clearer names (`eq`, `notEq`, `isNull`, `isNotNull`, `in`, `notIn`); the short forms are familiar in TypeScript query APIs and still map directly to the canonical operation names.
- String predicates accept an options object for case-insensitive matching rather than separate insensitive method names, keeping the attribute method surface compact while preserving the core operation's `caseInsensitive` flag.
- The DSL accepts empty arrays for membership predicates and normalizes them before serialization: `attr.in([])` becomes `none`, and `attr.notIn([])` becomes `all`. The core algebra requires non-empty membership lists, so this normalization is a TypeScript boundary rule; it avoids invalid SQL and makes dynamically built predicates follow ordinary set semantics.
