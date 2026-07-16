"""``parallax.conformance.api_suite`` — API Conformance Suite machinery.

The coverage-partition computation and the Usage Guide model shared by the
``tests/api_conformance`` suite and the ``gen-usage-guide`` generator. The
partition asserts the union of exercised and reasoned-skipped cases equals the
active slice, with no stale case IDs and no empty skip reasons.

Reasoned skips are drawn from an **explicit, reviewed** registry
(:data:`SKIP_REASONS`, keyed by module) rather than auto-derived from the active
set. An active case whose module is absent from the registry is covered by
neither exercised nor skipped, so the partition fails — forcing a human to
classify a newly reachable capability rather than letting it inherit a generic
reason. A registry entry that names no unexercised active case is reported as
stale. Entries are removed as each module's idiomatic examples land.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from parallax.conformance import case_format
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim
from parallax.conformance.graph_stories import GRAPH_STORIES, graph_story_snippet
from parallax.conformance.read_stories import READ_STORIES
from parallax.conformance.stories import WRITE_STORIES, story_snippet

__all__ = [
    "CASE_SKIP_REASONS",
    "EXAMPLES",
    "SKIP_REASONS",
    "Example",
    "Partition",
    "Skip",
    "active_slice",
    "build_skips",
    "compute_partition",
    "partition_report",
    "render_usage_guide",
    "stale_skip_reasons",
]


@dataclass(frozen=True, slots=True)
class Example:
    """A documented idiomatic public-API example exercising one corpus case."""

    case_id: str
    title: str
    snippet: str


@dataclass(frozen=True, slots=True)
class Skip:
    """A reasoned skip: a corpus case with no idiomatic example yet, plus why."""

    case_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class Partition:
    """The coverage-partition result over the active slice."""

    active: frozenset[str]
    exercised: frozenset[str]
    skipped: frozenset[str]
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.errors


# The registered idiomatic examples. Each mirrors a corpus case and is proven by
# the operation no-drift guard (its statement serializes to the case's operation).
# Later phases append an Example per newly reachable case as its capability lands.
EXAMPLES: Final[list[Example]] = [
    # The op-algebra / temporal-read / navigate / single-concrete-inheritance
    # read examples: each is an executable read story
    # (`parallax.conformance.read_stories`) — the snippet is the story's own
    # authored source, and the real-Postgres suite executes the SAME `build()`
    # through the shipped `parallax.snapshot.connect` + `parallax-postgres`
    # (test_story_run's generic runner), grading the mirrored case's own
    # `then.rows` (order-insensitive, exact-typed) and `then.roundTrips`. The
    # `navigate`-tagged siblings (a corpus spelling redundancy for the
    # identical correlated-EXISTS lowering `exists` already expresses —
    # m-op-algebra), the deep-fetch-bearing temporal siblings, the
    # multi-concrete polymorphic PROJECTING inheritance reads, and the
    # Customer value-object family are reasoned-skipped; see
    # CASE_SKIP_REASONS.
    *(Example(story.case_id, story.title, story.snippet) for story in READ_STORIES),
    # The developer transaction surface (m-unit-work, M4): each write example IS
    # an executable story (`parallax.conformance.stories`) — the snippet is the
    # story's own source, the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run), and the
    # fake-port write no-drift guard drives the same function against the golden
    # DML. One source, three consumers: the guide cannot drift from execution.
    *(Example(story.case_id, story.title, story_snippet(story)) for story in WRITE_STORIES),
    # Rejected-case build-time proofs (m-op-algebra/m-navigate/m-value-object):
    # the idiomatic surface refuses the SAME invalid input the corpus's own
    # rejected lane grades, through the SAME model-aware validator
    # (`validate_operation`), naming the SAME classified rule — proven by
    # `test_idiomatic_statement_build_rejects_the_corpus_rule`.
    Example(
        "m-value-object-038",
        "A nested comparison whose literal type mismatches the declared attribute",
        "Customer.where(Customer.address.city == 42)\n"
        '# raises OperationRejectedError(rule="nested-literal-type-mismatch")',
    ),
    Example(
        "m-inheritance-040",
        "A narrow that broadens beyond its position",
        "Animal.where(Pet.narrow(WildBoar))\n"
        '# raises OperationRejectedError(rule="narrow-outside-position")',
    ),
    Example(
        "m-inheritance-041",
        "A concrete-subtype attribute referenced outside a narrow scope",
        "Animal.where(Dog.bark_volume > 5)\n"
        '# raises OperationRejectedError(rule="subtype-attribute-outside-narrow-scope")',
    ),
    Example(
        "m-inheritance-042",
        "A nested narrow that broadens back out of the enclosing position",
        "Animal.where(Pet.narrow(Dog, where=Animal.narrow(Cat)))\n"
        '# raises OperationRejectedError(rule="narrow-outside-position")',
    ),
    # Snapshot/graph semantics (m-snapshot-read, m-navigate x m-temporal-read):
    # each example IS an executable graph story
    # (`parallax.conformance.graph_stories`) — the snippet is the story's own
    # source, and the real-Postgres suite executes it through the shipped
    # `parallax.snapshot.connect` + `parallax-postgres` (test_story_run),
    # grading the mirrored case's own oracle (a `then.graph`/`identityChecks`
    # reference-identity assertion, a closed-world `UnloadedRelationshipError`,
    # a `pin`/`edge_of` coordinate, or a scenario's own per-step observable).
    *(Example(story.case_id, story.title, graph_story_snippet(story)) for story in GRAPH_STORIES),
]

# The reviewed skip registry: primary module -> the reason its active cases carry
# no idiomatic API example yet. Keyed by module (a reason bucket), and NOT derived
# from the active slice, so a corpus case whose module is absent here fails the
# partition (see module docstring). Each reason names the COR-3 phase that brings
# the module's developer surface online; the entry is dropped when that lands.
SKIP_REASONS: Final[dict[str, str]] = {
    "m-core": (
        "m-core neutral-type behaviour has no standalone developer surface; it is "
        "exercised through the first read path (COR-3 Phase 5)"
    ),
    "m-descriptor": (
        "descriptor introspection is proven by the descriptor no-drift guard; the read "
        "path compiles/runs its descriptor cases (COR-3 Phase 5)"
    ),
    "m-op-algebra": (
        "representative predicate/grouping/ordering spellings are exercised as idiomatic "
        "examples (COR-3 Phase 5); the remaining op-algebra cases are graded through the "
        "compile/run lanes and land as examples incrementally"
    ),
    "m-temporal-read": (
        "the representative as-of spelling is exercised as an idiomatic example (the D-7 "
        "class-frontend axis declaration landed in M4); the remaining temporal-read cases "
        "are graded through the compile/run conformance lanes and land as examples "
        "incrementally"
    ),
    "m-db-error": (
        "the m-db-error corpus cases are graded end-to-end by the M4 run lanes — the "
        "single-connection triggers by the error run sweep, the two-connection "
        "choreography by the provider deadlock proof; the neutral DatabaseError surface "
        "the developer sees is exercised through the transact abort/retry unit tests"
    ),
    "m-pk-gen": (
        "write-side id allocation (the sequence/max registry reads an insert without an "
        "authored id needs) lands with the pk-gen write path (a later write increment)"
    ),
    "m-auto-retry": (
        "the bounded retry loop is implemented (parallax.core.auto_retry, M4) and proven "
        "by fake-port unit tests of db.transact (test_transact); the boundary cases need "
        "the case-driven boundary runner (when.boundary / given.fault / then.outcome over "
        "a fault-injecting port), which lands with the API-suite boundary lane build-out "
        "(ledger D-17)"
    ),
    "m-read-lock": (
        "the in-transaction shared-read-lock suffix is rendered by every locking-mode "
        "find (M4 — the write scenarios' golden reads carry it); the m-read-lock case "
        "matrix (projection suppression, two-session behavioral admits/blocks) lands "
        "with the lock path (COR-3 Phase 8)"
    ),
    "m-opt-lock": "optimistic-lock writes land with the write family (COR-3 Phase 8)",
    "m-audit-write": "audit (close-and-chain) writes land with the write family (COR-3 Phase 8)",
    "m-bitemp-write": "bitemporal writes land with the write family (COR-3 Phase 8)",
    "m-batch-write": "batched and set-based writes land with the write family (COR-3 Phase 8)",
}

# Case-scoped skips take precedence over the module registry and exist so a
# module can be MOSTLY exercised without a broad bucket silently absorbing a
# case that loses its example (the backbone review's partition red-check): with
# no `m-unit-work` module entry, dropping any exercised m-unit-work example
# fails the partition ("covered by neither") instead of inheriting a reason.
_COALESCING_WITNESS_REASON: Final[str] = (
    "a same-transaction coalescing witness: it buffers an insert+update / insert+delete "
    "pair whose one-statement / zero-statement collapse is m-batch-write behavior "
    "(COR-3 Phase 8); the planner folding is already unit-pinned (test_write_lowering)"
)

# --------------------------------------------------------------------------- #
# COR-3 Phase 7 increment 6b: the five flipped module buckets (m-navigate,     #
# m-deep-fetch, m-snapshot-read, m-value-object, m-inheritance) retire their  #
# blanket "lands with Phase 7" entries above — Phase 7 has landed. Every      #
# remaining active case under those modules gets its OWN reasoned, honest,   #
# case-scoped entry below, grouped by identical justification.               #
# --------------------------------------------------------------------------- #

# Rows-form inheritance reads (TPH tag-predicate/abstract-root/narrow, TPCS
# union-all/narrow) that are a REPRESENTATIVE SIBLING of an already-exercised
# SINGLE-CONCRETE example: the SAME correlated tag-predicate / superset-projection
# mechanism, proven once per shape (m-inheritance-001/012, the two exercised
# single-concrete-resolving reads), applied to a different family or narrow
# combination. No new developer-facing spelling to add; the no-drift guard
# already proves the mechanism these siblings would only repeat. (The
# MULTI-concrete-resolving siblings — abstract-root / narrow-to-2+-concretes —
# are NOT covered by this reason: see
# `_INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON` below, which is
# a genuinely different, structural block, not a mere spelling repeat.)
_TPH_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised TPH single-concrete tag-predicate "
    "examples (m-inheritance-001/012): the SAME correlated tag-predicate + "
    "superset-projection mechanism, over a different family or narrow combination — no "
    "distinct developer-facing spelling to add"
)
_TPCS_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised TPCS single-concrete/semi-join examples "
    "(m-inheritance-005/070/071): the SAME union-all-over-concretes + narrow-scope "
    "mechanism, over a different subtype combination — no distinct developer-facing "
    "spelling to add"
)
_TPH_POLYMORPHIC_EXISTS_SIBLING_REASON: Final[str] = (
    "a representative sibling of the exercised polymorphic-navigation examples "
    "(m-inheritance-070/071 for table-per-concrete-subtype; m-navigate-004/008/010 for "
    "the correlated-EXISTS form itself): the TPH analogue is the SAME "
    "EXISTS-over-effective-concrete-set mechanism, just the other inheritance strategy"
)
_TEMPORAL_INHERITANCE_ROW_SIBLING_REASON: Final[str] = (
    "a representative sibling combining two INDEPENDENTLY exercised capabilities — the "
    "as-of spelling (m-temporal-read-003) and the TPH/TPCS single-concrete tag-predicate "
    "read (m-inheritance-001/005) — over a bitemporal instrument/rate family neither "
    "existing example mirrors; no new mechanism, no distinct spelling"
)

# The TPH concrete-target temporal read (m-inheritance-101, Bond): a strategy sibling
# of the concrete-target root-owned-axis inheritance mechanism m-inheritance-100's
# OWN ReadStory proves for real (through `db.find`, real Postgres, the SAME generic
# case-driven runner every other read story uses) — TPH's own tag-predicate
# composition is independently proven by m-inheritance-001, and its as-of
# composition by m-temporal-read-003; the residual-finding binding decision's
# genuinely new mechanism (a concrete-target read resolves its family's
# root-declared axes) is proven once, by the TPCS witness, not twice.
_CONCRETE_TARGET_TEMPORAL_ROOT_AXIS_SIBLING_REASON: Final[str] = (
    "a table-per-hierarchy strategy sibling of the concrete-target root-owned-axis "
    "inheritance mechanism `m-inheritance-100`'s own ReadStory proves for real (through "
    "`db.find`, real Postgres): TPH's own tag-predicate composition is already proven "
    "by `m-inheritance-001`, its as-of composition by `m-temporal-read-003` — the "
    "genuinely new mechanism (a concrete-target read resolves its family's root-declared "
    "axes) is proven once by the TPCS witness, not twice"
)

# Multi-concrete polymorphic PROJECTING inheritance reads (an abstract-root read,
# or a narrow resolving to 2+ concretes): genuinely UNREACHABLE through
# `db.find` today, for two independent reasons — (1) table-per-hierarchy: each
# row's own typed instance carries only ITS OWN concrete class's fields, never a
# sibling's nullable column the wire row's superset includes, so a flat
# `then.rows` comparison cannot be reproduced from typed instances at all
# (python.md §4 says the RIGHT observation is `type(node)`, not a flattened
# dict); (2) table-per-concrete-subtype: instance-form projection over 2+
# resolved concretes has no goldened lowering yet at all (`SqlGenError`,
# `sql_gen.compile._compile_tpcs_read`) — a genuine engine gap. Distinct from
# every other inheritance reasoned-skip above: those are spelling repeats of an
# executed mechanism; these cannot be executed through the shipped surface at
# all yet. Ledger D-22 is now RESOLVED at the core level (COR-3 Phase 8
# increment 1, DQ7b Option C): the instance-form oracle for an abstract
# multi-concrete read is defined (m-case-format "Read targeting", the
# per-variant node shape) and witnessed by `then.graph` siblings
# (m-inheritance-106/-107/-108/-109, own reasoned skips below,
# `_INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON`). These four
# ROW-FORM cases remain unreachable through `db.find` for the reason above —
# `db.find` is instance-form, not row-form — and stay the values-lane
# witnesses; the D-22 Python half (typed per-variant `db.find`) is increment 7.
_INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON: Final[str] = (
    "a multi-concrete polymorphic PROJECTING read (an abstract-root read, or a narrow "
    "resolving to 2+ concretes) — genuinely unreachable through `db.find` today: a "
    "table-per-hierarchy row's own typed instance carries only its OWN concrete class's "
    "fields, never a sibling's nullable column the wire row's superset includes, so a "
    "flat `then.rows` comparison cannot be reproduced from typed instances (python.md "
    "§4: the right observation is `type(node)`, not a flattened dict); "
    "table-per-concrete-subtype instance-form projection over 2+ resolved concretes has "
    "no goldened lowering at all yet (`SqlGenError`) — a genuine engine gap, not a "
    "partition-honesty concern to grade around"
)

# The four NEW instance-form (`then.graph`) siblings of the row-form multi-
# concrete reads just above (m-inheritance-106/-107/-108 siblings of -003/
# -013/-015; m-inheritance-109 sibling of -052): COR-3 Phase 8 part C authors
# the corpus-level oracle these pin, but `db.find` does not yet MATERIALIZE it.
# Table-per-hierarchy (106/107/108): the find executor's row decoding
# (`parallax.snapshot.materialize.decode_row`) still passes every projected
# column through unchanged — the SAME padded-superset shape a row-form read
# carries, never narrowed to the variant's own declared columns (compile
# already emits the correct, byte-identical golden SQL; only the RUN-time
# graph assembly is unimplemented, `test_run_sweep.py`'s own carve-out).
# Table-per-concrete-subtype (109): `_compile_tpcs_union_read` unconditionally
# refuses instance-form with `SqlGenError` over a 2+-concrete union-all read —
# a genuine engine gap, not model-specific. COR-3 Phase 8 increment 7 (ledger
# D-22) implements the per-variant narrowing and lifts the TPCS refusal;
# until then this is a forward-looking, honestly-reasoned skip, not the
# permanent posture the descriptor-rejection group above carries.
_INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON: Final[str] = (
    "the then.graph instance-form oracle for a multi-concrete polymorphic read (the "
    "per-variant node shape: own-branch members only, no null sibling padding, plus "
    "familyVariant) — db.find on an abstract multi-concrete position does not yet "
    "materialize typed per-variant instances (table-per-hierarchy: the find executor's "
    "row decoding still passes the padded superset through unchanged; table-per-"
    "concrete-subtype: instance-form projection over 2+ resolved concretes has no "
    "goldened lowering at all yet, SqlGenError) — COR-3 Phase 8 increment 7 (ledger "
    "D-22) implements the narrowing and lifts the TPCS refusal; the row-form siblings "
    "(m-inheritance-003/-013/-015/-052) remain the values-lane witnesses"
)

# Inheritance-family / temporal writes: `lower_write` (parallax.snapshot.handle)
# explicitly refuses any instruction whose entity declares `inheritance` or is
# temporal, naming COR-3 Phase 8 — a byte-stable existing refusal this phase
# does not touch (D-16's full graduation, DQ1, changed the verbs' INPUTS, never
# the supported write classes).
_INHERITANCE_WRITE_PHASE8_REASON: Final[str] = (
    "an inheritance-family and/or temporal write: `lower_write` explicitly refuses any "
    "instruction whose entity declares `inheritance` (tag / concrete-subtype DML) or is "
    "temporal (milestone lowering), naming COR-3 Phase 8 — the existing, byte-stable "
    "refusal D-16's full graduation (DQ1) left untouched (it changed the verbs' inputs, "
    "never the supported write classes)"
)
_INHERITANCE_WRITE_REJECT_PHASE8_REASON: Final[str] = (
    "a write-PAYLOAD validation rule (subtype-write sibling/metadata/abstract-target/"
    "set-based attribute checks) — the write-side portion of D-12's third bullet, "
    "explicitly deferred to the write family (COR-3 Phase 8) alongside "
    "`write-required-attribute-missing` and its siblings (test_rejected_sweep.py already "
    "grades every `when.write` rejected case this way at the conformance-adapter layer); "
    "the read-side rejected lane (COR-3 Phase 7 increment 1) grades only `when.operation` "
    "inputs"
)

# `when.model` descriptor-shape rejects (m-inheritance-020..032, plus the
# residual-finding root-ownership witnesses 098/099, plus the D-25 optimistic-
# locking root-ownership witnesses 102/103): a DIFFERENT validation surface
# than the operation-level rejected lane increment 1 built.
# `parallax.core.inheritance.validate` classifies these exact rules, but the
# class metaclass never calls it (grep-verified) — DQ2's hierarchy-derived
# `parent`/`role` obsoletes most of what it checks. Most of these malformed
# shapes have literally no idiomatic spelling (`parent`/`role` are DERIVED from
# the live Python class hierarchy, never separately authored; Python's own
# class system additionally forbids a literal inheritance cycle), and the two
# table-placement rules that ARE independently authorable (`EntityConfig
# (table=...)` on an abstract node) are already rejected by the class
# frontend's own, DIFFERENT, unclassified error (`test_inheritance_frontend.py`
# "tableless and rowless"), not by `InheritanceError.rule`. A descendant
# declaring `EntityConfig(as_of=...)` (098/099's own rule,
# `inheritance-temporal-axes-not-root-owned`) or its own `optimisticLocking`
# attribute (102/103's own rule,
# `inheritance-optimistic-locking-not-root-owned`, D-25 / ADR 0027) is ALSO
# independently authorable, and likewise rejected by the class frontend's own,
# DIFFERENT, unclassified error (`test_inheritance_frontend.py`
# "family SUBCLASS cannot declare EntityConfig(as_of..." /
# "only the inheritance family root may declare"), joining the table-placement
# rules in the same posture — so no case in this whole group reproduces
# `then.rejectedRule` through today's public surface. This gap is PERMANENT
# (the metaclass-never-calls-`inheritance.validate` posture pre-dates and
# outlives this phase), not a forward promise.
_INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON: Final[str] = (
    "a `when.model` raw-descriptor invariant `parallax.core.inheritance.validate` "
    "classifies (parent/root/cycle/strategy/tag/temporal-axis-ownership/optimistic-"
    "locking-ownership shape) — the class metaclass never calls this validator (DQ2: "
    "`parent`/`role` are DERIVED from the live Python class hierarchy, never separately "
    "authored, so most of these malformed shapes — an unknown parent, a cycle, multiple "
    "roots, a missing root, a redeclared strategy, a duplicate/misplaced tag — have no "
    "idiomatic spelling at all); the table-placement rules AND a descendant's own "
    "`as_of` / `optimisticLocking` ARE independently authorable, but the class "
    "frontend's own existing checks raise a different, unclassified error in each case, "
    "not `InheritanceError.rule` — wiring an idiomatic path to the classified "
    "vocabulary is unbuilt infrastructure, not a capability gap this phase closes "
    "(permanent, pre-dating and outliving Phase 7/8)"
)

# `navigate`-tagged corpus siblings: a deliberate spelling redundancy for the
# IDENTICAL correlated-EXISTS lowering the exercised `.any()`/`.none()` examples
# already prove (m-navigate-002/003/004/006/008/009/010) — m-op-algebra's own
# framing ("navigate and exists are the same correlated-EXISTS lowering").
_NAVIGATE_TAG_REDUNDANT_REASON: Final[str] = (
    "a `navigate`-tagged corpus spelling redundancy for the IDENTICAL correlated-EXISTS "
    "lowering the exercised `.any()`/`.none()` examples already prove "
    "(m-navigate-002/003/004/006/008/009/010) — no distinct developer-facing shape to add"
)

# Temporal deep-fetch GRAPH siblings of the executed m-navigate-013 story (the
# ONE representative proof that a root as-of pin propagates per-hop into a
# deep-fetch child level): every other axis/cardinality/model permutation of
# the SAME propagation mechanism.
_TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON: Final[str] = (
    "a representative sibling of the EXECUTED `m-navigate-013` graph story (the "
    "as-of-pin-propagates-per-hop-into-a-deep-fetch-level capability, real-Postgres "
    "proven via `parallax.snapshot.connect` + `db.find`): the SAME propagation "
    "mechanism, a different axis/cardinality/model permutation — building a second "
    "executable story would re-prove the identical mechanism, not a new one"
)

# Snapshot-graph siblings of the executed orders-family graph stories (diamond
# identity, back-reference cycle, closed-world, empty root/intermediate): a
# different relationship shape (to-one nullable, shared-prefix dedup, declared
# ordering) over the SAME materializer already exercised for real.
_ORDERS_GRAPH_SIBLING_REASON: Final[str] = (
    "a representative sibling of the executed orders-family graph stories "
    "(m-snapshot-read-001/004/005/009/010/011): a different relationship shape "
    "(to-one nullable, shared-prefix dedup, declared child ordering) over the SAME "
    "assembler + frozen-node wrap already proven for real against Postgres"
)

# `models/person.yaml`'s own Person/Passport pair (the one-to-one graph case)
# lives in `tests/mirrored_models.py` — a test-only module, unreachable from
# the installed `parallax-conformance` distribution `graph_stories.py` needs
# (package-boundary rule, spec §7/§8): no parallax.conformance-scoped Person
# mirror exists, so this case cannot be driven through a real db.find story
# today. Deferred: ledger D-20 (the single, global, process-wide entity-registry
# constraint — closing it needs a registry/naming refactor, not this suite).
_PERSON_MIRROR_UNREACHABLE_REASON: Final[str] = (
    "`models/person.yaml`'s Person/Passport pair lives in `tests/mirrored_models.py` — "
    "test-only, unreachable from the installed `parallax-conformance` distribution "
    "`graph_stories.py` needs (the package-boundary rule, spec §7/§8) — no "
    "parallax.conformance-scoped Person mirror exists to drive this as a real story"
)

# `models/animal.yaml`'s own polymorphic owner is ALSO named `Person` — the
# same literal canonical name `mirrored_models.Person` already claims in the
# single, global, process-wide entity registry (see `snapshot_models`'s own
# module docstring, which renamed its OWN animal-family owner to `AnimalOwner`
# for exactly this reason). Any proof needing the EXACT corpus operation text
# (`rel: Person.pets`) or a real db.find over the animal family's owner
# relationship is unreachable: `snapshot_models`/`inheritance_models` are
# themselves test-only (same package-boundary rule as Person above), so even a
# renamed mirror cannot be driven from `parallax.conformance`. Deferred: ledger
# D-20 (the SAME single, global, process-wide entity-registry constraint the
# Person-mirror reason above defers).
_ANIMAL_OWNER_COLLISION_REASON: Final[str] = (
    "`models/animal.yaml`'s own polymorphic owner is ALSO named `Person` — the same "
    "canonical name `mirrored_models.Person` claims in the single, global, "
    "process-wide entity registry (`snapshot_models` renames its own mirror to "
    "`AnimalOwner` for exactly this reason); the exact corpus operation text names the "
    "real `Person.pets` relationship, and `snapshot_models`/`inheritance_models` are "
    "themselves test-only (unreachable from the installed `parallax-conformance` "
    "distribution `graph_stories.py` needs) — no reachable mirror can reproduce this "
    "case's operation or drive it as a real story today"
)

# `.history()`/`.as_of_range()` combined with `.include(...)` is an EXPLICIT,
# documented deferral (spec §3 `snapshot-history-includes`): `Statement`
# refuses the combination with `UnsupportedFeatureError` naming it. Not a gap —
# a designed-in refusal.
_SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON: Final[str] = (
    "`.history()`/`.as_of_range()` combined with `.include(...)` is an EXPLICIT, "
    "designed-in deferral (spec §3 `snapshot-history-includes`): `Statement` refuses "
    "the combination with `UnsupportedFeatureError` naming it — not a capability gap, a "
    "documented refusal"
)

# Value-object nested/absence/cast/array-traversal PREDICATE reads: rows-form,
# representative siblings of the Customer.address predicate BUILD-TIME proofs
# (m-value-object-001/002/007/015/016/017/019 — themselves case-scoped skips
# below, the Customer registry collision, never executed for real either) —
# the SAME nested-path resolution / absence-collapse / any-element lowering, a
# different operator, depth, or dialect-cast variant, and the SAME
# reachability block a real execution of any of them would hit.
_VO_PREDICATE_SIBLING_REASON: Final[str] = (
    "a representative sibling of the Customer.address predicate build-time proofs "
    "(m-value-object-001/002/007/015/016/017/019 — themselves case-scoped skips, the "
    "Customer registry collision below): the SAME nested-path resolution / "
    "absence-collapse / any-element lowering, a different operator, depth, or "
    "dialect-cast variant — no distinct developer-facing shape to add, and the SAME "
    "reachability block a real execution would hit"
)

# Customer-model cases needing a REAL execution (a `db.find`/`db.transact`
# story, not a build-only statement): `value_object_models.Customer` — the
# SAME canonical name this case's model declares — already claims "Customer"
# in the single, global, process-wide entity registry, and it is test-only
# (unreachable from the installed `parallax-conformance` distribution
# `stories.py`/`graph_stories.py`/`read_stories.py` need, the SAME
# package-boundary rule `snapshot_models`'s own docstring documents for
# animal.yaml's owner). A purpose-built, differently-named mirror could
# reproduce the WRITE DML, GRAPH shape, or ROW result but never the exact
# corpus operation/wire text this suite's no-drift guards compare, since the
# case's own `targetEntity`/`entity` names the real "Customer" — this covers
# the row-form predicate reads (m-value-object-001/002/007/015/016/017/019)
# exactly as it already covered the graph/write cases. Deferred: ledger D-20
# (the SAME single, global, process-wide entity-registry constraint the
# Person/AnimalOwner reasons above defer).
_CUSTOMER_UNREACHABLE_REASON: Final[str] = (
    "needs a REAL execution (a `db.find`/`db.transact` story) over the Customer "
    "entity, but `value_object_models.Customer` already claims that canonical name in "
    "the single, global, process-wide entity registry and is test-only — unreachable "
    "from the installed `parallax-conformance` distribution `stories.py`/"
    "`graph_stories.py`/`read_stories.py` need (the same package-boundary collision "
    "`snapshot_models`'s own docstring documents for animal.yaml's owner); a "
    "differently-named mirror could run the SQL but could never reproduce this case's "
    "own `Customer`-named operation/wire text"
)

# Supplier/Branch value-object-bearing temporal reads: genuinely exercisable in
# principle (temporal as-of and value-object materialization are each already
# proven independently), but no suite mirror or story exists yet for these two
# families — new coverage surface this increment's explicit item list did not
# build, not a structural block. Deferred: ledger D-21 (add the Supplier/Branch
# mirror and story — a coverage-surface gap, distinct from D-20's structural
# registry constraint).
_VO_TEMPORAL_GRAPH_DEFERRED_REASON: Final[str] = (
    "combines two independently-proven capabilities (temporal as-of reads, "
    "value-object composite materialization) over Supplier/Branch, families with no "
    "suite mirror or story yet — new coverage surface this increment did not build, "
    "not a structural block; a future increment can add the mirror and story"
)
_VO_TEMPORAL_WRITE_PHASE8_REASON: Final[str] = (
    "an audit-write / bitemp-write temporal write over a value-object-bearing entity — "
    "the write family's temporal milestone lowering (COR-3 Phase 8; m-audit-write / "
    "m-bitemp-write), matching this registry's own m-audit-write/m-bitemp-write bucket "
    "reasons"
)

# Value-object STRUCTURE rejects: each empirically confirmed (a REPL probe
# against the shipped surface) to have NO idiomatic spelling that reaches
# `validate_operation` with the corpus's own invalid shape — four DISTINCT
# failure modes, not one generic gap.
_VO_UNKNOWN_NESTED_FIELD_REASON: Final[str] = (
    "`Customer.contact` (the invalid path's first segment) is not a declared "
    "attribute at all: `vm.Customer.contact.city == ...` raises a plain Python "
    "`AttributeError` at attribute-access time — before any operation tree exists to "
    "validate, so the corpus's own invalid shape (a schema-valid but model-unknown "
    "nested path) has no idiomatic spelling to build"
)
_VO_DEEPFETCH_SEGMENT_REASON: Final[str] = (
    "`.include(...)` only accepts `RelationshipPath` arguments; `Customer.address` (a "
    "value-object `Attr`, not a `Rel`) raises a plain Python `TypeError` when passed to "
    "it — the type system itself prevents authoring the corpus's invalid "
    "deep-fetch-through-a-value-object shape"
)
_VO_NAVIGATE_TARGET_REASON: Final[str] = (
    "`Customer.address.any()` builds successfully, but to a DIFFERENT, valid operation "
    "(`nestedExists`, the to-many VO presence quantifier m-value-object-015/016 already "
    "exercise) — not the corpus's invalid `navigate` node targeting a value object; the "
    "idiomatic surface has no spelling that produces THAT exact shape, only a "
    "differently-typed valid one"
)
_VO_FIND_ROOT_REASON: Final[str] = (
    "`ValueObject` classes have no `.where()` classmethod at all (only `Entity` does); "
    "`vm.Address.where(...)` raises a plain Python `AttributeError` — the type system "
    "itself prevents rooting a find at a value object"
)

# Value-object write-input validation rejects (m-value-object-039..044): the
# write-side portion of D-12's third bullet, explicitly Phase 8 — the SAME
# reasoning `test_rejected_sweep.py` already applies to every `when.write`
# rejected case at the conformance-adapter layer.
_VO_WRITE_VALIDATION_PHASE8_REASON: Final[str] = (
    "a write-INPUT validation rule (required-attribute-missing at depth 1/2/3, a "
    "missing required value object, a value-type mismatch, a non-nullable top-level "
    "null) — the write-side portion of D-12's third bullet, explicitly deferred to the "
    "write family (COR-3 Phase 8); `test_rejected_sweep.py` already grades every "
    "`when.write` rejected case this way at the conformance-adapter layer"
)

# The three remaining m-value-object write-family siblings, each a DIFFERENT
# Phase-8 concern already named by an existing module bucket above.
_VO_BATCH_WRITE_REASON: Final[str] = (
    "a multi-row (batched) insert — the set-based flush collapse lands with the write "
    "family (COR-3 Phase 8; m-batch-write), matching this registry's own m-batch-write "
    "bucket reason"
)
_VO_OPT_LOCK_CONFLICT_REASON: Final[str] = (
    "a versioned write under an optimistic-lock gate — lands with the write family "
    "(COR-3 Phase 8; m-opt-lock), matching this registry's own m-opt-lock bucket reason"
)
_VO_SCENARIO_COMBO_REASON: Final[str] = (
    "a scenario combining a managed find, a materialized-predicate-write resolving "
    "read, and an audit-write terminate under an optimistic-lock gate — every step "
    "beyond the plain managed find is Phase-8 territory (m-audit-write / m-opt-lock / "
    "m-batch-write's predicate-write materialization); no isolated Phase-7 read facet "
    "to exercise separately"
)

CASE_SKIP_REASONS: Final[dict[str, str]] = {
    "m-unit-work-008": _COALESCING_WITNESS_REASON,
    "m-unit-work-010": _COALESCING_WITNESS_REASON,
    # -- m-inheritance: rows-form representative siblings ------------------- #
    "m-inheritance-002": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-004": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-011": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-014": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-016": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-017": _TPH_ROW_SIBLING_REASON,
    "m-inheritance-006": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-050": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-051": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-053": _TPCS_ROW_SIBLING_REASON,
    "m-inheritance-060": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-061": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-062": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-063": _TPH_POLYMORPHIC_EXISTS_SIBLING_REASON,
    "m-inheritance-092": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-093": _TEMPORAL_INHERITANCE_ROW_SIBLING_REASON,
    "m-inheritance-101": _CONCRETE_TARGET_TEMPORAL_ROOT_AXIS_SIBLING_REASON,
    # -- m-inheritance: multi-concrete polymorphic PROJECTING reads (genuinely #
    # unreachable through `db.find` today — see the reason's own comment) --- #
    "m-inheritance-003": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-013": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-015": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    "m-inheritance-052": _INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON,
    # -- m-inheritance: instance-form (`then.graph`) multi-concrete siblings — #
    # COR-3 Phase 8 part C authors the oracle; increment 7 implements it ----- #
    "m-inheritance-106": _INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON,
    "m-inheritance-107": _INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON,
    "m-inheritance-108": _INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON,
    "m-inheritance-109": _INHERITANCE_INSTANCE_FORM_MULTI_CONCRETE_DEFERRED_REASON,
    # -- m-inheritance: write family (COR-3 Phase 8) ------------------------- #
    "m-inheritance-007": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-008": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-009": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-010": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-080": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-081": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-082": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-083": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-084": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-085": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-090": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-091": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-094": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-095": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-096": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-097": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-104": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-105": _INHERITANCE_WRITE_PHASE8_REASON,
    "m-inheritance-086": _INHERITANCE_WRITE_REJECT_PHASE8_REASON,
    "m-inheritance-087": _INHERITANCE_WRITE_REJECT_PHASE8_REASON,
    "m-inheritance-088": _INHERITANCE_WRITE_REJECT_PHASE8_REASON,
    "m-inheritance-089": _INHERITANCE_WRITE_REJECT_PHASE8_REASON,
    # -- m-inheritance: `when.model` descriptor rejects (unreachable) -------- #
    "m-inheritance-020": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-021": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-022": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-023": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-024": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-025": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-026": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-027": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-028": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-029": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-030": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-031": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-032": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-098": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-099": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-102": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    "m-inheritance-103": _INHERITANCE_DESCRIPTOR_REJECT_UNREACHABLE_REASON,
    # -- m-inheritance / m-navigate: the Person/AnimalOwner collision -------- #
    "m-inheritance-064": _ANIMAL_OWNER_COLLISION_REASON,
    "m-inheritance-072": _ANIMAL_OWNER_COLLISION_REASON,
    "m-inheritance-065": _ANIMAL_OWNER_COLLISION_REASON,
    "m-inheritance-066": _ANIMAL_OWNER_COLLISION_REASON,
    "m-inheritance-067": _ANIMAL_OWNER_COLLISION_REASON,
    "m-snapshot-read-012": _ANIMAL_OWNER_COLLISION_REASON,
    # -- m-deep-fetch: the Customer-registry collision ----------------------- #
    "m-deep-fetch-018": _CUSTOMER_UNREACHABLE_REASON,
    # -- m-navigate: `navigate`-tagged corpus spelling redundancy ------------ #
    "m-navigate-001": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-005": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-007": _NAVIGATE_TAG_REDUNDANT_REASON,
    "m-navigate-011": _NAVIGATE_TAG_REDUNDANT_REASON,
    # -- m-navigate / m-snapshot-read: temporal deep-fetch graph siblings ---- #
    "m-navigate-012": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-014": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-015": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-016": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-017": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-019": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-020": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-021": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-022": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-navigate-024": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    "m-snapshot-read-002": _TEMPORAL_DEEPFETCH_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: orders-family graph siblings ----------------------- #
    "m-snapshot-read-003": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-006": _ORDERS_GRAPH_SIBLING_REASON,
    "m-snapshot-read-008": _ORDERS_GRAPH_SIBLING_REASON,
    # -- m-snapshot-read: Person mirror unreachable / history+include -------- #
    "m-snapshot-read-007": _PERSON_MIRROR_UNREACHABLE_REASON,
    "m-snapshot-read-013": _SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON,
    "m-snapshot-read-014": _SNAPSHOT_HISTORY_INCLUDES_UNSUPPORTED_REASON,
    # -- m-value-object: predicate-read representative siblings ------------- #
    "m-value-object-004": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-005": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-006": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-008": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-009": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-010": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-011": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-012": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-013": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-014": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-018": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-020": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-021": _VO_PREDICATE_SIBLING_REASON,
    "m-value-object-022": _VO_PREDICATE_SIBLING_REASON,
    # -- m-value-object: the Customer-registry collision (read + write) ------ #
    "m-value-object-001": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-002": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-007": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-015": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-016": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-017": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-019": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-023": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-024": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-025": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-026": _CUSTOMER_UNREACHABLE_REASON,
    "m-value-object-027": _CUSTOMER_UNREACHABLE_REASON,
    # -- m-value-object: Supplier/Branch temporal VO (deferred, not blocked) - #
    "m-value-object-028": _VO_TEMPORAL_GRAPH_DEFERRED_REASON,
    "m-value-object-029": _VO_TEMPORAL_GRAPH_DEFERRED_REASON,
    "m-value-object-030": _VO_TEMPORAL_GRAPH_DEFERRED_REASON,
    "m-value-object-031": _VO_TEMPORAL_GRAPH_DEFERRED_REASON,
    "m-value-object-032": _VO_TEMPORAL_WRITE_PHASE8_REASON,
    "m-value-object-033": _VO_TEMPORAL_WRITE_PHASE8_REASON,
    # -- m-value-object: structural rejects (no idiomatic spelling exists) --- #
    "m-value-object-034": _VO_UNKNOWN_NESTED_FIELD_REASON,
    "m-value-object-035": _VO_DEEPFETCH_SEGMENT_REASON,
    "m-value-object-036": _VO_NAVIGATE_TARGET_REASON,
    "m-value-object-037": _VO_FIND_ROOT_REASON,
    # -- m-value-object: write-input validation rejects (COR-3 Phase 8) ------ #
    "m-value-object-039": _VO_WRITE_VALIDATION_PHASE8_REASON,
    "m-value-object-040": _VO_WRITE_VALIDATION_PHASE8_REASON,
    "m-value-object-041": _VO_WRITE_VALIDATION_PHASE8_REASON,
    "m-value-object-042": _VO_WRITE_VALIDATION_PHASE8_REASON,
    "m-value-object-043": _VO_WRITE_VALIDATION_PHASE8_REASON,
    "m-value-object-044": _VO_WRITE_VALIDATION_PHASE8_REASON,
    # -- m-value-object: the remaining write-family siblings (COR-3 Phase 8) - #
    "m-value-object-045": _VO_BATCH_WRITE_REASON,
    "m-value-object-046": _VO_OPT_LOCK_CONFLICT_REASON,
    "m-value-object-047": _VO_SCENARIO_COMBO_REASON,
}


def _selection_filter(claim: Claim) -> case_format.SelectionFilter:
    return case_format.SelectionFilter(
        modules=frozenset(claim.modules),
        case_shapes=frozenset(claim.case_shapes),
        include=frozenset(claim.include),
        exclude=frozenset(claim.exclude),
    )


def active_slice(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
) -> list[case_format.Case]:
    """The corpus cases the claim's selection expression admits."""
    corpus = cases if cases is not None else case_format.load_cases()
    return case_format.select(corpus, _selection_filter(claim))


