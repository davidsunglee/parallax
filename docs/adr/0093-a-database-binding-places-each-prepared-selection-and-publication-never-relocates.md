# A Database Binding places each prepared selection, and publication never relocates

One logical Domain Model has to serve several tenants, or an existing database whose
tables sit in other schemas under other names. Until now Parallax placed nothing: every
statement named a bare declared table, and PostgreSQL found it through the connection's
`search_path`. We separate four concerns that this blurred. The model owns identity:
Entity Identities, Entity Namespaces, declared storage names, and logical allocators.
A **Database Binding** owns placement: each table's and each sequence's location and
physical name. The adapter owns connectivity, credentials, and the authorization of
connections. Deployment tooling owns provisioning, grants, and running migrations.

A binding is a standalone immutable value. It is required wherever a model is prepared
or evolved, and resolved once per prepared selection or evolution endpoint into the
physical facts every statement, DDL, and provenance path reads
([m-database-binding](../../core/spec/m-database-binding.md)). Nothing falls back to a
connection's current schema or database.

We rejected three other homes for placement:

- **The model.** A schema option on the entity header would force one model copy per
  deployment. It would also turn an Entity Namespace, which is identity, into placement.
  A binding may select a location by namespace, but the namespace places nothing itself.
- **The connection.** A `search_path` or an adapter setting is invisible to schema
  generation and evolution. A same-named table earlier on the path silently redirects it.
  It also ties placement to whoever holds credentials.
- **An implicit default.** Defaulting to `public`, or to the connection's schema, would
  keep existing callers compiling while leaving their placement unstated. Existing
  callers are refused with migration guidance instead.

The binding format is shared across backends: PostgreSQL locations are schemas and
MariaDB locations are databases. The reference harness proves MariaDB placement; Python
ships no MariaDB backend. This decision fixes where each logical allocator's sequence
resolves, not how sequences are created or allocated.

## Publication

We considered fixing one binding per Database Root, so that any binding change would
need a replacement root. We chose to let a Serving Model publish a candidate prepared
under a changed binding, just as it publishes a model edition:

- a selection already carries its resolved placement;
- each execution adopts exactly one selection;
- read plans are cached per selection.

So only a moved object could mix two placements. Publication refuses a candidate for
another backend, and one under which any table or sequence the expected selection holds
resolves elsewhere ([m-execution](../../core/spec/m-execution.md#model-editions)).
Evolution reports those same relocations as coordinated operations, from the one
comparison publication uses ([m-model-evolution](../../core/spec/m-model-evolution.md)).
Growth, removal together with its binding entries, and a default change that pins every
survivor therefore roll out hot. Moving a surviving table or sequence is a coordinated
migration behind a replacement root.

Derived constraint and index names follow a table's physical local name and never its
qualifier. A move between qualifiers therefore keeps them, while a physical rename
changes them, and deployment tooling reconciles the derived names before replacement
roots serve. Parallax generates no statement that provisions a location, moves or
renames a table, or reconciles derived names. Preparation and publication check
structure only, never that an object exists or may be used.
