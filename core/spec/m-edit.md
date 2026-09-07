# m-edit — Edited-Value Derivation

`m-edit` specifies how one in-memory value is derived from another by an
authored edit. Per the dependency graph, it depends on `m-metamodel`, which owns
declared members, framework ownership, and model-relative member resolution.
Lifecycle modules may carry their own state through this operation, but they do
not redefine the derivation.

## The edit operation

An edit accepts zero or more authored assignments and MUST return a distinct
derived value. It MUST NOT mutate the source. An edit with no assignments is
legal: it still derives a distinct value under every preservation and
invalidation rule below.

Every authored name MUST resolve to an assignable declared member, and every
authored value MUST satisfy that member's assignment rules before the result is
produced. Assigning a Value Object occurrence replaces that occurrence whole,
at either cardinality; elements of a `many` occurrence have no identity for an
edit to address or merge. A language surface MAY expose its own validation and
error shape, but MUST NOT turn an invalid assignment into carried state.

Framework-owned members are not author-assignable. Their source values remain
part of the carried complement and MUST survive an edit unless the module that
owns such state explicitly invalidates it.

## Preservation by complement

The result MUST carry every source binding that the edit neither replaces nor
invalidates. Preservation is by **complement**, not by an enumeration of known
state kinds: adding a supported application-owned state kind does not require a
new edit rule merely to make that state survive.

Carry is shallow. A reference-valued payload in the carried complement MUST be
the same payload object in source and result. The two values MUST nevertheless
own independent bindings: rebinding the result MUST NOT rebind the source,
while mutating the shared payload is visible through both references.

Installing carried state MUST NOT invoke an application assignment hook. A
read-only binding cannot refuse carry, and an intercepting setter cannot alter
the carried value. This rule constrains the observable result, not the storage
or attribute mechanism used to produce it.

An edit preserves occurrence presence as well as member values. In particular,
an unassigned Value Object member absent from the source remains absent from the
result, while an authored null is present as null. `m-value-object` owns the
absent-versus-null distinction and the rule that a `many` occurrence has no
absent state; this module requires an edit to preserve those answers rather than
restate their representation.

## Explicitly declared derived caches

State that the value's class or equivalent native declaration explicitly marks
as a **derived cache** is the one application-owned exception to complement
preservation. Every edit MUST exclude the source's declared derived-cache state,
including a change-free edit and an edit that assigns a member the cached
calculation does not read. No dependency tracking is implied or permitted by
this contract. Normal access or validation MAY compute the result's own cache.

Invalidation applies only to the derived value. The source and any cache it has
already computed MUST remain unchanged.

Manually memoized state with no explicit derived-cache declaration is
application-owned auxiliary state, not a derived cache, and MUST be preserved by
complement like any other supported auxiliary binding.

## Language-neutral witness roles

Compatibility cases name three roles rather than host-language mechanisms:

- **`auxiliary`** is supported application-owned state outside the declared
  member assignments. Its reference identity is shared by shallow carry and its
  source/result bindings are independent.
- **`derivedCache`** is state an idiomatic declaration explicitly marks as
  derived. It is excluded on every edit and evaluated anew only through the
  result's ordinary access or validation behavior.
- **`hooks`** are application assignment interception. Carry invokes none.

Each language specification MUST identify the idiomatic mechanisms that witness
the roles it supports. A language with no native derived-cache or assignment-hook
mechanism MAY record that one role as inapplicable, but MUST NOT silently skip a
supported native witness or the portable preservation contract.

The mechanism is non-normative. A language MAY use constructors, immutable
records, descriptor-bypassing storage seams, generated copy functions, or any
other implementation whose observable source, result, identity, presence,
cache, and hook behavior satisfies this contract.
