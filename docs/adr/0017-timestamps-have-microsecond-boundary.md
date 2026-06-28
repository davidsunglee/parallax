# Timestamps have microsecond boundary

The core timestamp contract uses a microsecond precision boundary. Implementations may map to runtime or database types with different native precision, but conformance is measured at the microsecond boundary.
