---
date: 2026-07-10
reladomo_commit: 9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4
reladomo_branch: master
topic: Reladomo cascade operation surface and Parallax compatibility recommendations
type: research
status: complete
---

# Reladomo cascade operations beyond cascade delete

> Part of [Research: Reladomo Core Features](00-index.md) — Reladomo @ commit
> `9b87d9e7cab32d4e9662b1d049a7d516e86f6bd4`. Repo root: the Reladomo checkout peer to this
> repository (`../reladomo`). This applied-research note also recommends how Parallax should model
> and test the discovered surface.

## Executive result

Parallax is missing two public cascade families, not just one method:

1. **Cascade insert**: `cascadeInsert`, `cascadeInsertAll`, and the business-time-bounded
   `cascadeInsertUntil` / `cascadeInsertAllUntil` variants.
2. **Cascade terminate** for dated objects: `cascadeTerminate`, `cascadeTerminateAll`, and
   `cascadeTerminateUntil` / `cascadeTerminateAllUntil`.

Reladomo has **no public cascade update, cascade purge, cascade bulk-insert, or cascade-in-batches
family**. Names such as `zCascadeCopyThenInsert` and `zCascadeUpdateInPlaceBeforeTerminate` are
runtime internals used by detached-object persistence, not peer application operations.

The recommendation is to replace `m-cascade-delete` with one snapshot-compatible **`m-cascade`**
module containing operation-specific sections for insert, delete, and temporal terminate. The three
operations share the same descriptor-owned dependent graph, recursive planner, and unit-of-work
atomicity. Operation-backed-list entry points are a separable integration seam; if Parallax wants to
claim them normatively, place them in a thin **`m-cascade-list`** extension rather than making the
base cascade behavior depend on `m-op-list`. Keep detached merge-back in `m-detach`, with cross-tagged
integration cases, rather than expanding “cascade” to every graph-persistence behavior.

## Authoritative public surface

The descriptor attribute is the root of the behavior. Reladomo's schema says
`relatedIsDependent` means that the related object's lifecycle depends on the owner, explicitly
names `cascadeInsert` and `cascadeDelete`, and says detached objects lazily detach their dependents
(`../reladomo/reladomogen/src/main/xsd/mithraobject.xsd:571-575`). The generated code then traverses
only relationships having a setter, marked dependent, whose target is transactional
(`../reladomo/reladomogen/src/main/templates/transactional/Abstract.jsp:1149-1175`,
`:1275-1297`). The test `Order` model illustrates dependent to-many and to-one relationships beside
ordinary non-dependent relationships (`../reladomo/reladomo/src/test/reladomo-xml/Order.xml:46-77`).

| Family | Single-object API | List API | Availability and meaning |
|---|---|---|---|
| Insert | `cascadeInsert()` | `cascadeInsertAll()` | Non-dated and dated transactional objects. Inserts the root and recursively inserts dependent relationship values that have been set. The object contract says “dependent relationships that have been set on it” (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/MithraTransactionalObject.java:70-79`). |
| Delete | `cascadeDelete()` | `cascadeDeleteAll()` | Non-dated roots. Recursively removes dependents before deleting the root (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/MithraTransactionalObject.java:86-96`). Dated roots reject `delete` and `cascadeDelete` (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java:585-593`). |
| Bounded insert | `cascadeInsertUntil(exclusiveUntil)` | `cascadeInsertAllUntil(exclusiveUntil)` | Business-dated objects only. The interval ends immediately before `exclusiveUntil` (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/MithraDatedTransactionalObject.java:39-57`). Generated traversal includes only dependent targets that themselves have a business-date attribute (`../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:380-399`). |
| Terminate | `cascadeTerminate()` | `cascadeTerminateAll()` | Dated roots. Recursively deletes non-dated dependent targets and terminates dated dependent targets, then terminates the root (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/MithraDatedTransactionalObject.java:64-88`, `:108-120`; dispatch generation at `../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:1915-1934`). |
| Bounded terminate | `cascadeTerminateUntil(exclusiveUntil)` | `cascadeTerminateAllUntil(exclusiveUntil)` | Business-dated objects only. Ends the root and business-dated dependents over the interval from the object's business coordinate up to but excluding `exclusiveUntil` (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/MithraDatedTransactionalObject.java:72-82`, `:113-120`; generated traversal at `../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:1936-1956`). |

