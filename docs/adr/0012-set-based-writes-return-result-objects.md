# Set-based writes return result objects

Set-based writes return explicit result objects rather than bare counts or booleans. This leaves room for affected counts, temporal details, conflict information, and dialect-specific diagnostics without changing the operation shape.