def build_skips(
    active: list[case_format.Case],
    examples: list[Example],
    reasons: Mapping[str, str] = SKIP_REASONS,
    case_reasons: Mapping[str, str] = CASE_SKIP_REASONS,
) -> list[Skip]:
    """Reasoned skips for un-exercised active cases the registries cover.

    A case-scoped reason (``case_reasons``, keyed by case id) takes precedence
    over the module registry. A case covered by neither is deliberately left
    uncovered — the partition then flags it as covered by neither, forcing a
    human to classify the newly reachable case rather than letting a broad
    module bucket absorb it.
    """
    exercised = {example.case_id for example in examples}
    skips: list[Skip] = []
    for case in active:
        if case.case_id in exercised:
            continue
        if case.case_id in case_reasons:
            skips.append(Skip(case.case_id, case_reasons[case.case_id]))
        elif case.primary_module in reasons:
            skips.append(Skip(case.case_id, reasons[case.primary_module]))
    return skips


def stale_skip_reasons(
    active: list[case_format.Case],
    examples: list[Example],
    reasons: Mapping[str, str] = SKIP_REASONS,
    case_reasons: Mapping[str, str] = CASE_SKIP_REASONS,
) -> list[str]:
    """Error strings for registry entries that name no un-exercised active case.

    A module entry is stale when its module is absent from the active slice or
    every case it would cover is already exercised (or case-scoped); a
    case-scoped entry is stale when its case is inactive or exercised. Either
    way the entry produces no skip and is dead weight that must be pruned.
    """
    exercised = {example.case_id for example in examples}
    unexercised = [case for case in active if case.case_id not in exercised]
    covered = {case.primary_module for case in unexercised if case.case_id not in case_reasons}
    stale = [
        f"stale skip-registry entry {module!r}: names no un-exercised active case"
        for module in sorted(reasons)
        if module not in covered
    ]
    unexercised_ids = {case.case_id for case in unexercised}
    stale.extend(
        f"stale case-skip entry {case_id!r}: not an un-exercised active case"
        for case_id in sorted(case_reasons)
        if case_id not in unexercised_ids
    )
    return stale


