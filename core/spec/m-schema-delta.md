# m-schema-delta — Schema Delta Generation

`m-schema-delta` turns a **Unilateral Evolution** into the ordered dialect
statements that carry a database from the earlier accepted Metamodel to the later
one. It generates; it never applies. The application executes the statements
against its own database and publishes the later Model Edition only after every
one of them succeeds, so this module opens no connection, runs no preflight
query, and prescribes no rollout procedure.

It consumes a Unilateral Evolution and nothing else. A Coordinated Evolution is
an equally complete description whose application needs authoring, data, or
rollout coordination, so it is not an input to schema generation at all — an
implementation states that in the accepted argument type rather than as a runtime
refusal.

It depends on `m-model-evolution` for the description it lowers, on `m-metamodel`
for the declarations an operation names, on `m-storage-layout` for every physical
fact, and on `m-dialect` for every spelling. It composes no key, no Column order,
and no nullability of its own, and it branches on no Dialect Identity: the
`Dialect` value passed in determines the whole output.

The decision record is
[ADR 0063](../../docs/adr/0063-model-evolution-is-described-at-model-altitude-and-applied-by-the-application.md).

## The generation algebra

```text
schemaDelta(evolution: UnilateralEvolution, dialect: Dialect) -> SchemaDelta

SchemaDelta
  statements                   ordered dialect statements, as plain strings
  createdIndices               provenance, one per newly created Index

CreatedIndex
  physicalIndexName            the name a later violation reports
  physicalTable                the Table the Index sits on
  logicalIndexIdentity         the authored Index Identity it was derived from
  unique                       whether it enforces uniqueness
```

A Schema Delta is an immutable value. Statements have **no** wrapper and no
per-statement causal metadata: the physical-operation algebra below is private,
and an application applying a delta already holds the Evolution and observes the
statement that failed. Created-Index provenance is the sole exception, because
only a physical name lets a host correlate a later uniqueness violation with the
rollout that created the Index.

Generation is total over its accepted input and deterministic: equal inputs give
equal values, and equal models give an empty Schema Delta rather than an absent
one.

## Statements are prefix-safe and deliberately not idempotent

The returned order is executable: every prefix of it can be applied to a database
at the earlier edition. No statement uses `IF EXISTS` or `IF NOT EXISTS`, because
a delta states what must happen to a database at a **known** edition rather than
reconciling an unknown one, and a silently skipped statement would leave the
later edition published over a schema that never received it.

Creating a unique Index is the authoritative validation of the data already
stored. The generator performs no preflight data query: if existing rows violate
the rule, the creating statement fails, the earlier definition is left intact, and
the later edition is not published.

## The private physical-operation algebra

Between the model-altitude description and the dialect statements sits one
private algebra. It is the closed choice below and it never crosses the module's
boundary in either direction.

```text
CreateTable          the complete target Table Layout: every target Column and the
                     derived primary key inline, EXCLUDING authored secondary Indices
AddColumn            one target Column Slot
ExpandColumnDomain   the earlier and later physical Column facts; may only relax
                     nullability, widen a bounded String, remove its bound, or
                     combine those expansions
CreateIndex          one target physical Index definition
DropIndex            one earlier physical Index definition
```

Drop-table, drop-column, rename, primary-key-alteration, and arbitrary-SQL
variants are deliberately absent, because no Unilateral Evolution can produce
one. `ExpandColumnDomain` is not a generic column alteration: nothing that
narrows a stored domain is unilateral.

Each physical operation carries its **causal Evolution Operations** — all and
only the operations whose changed facts asked for it, in canonical operation
order. An entity-level addition brings a whole Table with it and suppresses
operations for the members it contains, so the Columns and authored Indices of an
added Entity are read off the later model rather than arriving as operations of
their own; every addition that contributes a Column to a Table, or owns rows in
it, is a cause of that Table's creation, and an Index created as part of creating
its Table carries the same causes as the Table.

A schema-neutral unilateral operation lowers to no physical operation at all.

## Statement order

Order is stated as dependency rules plus tie-breakers:

- a Table is created before anything acts on its Columns or Indices;
- a Column is added before any new Index that references it;
- an altered Index's target definition is created before its earlier definition
  is dropped;
- independent operations use stable physical-location and operation-kind
  tie-breakers, never a global phase order.

Every edge those rules can produce stays inside **one Table**: the algebra emits
no foreign key, and an Index is always local. The current algebra therefore
admits a total key —

```text
orderKey(operation) = (physical Table, physicalOperationKindRank, member addressed)
physicalOperationKindRank:
    CreateTable < AddColumn < ExpandColumnDomain < CreateIndex < DropIndex
```

— which is a linear extension of the dependency relation, so sorting by it emits
what a deterministic topological walk over the same key would. Leading with the
Table keeps one Table's statements together and keeps the whole output stable
under an edit to an unrelated Table. An implementation MAY sort; the rules above
are the contract, and the first physical operation kind with a cross-Table
dependency reintroduces an explicit graph.

