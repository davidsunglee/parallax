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
reports the same problems at the same paths. A YAML binding document is read
under the YAML 1.2 core schema, the schema `m-case-format` fixes for the
corpus: a plain scalar is null, a boolean (`true`/`false` spellings), an integer
(decimal, `0o`, `0x`), or a float only in that schema's spellings, and every
other plain scalar — `yes`, `off`, `1_000`, `1:30`, or a bare date — is the
string written. Serialized YAML quotes every string a YAML 1.1 or 1.2 core
reader would resolve to another type. Normalization:

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
| `binding-identifier-invalid` | a physical identifier component is empty; at resolution, also a resolved component containing NUL or longer than the backend's identifier byte limit |

Definition validity is a property of the binding alone. Whether each key names
something a given model declares, and whether the binding places every table
and sequence of that model distinctly, are decided when the binding is resolved
against the model, and are reported under the separate phase
`binding-resolution-rejected`.

## Resolving a binding against a model

Resolving a binding against an accepted model yields one **resolved binding**:
for every mapping owner (`m-storage-layout`) one **physical table**, and for
every logical allocator (`m-pk-gen`) one **physical sequence**. Each is a
qualifier — the location's components, in order — and a raw local name, never a
dotted string. Resolution either places the whole model or refuses it with one
binding refusal of phase `binding-resolution-rejected` carrying every issue.
Resolution is structural and offline: it checks no schema, grant, or object's
existence.

Every key must name something the model declares, so a typo fails loudly
instead of placing a table at the default:

| Code | Meaning | Path |
|---|---|---|
| `binding-entity-unknown` | an `entities` key names no Entity the model declares | the entry |
| `binding-entity-owns-no-table` | an `entities` key names an Entity that owns no table, such as a table-per-hierarchy descendant or a table-per-concrete-subtype abstract position | the entry |
| `binding-namespace-unknown` | a `namespaces` key names no Entity Namespace the model declares an Entity in | the entry |
| `binding-sequence-unknown` | a `sequences` key names no logical allocator the model declares | the entry |
| `binding-table-unresolved` | no entry, namespace, or default supplies a mapping owner's location | `("entities", owner)` |
| `binding-sequence-unresolved` | no entry or default supplies an allocator's location | `("sequences", allocator)` |
| `binding-identifier-invalid` | a resolved component is empty, contains NUL, or exceeds the backend's identifier byte limit | the position supplying it: the entry, namespace, or `default`, or the entry's `table` / `sequence` |
| `binding-table-collision` | a mapping owner resolves to the physical table an earlier owner (canonical owner order) holds | the later owner's entry, related to the earlier one's |
| `binding-sequence-collision` | an allocator resolves to the physical sequence an earlier allocator (codepoint order) holds | the later allocator's entry, related to the earlier one's |
| `binding-sequence-table-collision` | a physical sequence and a physical table share one qualifier and name | the allocator's entry, related to the owner's |

Components compare exactly: no case folding, no trimming, and no dotted-name
parsing. Tables and sequences share one relation namespace per qualifier on both
backends, so equal qualifier and name are the same relation. Collisions are
checked within one resolved binding, never across roots. Server settings that
change identifier comparison, such as MariaDB's `lower_case_table_names`, are
outside what offline resolution can establish.

### Resolved tables

Each resolved table carries its mapping owner, its physical table, its SQL
reference — every component quoted alone by the backend's dialect
(`m-dialect`), rendered once at resolution — and, for a temporal table, the
names of its temporal constraints. Those names are derived once from the raw
physical local name and the logical definitions `m-storage-layout` compiles,
following that module's `pxc_` convention. A binding that pins a local name
therefore fixes every derived name however the declared name changes; one that
moves a table between qualifiers changes no derived name. Every statement and
DDL naming the table reads this one reference.

## Relocation between two resolved bindings

Two resolved bindings of one backend are compared by **relocation**: every
mapping owner both hold whose physical table differs is a **table relocation**
(owner, earlier physical table, later physical table), in canonical owner order,
followed by every logical allocator both declare whose physical sequence differs
as a **sequence relocation** (allocator, earlier, later), in codepoint order. An
owner or allocator only one side holds was added or removed, not relocated.

A serving model publishes a candidate prepared under a binding only when the
candidate's backend is the expected selection's and the comparison finds no
relocation (`m-execution`); `m-model-evolution` reports the same relocations as
coordinated operations. Publishing a binding change therefore needs no
replacement root while nothing surviving moves, and every move needs a
coordinated migration behind one.