def compute_partition(
    active_ids: frozenset[str],
    exercised: list[Example],
    skips: list[Skip],
) -> Partition:
    """Compute and validate the coverage partition of the active slice.

    Records an error for any stale ID (exercised/skipped outside the slice), any
    empty skip reason, any case both exercised and skipped, and any active case
    covered by neither.
    """
    exercised_ids = frozenset(example.case_id for example in exercised)
    skipped_ids = frozenset(skip.case_id for skip in skips)
    errors: list[str] = []
    for case_id in sorted(exercised_ids - active_ids):
        errors.append(f"stale exercised id (not in active slice): {case_id}")
    for case_id in sorted(skipped_ids - active_ids):
        errors.append(f"stale skipped id (not in active slice): {case_id}")
    for skip in skips:
        if not skip.reason.strip():
            errors.append(f"empty skip reason: {skip.case_id}")
    for case_id in sorted(exercised_ids & skipped_ids):
        errors.append(f"case both exercised and skipped: {case_id}")
    for case_id in sorted(active_ids - (exercised_ids | skipped_ids)):
        errors.append(f"active case covered by neither exercised nor skipped: {case_id}")
    return Partition(active_ids, exercised_ids, skipped_ids, tuple(errors))


def partition_report(
    claim: Claim = SNAPSHOT_CLAIM,
    cases: list[case_format.Case] | None = None,
    examples: list[Example] | None = None,
) -> Partition:
    """Load the active slice and compute its partition against the skip registry."""
    active = active_slice(claim, cases)
    registered = examples if examples is not None else EXAMPLES
    skips = build_skips(active, registered, SKIP_REASONS)
    active_ids = frozenset(case.case_id for case in active)
    partition = compute_partition(active_ids, registered, skips)
    stale = stale_skip_reasons(active, registered, SKIP_REASONS)
    if not stale:
        return partition
    return Partition(
        partition.active,
        partition.exercised,
        partition.skipped,
        (*partition.errors, *stale),
    )


