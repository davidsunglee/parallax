# Managed graph mutation requires transactions

Mutating a managed object graph through objects or relationship references requires an explicit transaction. This keeps persistence, relationship wiring, and rollback behavior visible and consistent.
