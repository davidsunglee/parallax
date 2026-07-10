# m-inheritance — Inheritance Mapping

`m-inheritance` is the **class-hierarchy mapping** strategy a metamodel entity may
declare. It depends on `m-descriptor` (the entity it annotates).

Inheritance is a **closed tree** of entities: one abstract **root**, zero or more
abstract intermediate nodes, and the concrete, instantiable leaves (or any
concrete node). The family behaves conceptually like a **discriminated union** —
every returned row has exactly one concrete variant — even when the physical
strategy uses no discriminator column. An entity that participates declares an
`inheritance` element naming its **role** and, for the root, the family
**strategy**.

## Roles

| Role | Meaning | Table / rows |
|---|---|---|
| `root` | the abstract hierarchy root; declares the family strategy and (for table-per-hierarchy) the `tag` column | **tableless, rowless** — a polymorphic position naming the whole family |
| `abstract-subtype` | an abstract interior node between the root and its concrete descendants | **tableless, rowless** — a polymorphic position naming its concrete descendants |
| `concrete-subtype` | an instantiable participant, the only one that owns rows | owns the physical table the family strategy requires |

The `root` and every `abstract-subtype` are **abstract**: tableless, rowless, and
addressable only as **polymorphic entity positions** (`targetEntity`, a `narrow`
target, or a relationship target). Only a `concrete-subtype` is instantiable and
row-owning. An `abstract-subtype` MAY have abstract or concrete descendants; a
`concrete-subtype` is the leaf of instantiation.

## Strategies

The **root alone** declares the family strategy; every descendant inherits it and
**MUST NOT** redeclare it. Core admits exactly two strategies and **rejects the
rest**:

| Strategy | Meaning | In core? |
|---|---|---|
| `table-per-hierarchy` | the whole family in **one** shared table; rows discriminated by the root's `tag` column carrying each concrete subtype's `tagValue` | **yes** |
| `table-per-concrete-subtype` | one table **per concrete subtype**; no shared table, no tag | **yes** |
| `table-per-leaf` | the pre-ADR name for per-concrete-subtype mapping | **REJECTED** — strictly replaced by `table-per-concrete-subtype`; not a canonical alias |
| `table-per-class` | one table per class, joined at query time | **REJECTED** — the metamodel schema does not admit it |

`table-per-class` is intentionally excluded: per-query joins to assemble a single
object are exactly the hidden N+1 / fan-out cost the suite exists to prevent, and
the two admitted strategies cover the field's real use. `table-per-leaf` is the
retired name; the descriptor vocabulary uses `table-per-concrete-subtype`. A
descriptor declaring either **MUST** fail schema validation (negative
metamodel-extension tests assert this).

## Descriptor surface

| Property | Values / meaning |
|---|---|
| `role` | `root` \| `abstract-subtype` \| `concrete-subtype` (REQUIRED) |
| `strategy` | `table-per-hierarchy` \| `table-per-concrete-subtype`; declared by the `root` ONLY (REQUIRED there, FORBIDDEN on any descendant) |
| `parent` | the entity this node directly extends (REQUIRED for a non-root, FORBIDDEN for a root) |
| `tag` | `{ column }`, the shared-table discriminator column — declared on the `table-per-hierarchy` ROOT only (FORBIDDEN elsewhere and under table-per-concrete-subtype) |
| `tagValue` | the value the tag column carries for THIS concrete subtype's rows — a `concrete-subtype` under `table-per-hierarchy` only |

The pre-ADR `discriminator` / `discriminatorValue` vocabulary is **strictly
replaced** by `tag` / `tagValue`; the inheritance block is closed, so the retired
keys fail validation.

### Canonical descriptor blocks

Table-per-hierarchy root (abstract, tableless):

```yaml
inheritance:
  role: root
  strategy: table-per-hierarchy
  tag:
    column: kind
```

Abstract subtype (tableless):

```yaml
inheritance:
  role: abstract-subtype
  parent: Animal
```

Table-per-hierarchy concrete subtype:

```yaml
table: animal
inheritance:
  role: concrete-subtype
  parent: Pet
  tagValue: dog
```

Table-per-concrete-subtype concrete subtype:

```yaml
table: dog
inheritance:
  role: concrete-subtype
  parent: Pet
```

## Inherited members

Attributes, value objects, relationships, temporal axes (`asOfAttribute`), and
mutability declared on an abstract ancestor are **inherited by every descendant**.
A concrete subtype descriptor **does not repeat** inherited attributes merely to
satisfy `table-per-concrete-subtype`; validation and lowering **derive the full
inherited attribute/column chain from the ancestry** (root → … → self). A
concrete subtype whose members are entirely inherited declares no `attributes` of
its own (the conditional requirement in `m-descriptor`).

## Physical mapping

**Table-per-hierarchy.** The whole family maps to **one shared table** owned by
its concrete subtypes; the root's `tag` column distinguishes them. The shared
table physically carries the union of every concrete subtype's columns, so a
subtype-declared column is **nullable** in the shared table (a `card` row leaves
the `cash` column null and vice-versa). The `tag` column is **framework-owned
metadata, not a declared attribute**: a concrete-subtype read injects
`t0.<tag> = ?` (its `tagValue`); an abstract-target read projects the tag column
raw so `familyVariant` can be materialized (`m-sql` / `m-case-format`). `m-sql`
fixes the tag-filter golden SQL.