_GUIDE_HEADER: Final[str] = (
    "<!-- GENERATED by `gen-usage-guide` from the API Conformance Suite. "
    "Do not edit by hand; run `just python-verify` / `uv run gen-usage-guide`. -->"
)


def render_usage_guide(examples: list[Example]) -> str:
    """Render the Usage Guide markdown from the registered examples."""
    lines: list[str] = [
        _GUIDE_HEADER,
        "",
        "# Parallax Python — Usage Guide",
        "",
        "Idiomatic public-API usage, generated from the API Conformance Suite's",
        "examples. Each example mirrors a compatibility-corpus case, so the guide",
        "cannot drift from graded behavior.",
        "",
    ]
    if not examples:
        lines.append(
            "_No idiomatic examples yet — they are added as each COR-3 phase brings "
            "its capability online._"
        )
        lines.append("")
    else:
        # The D-16 staged-realization notice retired here (COR-3 Phase 7
        # increment 6b): the transaction verbs it warned about graduated to
        # their final entity-instance signatures in increment 6a
        # (`tx.insert(instance)` / `tx.update(edited_copy)` / `tx.delete(node)`,
        # `tx.find` returning `Snapshot[T]`) — every rendered transaction
        # example already uses that final surface, so a banner distinguishing
        # "provisional" from "final" has nothing left to warn about. Plain
        # removal, not a replacement "graduated" note: the ordinary per-example
        # rendering below already IS the final, non-provisional documentation.
        for example in sorted(examples, key=lambda item: item.case_id):
            lines.append(f"## {example.title}")
            lines.append("")
            lines.append(f"Corpus case: `{example.case_id}`")
            lines.append("")
            lines.append("```python")
            lines.append(example.snippet)
            lines.append("```")
            lines.append("")
    # Collapse the trailing separator blank(s) into a single terminating newline
    # so the generated Markdown satisfies markdownlint MD012 (no multiple blanks).
    return "\n".join(lines).rstrip("\n") + "\n"