The list entry points are visible on `DelegatingList`
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/DelegatingList.java:444-490`,
`:526-533`). The narrower public interfaces expose `cascadeInsertAll` for transactional and temporal
lists and `cascadeDeleteAll` for non-dated transactional lists
(`../reladomo/reladomo/src/main/java/com/gs/fw/finder/TransactionalDomainList.java:20-31`,
`../reladomo/reladomo/src/main/java/com/gs/fw/finder/TemporalTransactionalDomainList.java:20-30`).

### Recursion, direction, and mixed temporal graphs

Normal `cascadeInsert` captures the currently assigned dependent relationship values, inserts the
root, then calls `cascadeInsertAll` or `cascadeInsert` recursively on those values
(`../reladomo/reladomogen/src/main/templates/transactional/Abstract.jsp:1140-1176`; dated equivalent
at `../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:247-283`). This is why
an unset dependent is skipped, while a populated to-one or to-many is persisted. Reladomo's tutorial
describes the intended graph-wide effect: all new objects directly or indirectly related to the root
are inserted by the one call (`../reladomo/reladomo/src/doc/docbook/userguide/ReladomoTutorial.xml:598-605`).

Delete traverses in the opposite direction: generated code calls the dependent target's
`cascadeDelete` **or** `cascadeTerminate` first, chosen from the target's temporal type, and deletes
the owner last (`../reladomo/reladomogen/src/main/templates/transactional/Abstract.jsp:1275-1297`,
`../reladomo/reladomogen/src/main/java/com/gs/fw/common/mithra/generator/MithraObjectTypeWrapper.java:2609-2621`).
The same type-based dispatch is used by dated `cascadeTerminate`, so a dated owner can delete a
non-dated dependent while terminating a dated dependent
(`../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:1915-1934`). “Cascade
removal” is therefore more accurate than assuming every node receives the same SQL verb.

The bounded methods are narrower. `cascadeInsertUntil` and `cascadeTerminateUntil` recurse only into
business-dated dependent targets and pass the same exclusive bound to every visited node
(`../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:380-399`,
`:1936-1956`). They do not apply an `Until` operation to processing-only or non-dated dependents.

One implementation detail should **not** be standardized without an actual SQL trace: ordinary
`cascadeInsert` invokes the root before its dependents, whereas the generated
`cascadeInsertUntil` method invokes business-dated dependents before the root. Reladomo buffers
writes in a transaction, so Java call order need not equal executed SQL order. Compatibility should
pin dependency-safe observable DML and final temporal state, not this template accident.

### Transaction and list behavior

Single-object `cascadeInsert` and `cascadeDelete` start a transaction when none exists, join an
existing transaction, and run through Reladomo's bounded retry loop
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraTransactionalObjectImpl.java:365-424`;
dated insert equivalent at
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/superclassimpl/MithraDatedTransactionalObjectImpl.java:449-477`).
The generated temporal `...Until` and terminate methods are direct object operations; Reladomo's
tests call them inside an explicit transaction
(`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java:3421-3467`,
`:4869-4885`). Parallax should specify one clear unit-of-work rule across the family rather than
copy this API inconsistency.

`cascadeInsertAll` and both terminate-all variants execute one transactional command and loop over
the objects one by one
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/CascadeInsertAllTransactionalCommand.java:27-44`,
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/CascadeTerminateAllTransactionalCommand.java:26-44`,
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/CascadeTerminateAllUntilTransactionalCommand.java:28-48`).
An operation-backed list rejects cascade insert because query results are not an insertable adhoc
collection (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/AbstractTransactionalOperationBasedList.java:184-192`).

Delete-all has two paths:

- An adhoc list prepares every root for deletion, then calls `cascadeDelete` one by one
  (`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/CascadeDeleteAllOneByOneCommand.java:27-48`).
- An operation-backed list recursively issues `cascadeDeleteAll` for generated dependent lists,
  then uses `deleteAll` for the roots
  (`../reladomo/reladomogen/src/main/templates/transactional/ListAbstract.jsp:213-223`,
  `../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/AbstractTransactionalOperationBasedList.java:328-345`,
  `:415-429`).

There is a Reladomo implementation asymmetry worth making explicit rather than copying silently:
the generated operation-list traversal includes only **non-dated** dependent targets
(`../reladomo/reladomogen/src/main/templates/transactional/ListAbstract.jsp:217-220`), while
single-object/adhoc cascade delete dispatches a dated target to `cascadeTerminate`. Parallax should
standardize representation-independent logical behavior (the same dependent closure for adhoc and
operation-backed lists) and cover it with a case; the Reladomo restriction looks like a set-based
implementation boundary, not a different lifecycle concept.

There is no cascade counterpart to `bulkInsertAll`, `deleteAllInBatches`, or `purgeAllInBatches`.
The non-cascade batch operations are adjacent in `DelegatingList`, while the complete cascade list
surface contains only the methods enumerated above
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/DelegatingList.java:444-533`).

