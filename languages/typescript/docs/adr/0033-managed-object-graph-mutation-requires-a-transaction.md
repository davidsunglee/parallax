# Managed object graph mutation requires a transaction

TypeScript writes require an active transaction, including `create`, set-based `update`, set-based `delete`, and managed object graph mutations. This gives users one rule for persistence: reads may use the `Parallax` handle directly, but every write belongs to a visible unit of work and flushes at transaction commit.
