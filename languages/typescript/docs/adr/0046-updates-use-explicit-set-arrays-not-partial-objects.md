# Updates use explicit set arrays, not partial objects

The TypeScript `update` API expresses changes as generated assignment expressions inside `{ set: [...] }` rather than as partial objects. This keeps updates on the same typed expression DSL as predicates, separates the target from the changes, and avoids ambiguity around unmapped properties, omitted fields, `undefined`, nulls, and future computed assignment forms.
