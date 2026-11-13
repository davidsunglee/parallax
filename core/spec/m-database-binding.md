# m-database-binding — Database Binding

A **Database Binding** is one deployment's physical placement of a model's
tables and sequences: which location each table and each logical allocator
lives in, and under which physical name. It is a standalone immutable value.
It is neither part of Entity identity nor connection configuration, and one
logical model is placed differently by different bindings.

| Concern | Owner |
|---|---|
| Entity identity, declared storage names, logical allocator identity and policy | the model (`m-metamodel`, `m-storage-layout`, `m-pk-gen`) |
| Physical locations and physical names of tables and sequences | the Database Binding |
| Connectivity, credentials, authorization, connection lifecycle | the database adapter (`m-db-port`) |
| Provisioning locations, grants, and migration execution | deployment tooling, outside Parallax |

The canonical document schema is
[`core/schemas/database-binding.schema.json`](../schemas/database-binding.schema.json).
It owns the serialized structure; this module owns what a binding means and
how a malformed one is reported. Shared accepted and rejected documents live
under `core/compatibility/bindings/`, where `default.yaml` is the corpus-wide
default binding per dialect.

## The binding document

A document carries `format_version` (always `1`) and `backend`, which selects
the **location** shape every section uses:

| Backend | Location | Qualifies |
|---|---|---|
| `postgres` | `{ schema }` | a schema inside the database the adapter's endpoint selects |
| `mariadb` | `{ database }` | a database on the connected server |

Its sections are each named for what their keys are:

- `default` — one location for every table and sequence nothing more specific
  places;
- `namespaces` — a location per **exact** Entity Namespace;
- `entities` — an override per mapping owner, keyed by its exact canonical
  Entity identity (`m-metamodel`), never by a spelling relative to a model;
  an override carries the location keys, a `table` name, or both;
- `sequences` — an override per logical allocator, keyed by its exact
  allocator key (`m-pk-gen`); an override carries the location keys, a
  `sequence` name, or both.

Every physical identifier component is a raw, nonempty string. A dot, a quote
character, letter case, or a reserved word is part of the component, never
syntax: qualification is structural, and a backend quotes each component
independently.

## How a binding places a model

A mapping owner's location comes from the first entry that supplies one: its
own `entities` entry, then the entry for its own Entity Namespace, then
`default`. Its physical table name is its entry's `table`, or else its declared
storage name. A logical allocator's location comes from its own `sequences`
entry, then `default`; its physical sequence name is its entry's `sequence`, or
else its allocator key. Nothing else supplies placement: no connection default,
`search_path`, or current database applies.

- **Namespaces match exactly.** `audit` never covers `audit.billing`, and an
  unnamespaced owner uses only `default`.
- **The owner's own namespace applies.** A table-per-hierarchy family is placed
  by its root's namespace; each table-per-concrete-subtype concrete subtype by
  its own.
- **Sequences ignore namespaces.** An allocator never follows the location of a
  table that draws keys from it.

## One normalized value

A binding written as a document and a binding constructed from typed values
normalize through one implementation to one immutable value, and every ingress
reports the same problems at the same paths. Normalization:

- copies every supplied map, so later changes to the caller's maps cannot
  change the binding;
- keys `entities` by Entity Identity, parsed with the canonical parse rule;
- orders each map canonically — namespaces and allocator keys by codepoint,
  owners by Entity Identity order;
- treats an omitted key or section as absent, and an empty section as omitted.
  A `null` value is an invalid value, not an omission.

Serializing a binding projects its normalized value: `format_version`,
`backend`, then each nonempty section in the order above, each map in
canonical order. Reading the serialized form back yields an equal binding.

## Definition diagnostics

A binding refused for its own shape is one **binding refusal** with phase
`binding-definition-rejected`, carrying **every** issue. An issue is
`(code, path, related)`: `path` addresses the offending position in the
document's own vocabulary — `("entities", "commerce.Customer", "table")` —
whether the binding was a document or typed values, and `related` names other
entries a problem involves. Issues are unique and ordered by path, comparing
segments by codepoint, then by code, then by related paths; explanatory text
never participates.

A binding is read for one backend. When `format_version` is missing or not the
integer `1`, or `backend` is missing or names another backend, the sections'
shape is undecided, so only those issues and unknown top-level keys are
reported.

| Code | Meaning |
|---|---|
| `binding-syntax-invalid` | the text is not well-formed in its declared format; path `()` |
| `binding-value-invalid` | a value has the wrong shape, such as a non-object document or section, a non-object location or entry, or a non-string identifier |
| `binding-field-unknown` | an object carries a key its position does not define |
| `binding-field-missing` | a required key is absent: `format_version`, `backend`, or a location's component |
| `binding-version-unsupported` | `format_version` is present but not the integer `1` |
| `binding-backend-mismatch` | `backend` is present but not the reading backend |
| `binding-namespace-key-invalid` | a `namespaces` key is not an Entity Namespace |
| `binding-entity-key-invalid` | an `entities` key is not an exact canonical Entity identity |
| `binding-sequence-key-invalid` | a `sequences` key is not a nonempty allocator key |
| `binding-identifier-invalid` | a physical identifier component is empty |

Definition validity is a property of the binding alone. Whether each key names
something a given model declares, and whether the binding places every table
and sequence of that model distinctly, are decided when the binding is resolved
against the model, and are reported under the separate phase
`binding-resolution-rejected`.
