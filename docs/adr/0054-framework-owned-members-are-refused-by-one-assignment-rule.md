# Framework-owned members are refused by one assignment rule

Accepted Attribute metadata carries a single `framework_owned` designation, and
every surface that assigns a member consults one shared assignment rule that
refuses a framework-owned target. The designation answers who supplies the
value — the framework, never the caller. It is derived rather than authored and
has no authoring form.

Derivation runs where declarations are normalized, not only where they are
accepted. The fact is a function of two levels — a flag on the Attribute, and
axis-endpoint membership knowable only from the Entity's As-Of Axes — so a
frontend computes it while assembling an Entity's declared Attributes, and
every frontend computes it through one shared rule rather than its own copy.
That placement is forced by the surfaces the refusal has to cover: two of the
three assigning surfaces judge a declared member with no accepted model in
reach, so a designation that first appeared in accepted Metadata would silently
accept there what it refuses elsewhere — the divergence this record exists to
prevent. One rule with several callers is the requirement; a second
implementation of that rule is not one of them.

ADR 0013 settled this for the optimistic-lock version: Parallax sources the
value from the row the unit of work observed and computes the advance itself, so
a caller-supplied version is never a legitimate alternative. The same sentence
is true of the temporal axis endpoints, whose instants come from the Clock
Strategy and the verb's own window (ADR 0010), and of audit attributes, whose
values come from the Principal and the Transaction Instant (ADR 0037). What was
missing was the generalization: one designation those categories share, and one
rule that reads it.

Three cases are genuinely different, and the designation keeps them apart.

A value **authored by the caller** is refused where it is authored, rather than
several steps later when a row is derived from it. In an object frontend that
means the constructor refuses it, so the diagnostic names the assignment instead
of the row.

A value **assigned after authoring** — through an edited copy, a
predicate-selected write's typed assignment, or the serialized write boundary —
is refused by the shared rule. One rule rather than three checks is the point:
those surfaces differ only in how they resolve a name to a member, so a value
they all judge cannot be accepted by one and rejected by another.

A value that **arrives by hydration** stays readable and is never re-emitted as
a caller assignment. Hydration is how a framework-owned value legitimately
reaches an object at all, so refusing it there would make a stored row
unreadable; and treating a read-back value as an authored one would launder
stored state into an assignment the caller never made.

`framework_owned` is a distinct fact from the two designations beside it.
`optimistic_locking` names a role — this Attribute is the version — which
`m-opt-lock` reads to compute the advance; authorship is a separate question,
and a framework-owned Attribute that is not a version has no role to name.
`read_only` says the caller supplies the value once and may not change it, which
is a weaker claim: a read-only Attribute is authored at insert, a
framework-owned one is never authored at all. Keeping the three apart is what
lets a rejection say which of the three it is.

Because the designation is derived, no authoring surface gains a field and the
canonical descriptor is unchanged. Temporal axis endpoints are synthesized from
the authored temporality profile (ADR 0052), so their designation is a property
of that synthesis. Audit attributes are ordinary declared Attributes that Audit
Metadata references (ADR 0035), so theirs is a property of that reference.
Designating a category's members is therefore the whole cost of adding one: no
assigning surface changes, and no rejection is added.

Not chosen: passing the owning Entity into the shared rule so it could derive
axis membership itself. The rule states its verdict from the member alone, which
is what keeps the typed and serialized paths from disagreeing; making the verdict
depend on the position a member was reached from reintroduces exactly that
divergence.

Not chosen: leaving the refusal at the write boundary, where a caller-supplied
temporal instant was previously caught. The same authored value would then be
accepted by an edit and rejected at flush, and the diagnostic would name a
derived row rather than the assignment that produced it.

The normative detail lives in `core/spec/m-metamodel.md`.