Inspection order and statement order are independent. An Evolution's operations
are in canonical Model Location order because that is how a change is READ; a
Schema Delta's statements are in executable order because that is how it is
APPLIED.

Statements emitted for one physical operation stay contiguous and preserve
renderer order.

## Physical Index Names

Fresh provisioning creates each Table with all of its target Columns and its
derived primary key, then creates **every** authored secondary Index — unique and
non-unique alike — as a separate, explicitly named statement. An incremental
delta uses the same Index form. The derived primary-key Index is never a separate
statement: it is the Table's key.

Each Physical Index Name is:

```text
pxi_<readable-prefix>_<fingerprint>
```

The **readable input** concatenates the physical Table, the complete declaring
Entity Identity, the authored Index name, and a unique/non-unique marker. ASCII
letters are lowercased, digits are retained, each maximal remaining run becomes
one underscore, surrounding underscores are trimmed, and an empty result becomes
`index`.

The **fingerprint** is the first 128 bits of SHA-256 over a versioned sequence of
length-prefixed UTF-8 fields — the physical Table, the structured declaring
Entity Identity, the authored Index name, the ordered structured Attribute
Identities, and uniqueness — rendered as 32 lowercase hexadecimal characters.
Length-prefixing is what makes the digest a function of the structure rather than
of a joined string, and the version field makes a later change to what is hashed
produce different names by construction.

Only the readable prefix is truncated, to whatever the Dialect's identifier byte
limit leaves; the fingerprint is **never** truncated. The transliterated prefix is
ASCII, so a character budget and a byte budget are the same budget. The trim and
empty-result rules are re-applied to the truncated prefix, so a shortened name
never ends in the separator run the cut landed on.

Every input is the definition's own, so a definition's name is stable
independently of every other Index in the model: adding an Index beside one moves
no existing name.

Because an altered Index's target definition differs from its earlier one in a
fingerprinted fact, the two take distinct names — which is what lets the target
be created and validated before the earlier Index is dropped.

## Errors

Both errors are aggregated values, raised once with the complete finding set.
Neither returns a partial Schema Delta.

**Unsupported schema evolution.** Before returning anything, the complete plan is
checked against the selected Dialect. If any operation is unsupported, generation
raises one atomic error carrying the Dialect Identity and the complete nonempty
sequence of unsupported operations in deterministic physical-operation order.
Each record carries the operation kind, its physical location, and its causal
Evolution Operations in canonical operation order. This does **not** reclassify
the dialect-independent Unilateral Evolution as coordinated: renderer support is a
deployment capability, not a model-semantic fact.

**Physical Index Name collision.** If two distinct physical Index definitions that
can coexist during any statement prefix derive one name, generation refuses
rather than silently renaming either. The error carries the Dialect Identity and
every collision group in Physical Index Name order; each group carries the shared
name and at least two colliding definitions in canonical logical-identity order,
each naming its physical Table, logical Index Identity, ordered components,
uniqueness, and whether it occurs in the earlier endpoint, the later endpoint, or
both. This is a defensive backstop for an unexpected 128-bit fingerprint
collision, not an ordinary control path and not a dialect-capability error.

## Rule Set boundary

`m-schema-delta` contributes no Model Formation Rule Set, no Issue Codes, no
Model Compiler, and no facet. Both endpoints are already accepted before an
Evolution exists, and classification already decided that this Evolution is
unilateral, so there is no model question left for this module to answer and no
input it refuses on model grounds. Its two errors are about the selected Dialect
and about generated names — never about the model.

It also owns no physical fact. Table composition, canonical Column order,
effective physical nullability, the physical primary key, and the resolution of an
Index component to a Column are all `m-storage-layout`'s, read through the later
endpoint's compiled facet and re-derived nowhere.

## Consumer contract

**A DDL-applying application.** Executes `statements` in the returned order,
stopping at the first failure, and publishes the later Model Edition only after
all of them succeed. It MUST NOT reorder, deduplicate, or make a statement
idempotent, and MUST NOT treat a Schema Delta as reversible: no inverse delta is
produced, because a Unilateral Evolution's inverse is not generally unilateral.
It retains `createdIndices` as its own rollout ledger; correlating a later
`m-db-error` uniqueness violation with an entry is what the provenance exists
for.

**`m-db-error`.** Carries the violated Physical Index Name a driver reports, as a
`m-dialect` value. It never parses a message and never asks this module anything:
a name that matches no `createdIndices` entry — a primary key, or an Index some
earlier rollout created — is an ordinary negative correlation.

**A non-relational consumer.** Consumes the same Unilateral Evolution directly
from `m-model-evolution` and produces no statements at all. That is why the
description is at model altitude and why this module is a consumer of it rather
than part of it.
