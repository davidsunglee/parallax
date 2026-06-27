# M9 — Object Lifecycle & Detach

`M9` is the **object lifecycle state machine** and the **detached-copy / merge-
back** protocol: the rules that govern when an object's mutations are buffered
into a unit of work, when they are flushed as SQL, and how an object can be
edited entirely **outside** any transaction (a *detached* copy) and later merged
back into the persisted store.

`M9` is a fast-follow module. It depends on `M8` — the unit of work, the identity
cache, and the buffered-write machinery it is layered on — and on nothing below
that. Like `M8`, it is expressed in terms of **operations and object state**, not
SQL; the concrete DML a merge-back flushes is produced by `M3` and run through
the `M11` execution seam, so `M9` takes no direct edge to SQL generation.

This mirrors Reladomo's per-state behavior dispatch (a persisted object behaves
differently from a detached or deleted one) and its `getDetachedCopy` /
`copyDetachedValuesToOriginalOrInsertIfNew` pair — but `M9` mandates only the
**observable** lifecycle rules, not any particular behavior-object decomposition.

## The lifecycle state machine

Every transactional object is in exactly one **persistence state**. The states
and the legal transitions between them:

| State | Meaning |
|---|---|
| `in-memory` | newly constructed, not yet inserted; mutations stay in memory |
| `persisted` | backed by a database row; interned in the identity cache; mutations buffer into the unit of work |
| `deleted` | marked for deletion within a unit of work; the `DELETE` flushes at the boundary |
| `detached` | a deep copy decoupled from the cache; mutations stay in the copy (no SQL) |
| `detached-deleted` | a detached copy marked for deletion; merge-back deletes the original |

```text
            new object
                │
                ▼
           in-memory ──── insert ────▶ persisted ──── delete ────▶ deleted
                                          │  ▲
                              getDetached │  │ merge-back
                                  Copy    ▼  │ (copy values to original
                                      detached   or insert if new)
                                          │
                                  delete  ▼
                                   detached-deleted ── merge-back ──▶ deleted
```

The transitions an implementation **MUST** support:

- **`in-memory → persisted`.** Inserting a new object (directly, or by committing
  the unit of work it was created in) flushes an `INSERT` and interns it in the
  identity cache.
- **`persisted → deleted`.** Deleting a persisted object marks it; the `DELETE`
  flushes at the unit-of-work boundary (`M8` ordering rules apply).
- **`persisted → detached`.** Taking a **detached copy** (below) yields a new
  object in the `detached` state, fully decoupled from the cache.
- **`detached → detached-deleted`.** Deleting a detached copy marks the copy; no
  SQL is issued until merge-back.
- **`detached / detached-deleted → persisted / deleted`.** **Merging back**
  (below) reconciles the copy with the live store.

A state transition is the **only** way an object's persistence behavior changes;
the *mechanism* (per-state singleton behavior objects, a status enum, dynamic
dispatch) is non-normative. Only the observable transitions and their effects are
mandated.

## Where mutations go (the in-memory vs. buffered rule)

The state decides **where a mutation lands**, and this is the load-bearing
observable contract:

- An **`in-memory`** object's mutations are held in the object until it is
  inserted; nothing reaches the database until then.
- A **`persisted`** object's mutations **buffer** into the enclosing unit of work
  (`M8`) and flush as SQL at the boundary — never eagerly, one statement per set.
- A **`detached`** object's mutations land **only in the copy**. A detached object
  is **not** enrolled in any unit of work and issues **no** SQL when mutated; the
  database is untouched until merge-back. This is the property that makes a
  detached object usable across transaction boundaries (e.g. carried through a UI
  edit) without holding a transaction open.

## Detached copy — a deep copy decoupled from the cache

A **detached copy** of a persisted object is a **deep copy** of its data into a
brand-new object in the `detached` state, with **no** link to the identity cache:

- The **original stays live** in the cache and the unit of work; the copy is
  independent.
- Mutating the copy does **not** mutate the original and issues **no** SQL.
- A detached copy is editable with **no transaction open** — it is a plain
  in-memory object carrying a snapshot of the persisted values plus its primary
  key.

Because the copy is decoupled, two detached copies of the same row are
independent objects (the one-object-per-PK identity rule, `M8`, governs the
**cache** — detached copies live *outside* it by construction).

### `isModifiedSinceDetachment`

A detached copy can report whether it differs from the values it was detached
with. `isModifiedSinceDetachment` compares the copy's current attribute values to
the **snapshot taken at detachment**, attribute by attribute, and is `true` iff
any differs. An implementation **MUST** provide this predicate; it is what lets a
merge-back skip a no-op write (a copy edited and then reverted, or never edited,
need not flush an `UPDATE`).

## Merge-back — reconcile the copy with the live store

**Merging back** a detached copy reconciles it with the persisted store **inside a
unit of work**. The rule, keyed by the copy's state and whether the original row
still exists:

| Detached state | Original found (by PK) | Effect |
|---|---|---|
| `detached` | yes | copy the changed attributes onto the live object ⇒ a buffered `UPDATE` (the normal `M8` flush) |
| `detached` | no | **insert** the copy as a new row ⇒ an `INSERT` |
| `detached-deleted` | yes | delete the original ⇒ a `DELETE` |

So merge-back is *copy-values-to-original-or-insert-if-new* (plus the delete
case): it looks up the original by primary key in the cache / store, and either
updates it in place (driving the ordinary buffered-write machinery of `M8`),
inserts a new row when the original is gone, or deletes it. A merge-back of an
**unmodified** copy (`isModifiedSinceDetachment` is `false`) flushes **no**
`UPDATE`.

Only the **changed** attributes need participate in the `UPDATE`'s `set` (a
`readOnly` attribute, `M1`, is never written), but an implementation **MAY** write
the full attribute set; the observable contract is the **resulting persisted
rows**, which the suite asserts.

## What the suite pins down

`M9` is expressed in object state, so its **observable** effect is the rows a
merge-back leaves behind. The compatibility suite proves it with **write-sequence**
cases (`M12`) — applying the golden DML a merge-back flushes and asserting the
resulting table state:

| Case | What it proves |
|---|---|
| detached insert | merging back a never-persisted detached object **inserts** it (the resulting row matches) |
| detached update | merging back a mutated detached copy of a persisted object **updates** the original in place (only the original row changes; the change is the edited attribute) |

The detached-insert case starts from an **empty** table (the object was never
persisted) and asserts the inserted row. The detached-update case **loads the
model's fixtures first** (the original persisted row exists), then applies the
merge-back `UPDATE` and asserts the table state — the edited row changed, the
others untouched. Both reuse the `M12` write-sequence machinery: *apply the
documented golden DML, assert the rows it leaves behind*, so the merge-back
contract is verified against real data rather than merely asserted in prose.

Optimistic-lock conflict on merge-back — when a concurrent transaction changed
the original between detachment and merge-back — is the subject of `M10`.