### Relationship mutation and detach are integration behavior, not new cascade families

Persisted relationship mutation also reuses the explicit cascade operations; it is an integration
trigger, not another public family. Generated dependent to-many relationship lists install an add
handler and a type-specific remove handler
(`../reladomo/reladomogen/src/main/templates/transactional/Abstract.jsp:862-872`; dated equivalent
at `../reladomo/reladomogen/src/main/templates/datedtransactional/Abstract.jsp:1370-1380`). Adding to
a persisted dependent list copies the owner key into the child and calls `cascadeInsert`
(`../reladomo/reladomogen/src/main/templates/AddHandler.jspi:16-42`); removing a child calls
`cascadeDelete` for a non-dated target or `cascadeTerminate` for a dated target
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/DeleteOnRemoveHandler.java:24-37`,
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/TerminateOnRemoveHandler.java:23-36`).
Reladomo covers both non-dated and audit-only persisted add/remove behavior
(`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestRelationshipPersistence.java:449-530`,
`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestAuditOnlyRelationshipPersistence.java:326-426`).
These deserve cross-module compatibility cases, but not `m-cascade-add` / `m-cascade-remove` modules.

Dependent relationships participate in detach/merge-back, but Reladomo does not expose a separate
`cascadeUpdate` application operation. Removing items from a detached relationship marks the items
deleted or terminated; merge-back later performs the real cascade against the original graph
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/list/AdhocDetachedList.java:147-171`,
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DetachedDeletedBehavior.java:177-185`,
`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DatedDetachedDeletedBehavior.java:147-176`).
The Reladomo suite verifies detached `cascadeTerminate` followed by merge-back removes the audited
dependents (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestAuditOnlyRelationshipPersistence.java:449-467`).

Direct bounded termination of a detached dated object is explicitly not implemented
(`../reladomo/reladomo/src/main/java/com/gs/fw/common/mithra/behavior/detached/DatedDetachedSameTxBehavior.java:159-167`).
Do not infer detached support for every temporal cascade variant.

## Module recommendation

### Prefer `m-cascade`

Rename and broaden the current module instead of adding `m-cascade-insert` and
`m-cascade-terminate`.

Reasons:

- The stable capability is **dependent-lifecycle graph orchestration**. Insert, delete, and
  terminate are traversal policies over the same graph, not unrelated subsystems.
- Mixed graphs already cross the apparent verb boundary: deleting a non-dated owner can terminate
  a dated child, and terminating a dated owner can delete a non-dated child.
- Object and list forms are cardinality variants of one operation; `...All` should not become a
  separate module.
- One module yields a coherent compatibility matrix for dependency inclusion, recursion, ordering,
  atomicity, list selection, and temporal bounds. Three thin modules would repeat those rules and
  make mixed-graph ownership awkward.
- The existing spec already says its one witness is intentionally narrow and calls the broad
  Reladomo surface a fast-follow (`core/spec/m-cascade-delete.md:3-27`). Broadening the name matches
  that stated trajectory.

Suggested sections within `m-cascade`:

1. dependent graph and eligibility;
2. cascade insert (one root or an explicit root collection);
3. cascade removal dispatch (delete vs terminate);
4. bounded business-time variants;
5. unit-of-work atomicity and failure semantics;
6. explicit-root/set behavior and non-goals (no cascade bulk or batch API);
7. integration points, with detached behavior remaining owned by `m-detach`.

The existing direct edge to `m-unit-work` remains appropriate. The current `m-op-list` edge should be
removed from the base module: a snapshot implementation can cascade from an explicit value graph,
root key, or predicate by planning descendant writes from `m-descriptor` metadata; it need not create
or resolve an operation-backed managed list. Reladomo's generated object methods happen to use typed
lists while traversing to-many relationships, but that Java implementation shape is non-normative for
Parallax. If bounded and processing-time termination are normative in the broadened module, add a
dependency from `m-cascade` to `m-bitemp-write`; that reaches `m-audit-write` transitively in the
current graph (`core/spec/modules.md:95-110`). If detached cascade integration is made normative, the
natural direction is `m-detach --> m-cascade`, because merge-back invokes cascade removal; avoid
making the base cascade module depend on detach.

Thin modules are reasonable only if Parallax wants languages to claim insert, delete, and terminate
conformance independently. The cost would be a shared graph contract (or duplicated normative text)
plus explicit mixed-graph rules spanning two modules. Nothing in the Reladomo surface suggests that
this extra conformance granularity is worth the complexity.

This conclusion does **not** treat thin Parallax modules as a design smell. Thin modules are valuable
when they let a language build enforce a smaller dependency closure or let a slice name a genuinely
separable capability. The verb split does not buy that here once the complete semantics are included:

- `m-cascade-delete` would still need the temporal-write stack because deleting a non-dated owner
  terminates dated dependents rather than physically deleting them.
- `m-cascade-terminate` would still need ordinary non-temporal deletion because terminating a dated
  owner physically deletes non-dated dependents.
- `m-cascade-insert` would still need temporal writes because ordinary cascade insert applies to dated
  roots, and its bounded variant is bitemporal/business-time behavior.

A verb split creates smaller dependency closures only by forbidding mixed graphs or by leaving each
module intentionally partial. That is the wrong seam: the stable interface is “apply this lifecycle
transition to the owned dependent closure,” with node type selecting the concrete mutation. Slices can
still stage individual `m-cascade` cases because Parallax slices are case-granular
(`core/spec/slices.md:3-7`), while the build graph honestly records the full module prerequisites.

For the currently active catalog, the recommended base edges are:

```dependency-graph
m-cascade --> m-unit-work
m-cascade --> m-bitemp-write
```

`...All` does not itself imply `m-op-list`: cascading an explicit array of snapshot graphs or a
predicate-selected set is still base cascade behavior. Only entry points that specifically consume an
`m-op-list` operation-backed result need the list module. If those managed-list entry points are a
normative capability rather than per-language composition glue, model that dependency precisely:

```dependency-graph
m-cascade-list --> m-cascade
m-cascade-list --> m-op-list
```

This lets both snapshot and managed-object slices claim `m-cascade`; only a slice promising cascade
methods on operation-backed lists needs `m-cascade-list`.

`m-bitemp-write` reaches `m-audit-write` transitively. Do not add an edge to the currently deferred
`m-business-only` while `m-cascade` is active: either keep business-only cascade cases deferred, or
activate `m-business-only` first and add the edge in the same coherent change. Do not add
`m-batch-write` merely because the surface has `...All` methods—Reladomo has no cascade bulk/batch
family, and batching remains a separate compositional optimization. `m-pk-gen` and `m-detach` should
be cross-tagged in their integration cases; if deep detached merge-back later becomes a required
module behavior, the natural edge remains `m-detach --> m-cascade`.

## Recommended compatibility cases

The cases below are behavioral witnesses, not a demand to copy Reladomo's Java API. Use one primary
`m-cascade` tag after the rename and cross-tag the modules whose underlying behavior is exercised.
For write-sequence fixtures, constrain only dependency-significant ordering; do not pin arbitrary
sibling relationship declaration order.

### Current baseline to retain and retag

The four existing `m-cascade-delete` cases should move with the module rename, not be recreated:

| Existing case | What it already proves | Remaining gap |
|---|---|---|
| `m-cascade-delete-001-dependent-order` | Direct dependent to-many rows delete before the root | It does not prove recursive depth: `Order.statuses` reaches the status table directly, so the SQL can remove apparent item “grandchildren” without traversing `Order.items -> OrderItem.statuses`. |
| `m-cascade-delete-002-non-dependent-untouched` | A populated non-dependent relationship is excluded | Retain as the delete-side exclusion witness; add the insert-side equivalent below. |
| `m-cascade-delete-003-one-to-one-cascade` | A dependent to-one deletes before its root | Insert and temporal operations still need to-one witnesses. |
| `m-cascade-delete-004-multi-root` | Two enumerated root cascades remain correctly ordered | It is two one-root operations (six statements), not the predicate-driven/set-oriented `cascadeDeleteAll` witness below. |

Everything in the following tables is an addition unless it explicitly says it reuses one of these
baseline assertions.

### P0: normative cascade core

| ID | Case | Required assertions | Likely cross-tags |
|---|---|---|---|
| `cascade-insert-to-one-many` | New root with one dependent to-one and two dependent to-many children | Root and all three dependents exist; child FKs equal the root PK; root insert precedes FK-constrained child inserts | `m-unit-work`, `m-descriptor` |
| `cascade-insert-deep` | Root -> child -> grandchild, all dependent | Every level is inserted recursively and in dependency-safe order | `m-unit-work` |
| `cascade-insert-excludes-nondependent` | Root has one dependent and one populated non-dependent relationship | Only the root and dependent are inserted | `m-descriptor` |
| `cascade-insert-unset-dependent` | Dependent to-one is unset and dependent to-many is empty/unset | Root inserts successfully with no synthetic child writes | `m-descriptor` |
| `cascade-insert-generated-root-key` | Root PK is generated and child FK derives from it | PK is assigned before child persistence and the exact generated value appears in every child FK | `m-pk-gen` |
| `cascade-insert-rollback` | Deep child insert fails a constraint after earlier graph writes are staged | No root, child, or grandchild persists | `m-unit-work`, `m-db-error` |
| `cascade-insert-all` | Explicit collection of two new root snapshot graphs, each with dependents | Both graphs persist in one unit of work; a failure in graph two rolls back graph one | `m-unit-work` |
| `cascade-delete-deep-unloaded` | Persisted root key with unloaded to-one/to-many children and grandchildren | All dependents are discovered from descriptor metadata; grandchildren delete before children and children before root | `m-unit-work`, `m-descriptor` |
| `cascade-delete-excludes-nondependent` | Existing `m-cascade-delete-002`, retained under the new module name | Dependent rows delete; non-dependent rows survive unchanged | `m-descriptor` |
| `cascade-delete-all-filtered` | Predicate selects some roots from several populated graphs | Only selected roots and their dependent closures delete; non-selected graphs remain | `m-op-algebra`, `m-unit-work` |
| `cascade-delete-all-self-dependent` | A finite self-referential dependent tree | Descendants delete before ancestors with no duplicate deletion or infinite recursion; modeled after Reladomo's self-relationship test (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestTransactionalList.java:666-670`) | `m-unit-work`, `m-descriptor` |
| `cascade-delete-rollback` | A dependent delete fails or the transaction is explicitly rolled back | Every node remains visible; no partial graph removal | `m-unit-work` |
| `cascade-terminate-audit-only` | Processing-dated root with dependent to-one and to-many rows | Current root and dependents disappear; historical rows remain and share the transaction processing cutoff | `m-audit-write`, `m-temporal-read` |
| `cascade-terminate-bitemporal` | Bitemporal root retrieved at business coordinate `t`, with dependents | Root and dependents are absent from `t` forward according to normal terminate semantics; prior business history remains | `m-bitemp-write`, `m-temporal-read` |
| `cascade-insert-until` | New bitemporal root and dependents over `[from, until)` | Root and every business-dated dependent exist at `from` and immediately before `until`, and are absent at `until`; Reladomo's equivalent verifies root, to-many, and to-one (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java:3413-3474`) | `m-bitemp-write`, `m-temporal-read` |
| `cascade-terminate-until` | Existing bitemporal graph terminated over `[at, until)` | Root and dependents are absent within the interval, while versions before `at` and at/after `until` remain; Reladomo verifies all three entity types (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java:4858-4894`) | `m-bitemp-write`, `m-temporal-read` |
| `cascade-temporal-exclusive-boundary` | `until` equals a queried boundary coordinate | The upper bound is exclusive for root and all visited dependents; no off-by-one/timestamp rounding difference | `m-core`, `m-bitemp-write` |
| `cascade-mixed-delete-terminate` | Non-dated root owns both non-dated and dated dependents | Non-dated dependents are physically deleted; dated dependents are terminated with history retained; root deletes last | `m-audit-write`, `m-temporal-read` |
| `cascade-mixed-terminate-delete` | Dated root owns a non-dated dependent | Non-dated dependent deletes and dated root terminates atomically | `m-audit-write`, `m-unit-work` |

### P1: list, graph-shape, and error boundaries

| ID | Case | Required assertions | Likely cross-tags |
|---|---|---|---|
| `cascade-terminate-all-filtered` | Predicate selects several dated roots | Every selected dependent closure terminates; other graphs and their histories are unchanged | `m-op-algebra`, `m-audit-write` |
| `cascade-insert-all-until` | Explicit collection of business-dated snapshot graphs | Same exclusive interval is applied to every root and dependent in one unit of work | `m-bitemp-write` |
| `cascade-terminate-all-until` | Explicit or predicate-selected collection of business-dated graphs | Same removal interval is applied atomically to every selected graph | `m-op-algebra`, `m-bitemp-write` |
| `cascade-until-skips-nonbusiness-dependent` | Business-dated root owns a processing-only or non-dated dependent | Pin the chosen rule. Reladomo leaves that target outside both bounded traversals because generated `Until` recursion visits only business-dated targets; recommended Parallax behavior is to preserve that explicit exclusion rather than invent an unbounded side effect | `m-bitemp-write`, `m-audit-write` |
| `cascade-delete-all-mixed-temporal-parity` | The same mixed temporal graph is removed once through the snapshot/base surface and once through an operation-backed root list | Both representations produce the same logical closure: delete non-dated nodes and terminate dated nodes. This deliberately smooths Reladomo's operation-list implementation restriction | `m-cascade-list`, `m-op-list`, `m-audit-write` |
| `cascade-shared-dependent-once` | A dependent with multiple lifecycle parents is reachable twice | It is inserted/removed once, or the descriptor is rejected with a defined diagnostic; never duplicate DML | `m-descriptor`, `m-unit-work` |
| `cascade-dated-delete-rejected` | Invoke cascade delete on a dated root | Stable error category; no writes occur | `m-audit-write` |
| `cascade-until-requires-business-axis` | Invoke either `...Until` on processing-only or non-temporal data | Stable unsupported-operation/descriptor diagnostic; no writes occur | `m-audit-write`, `m-db-error` |
| `cascade-insert-operation-list-rejected` | Attempt insert-all from an operation-backed query result | Stable error and no writes, if Parallax adopts Reladomo's adhoc-only insertion rule | `m-cascade-list`, `m-op-list` |
| `cascade-no-bulk-or-batch-claim` | Conformance metadata/API capability declaration | Cascade conformance does not imply bulk insert or batched-delete behavior; those require their own ordinary write contracts | `m-batch-write` |

### P2: cross-module lifecycle integration

| ID | Case | Required assertions | Likely cross-tags |
|---|---|---|---|
| `cascade-managed-dependent-add` | Add a new dependent subtree to a persisted owner's managed to-many relationship | The owner FK is propagated; the added root and its dependents insert atomically; the existing owner is not reinserted | `m-detach`, `m-identity-map`, `m-unit-work` |
| `cascade-managed-dependent-remove` | Remove one child subtree from a persisted dependent to-many relationship | The removed subtree is deleted or terminated by target temporal type; retained siblings and owner remain | `m-detach` plus the relevant temporal write module |
| `cascade-detached-delete-merge` | Detach graph, cascade-delete the detached root, merge back | Database remains unchanged before merge; merge removes the original dependent closure atomically | `m-detach`, `m-identity-map` |
| `cascade-detached-terminate-merge` | Detach audited graph, cascade-terminate, merge back | Database remains unchanged before merge; merge terminates the original graph and retains history | `m-detach`, `m-audit-write` |
| `cascade-detached-relationship-removal` | Remove one dependent from a detached to-many and merge | Removed dependent is deleted/terminated recursively; retained siblings and owner remain | `m-detach` plus relevant temporal write module |
| `cascade-cache-identity-after-commit` | Read managed nodes, cascade remove, commit, query again | Removed/terminated current identities are not returned and historical temporal identities remain correct | `m-identity-map`, `m-temporal-read` |

## Reladomo test corroboration

- `cascadeInsert` persists a root with both to-many items and a to-one status and propagates the
  root ID to the children
  (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestRelationshipPersistence.java:75-123`,
  `:125-175`).
- `cascadeDeleteAll` is tested over an operation-backed order list, and a separate test covers a
  self relationship
  (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestTransactionalList.java:645-670`).
- Audit-only `cascadeTerminate` removes current dependents, including through a detached root after
  merge-back
  (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestAuditOnlyRelationshipPersistence.java:428-467`).
- Bitemporal `cascadeInsertUntil` and `cascadeTerminateUntil` verify root, to-many, and to-one graph
  behavior at the temporal boundaries
  (`../reladomo/reladomo/src/test/java/com/gs/fw/common/mithra/test/TestDatedBitemporal.java:3413-3474`,
  `:4858-4894`).