**Table-per-concrete-subtype.** Each concrete subtype maps to its **own table**;
no shared table and no tag exist. A concrete read is an ordinary single-table read
of that subtype's table — the subtype is selected by *which table* is queried.
Each concrete table **physically contains columns for the full inherited attribute
chain** plus the concrete subtype's own attributes, derived from the ancestry.

## Canonical concrete-subtype ordering

Whenever a family's concrete subtypes are **enumerated** in a canonical artifact,
they appear in one fixed **total order**: **ascending by concrete-subtype entity
name, compared codepoint-by-codepoint (Unicode scalar value)** — i.e. plain
**alphabetical order by entity name**. This order is a pure function of the entity
names and is **independent of the descriptor's declaration order and file layout**:
reordering the subtype entries in a model file, or splitting them across files,
never changes it. The **effective concrete-subtype set** of any polymorphic
position (root, abstract subtype, concrete subtype, or a resolved `narrow`) is
presented in this order.

This canonical sibling-set order is the one every downstream module uses to
enumerate a family's concretes:

- the table-per-hierarchy tag predicate `in (…)` list and its binds (`m-sql`);
- the table-per-concrete-subtype `union all` **branch order** (`m-sql`);
- the grouped-`OR` per-branch `EXISTS` **branch order** for polymorphic navigation
  (`m-navigate`, `m-sql`);
- the derived **narrowed view key** `<rel>[<Concrete>,<Concrete>]` (`m-deep-fetch`);
- the **per-subtype own-column blocks** of an abstract-read superset projection
  (`m-sql`, below).

Three orderings are deliberately **not** this alphabetical sibling order and are
specified elsewhere:

- The **inherited-column prefix** of a superset stays **ancestry order**
  (root → abstract-subtype → concrete): columns are enumerated down the inheritance
  chain, never alphabetized across it.
- A **single entity's own attributes/columns** keep their **declared order**.
- A `narrow` node's authored **`to` list** is preserved **verbatim** by serde
  (`m-op-algebra`); only the *resolved/effective* concrete set it denotes is
  canonicalized to this alphabetical order, so `to: [Pet]` and `to: [Cat, Dog]`
  round-trip as distinct spellings yet resolve to the same ordered set.

## Family invariants

The following cross-entity invariants hold for every family. They are **semantic**
(not expressible per-entity in the schema) and a model-aware validator **MUST**
reject a descriptor that violates one, before any SQL; the compatibility corpus
pins each as a portable `rejected` / `when.model` case with a
`then.rejectedRule`:

- **Parent resolution** — every `parent` resolves to another entity in the
  descriptor (`inheritance-unknown-parent`).
- **Acyclicity** — parent links form no cycle (`inheritance-cycle`).
- **Single root** — a family has **exactly one** root. A descriptor with
  inheritance participants but **no** root (a zero-root / abstract-orphan family) is
  rejected with `inheritance-missing-root`; one that reaches **more than one** root
  is rejected with `inheritance-multiple-roots`. (A concrete participant that never
  tops out at a root is the distinct concrete-without-abstract-root case below.)
- **Concrete under an abstract root** — every concrete subtype has an abstract
  root ancestor (`inheritance-concrete-without-abstract-root`).
- **Tableless abstract nodes** — a `root` / `abstract-subtype` declares no table
  (`inheritance-abstract-node-with-table`) and owns no fixture rows
  (`inheritance-abstract-node-fixture-rows`).
- **Root-only strategy** — a non-root does not redeclare the strategy
  (`inheritance-strategy-redeclared`).
- **Tag presence** — under table-per-hierarchy, **every** concrete subtype
  declares a `tagValue` (`inheritance-missing-tag-value`); the shared table cannot
  discriminate a subtype's rows without one. The per-entity schema leaves
  `tagValue` optional and delegates this presence rule (a family-strategy fact) to
  semantic validation.
- **Family-wide tag uniqueness** — under table-per-hierarchy, `tagValue` values
  are unique across the **whole family**, not just siblings
  (`inheritance-duplicate-tag-value`).
- **Shared-table consistency** — under table-per-hierarchy, all concrete subtypes
  map to one physical table (`inheritance-inconsistent-hierarchy-table`).
- **Tag placement** — a table-per-concrete-subtype family declares no `tag` /
  `tagValue` anywhere (`inheritance-tag-on-concrete-subtype-strategy`).

## Prior art (Reladomo)

Reladomo's `table-for-all-subclasses` and `table-per-subclass` correspond to the
two admitted strategies; its own "not recommended" `table-per-class` mirrors this
module's rejection. Parallax's declarative `tag` / `tagValue` metadata
deliberately diverges from Reladomo's code-level `createObject` discriminator
dispatch — the portable contract lives in descriptors and golden SQL, not
generated code.
