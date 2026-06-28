# Set-based writes return result objects

TypeScript set-based `update` and `delete` return result objects with at least `affectedRows` rather than raw numbers. Result objects leave room for optimistic-lock diagnostics and dialect metadata without changing the public API.
