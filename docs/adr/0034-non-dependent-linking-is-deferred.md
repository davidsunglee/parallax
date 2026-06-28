# Non-dependent linking is deferred

The first TypeScript API does not mutate non-dependent relationships through relationship collections. Callers change those associations through explicit foreign-key updates or explicit join-entity writes; a later `link` / `unlink` API may hide join-table mechanics once the metamodel can describe association-table mappings directly.
