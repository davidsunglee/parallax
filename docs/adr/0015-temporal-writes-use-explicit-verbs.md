# Temporal writes use explicit verbs

Temporal writes use explicit operation verbs rather than overloading ordinary update and delete semantics. This makes business-time changes visible and avoids treating audit-preserving operations like normal destructive writes.
