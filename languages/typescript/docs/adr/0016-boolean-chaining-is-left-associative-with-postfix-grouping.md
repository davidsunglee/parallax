# Boolean chaining is left-associative with postfix grouping

TypeScript predicate chaining with `.and(...)` and `.or(...)` is left-associative, and explicit precedence is expressed with postfix `.group()` on a predicate. A prefix helper would make grouping visually clearer, but postfix grouping keeps the operation discoverable through autocomplete and avoids requiring users to find an extra import for common predicate authoring.
