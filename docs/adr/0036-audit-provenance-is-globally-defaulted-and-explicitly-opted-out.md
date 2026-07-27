# Audit provenance is globally defaulted and explicitly opted out

Audit authoring has one portable meaning independent of Conformance Slice,
language target, or implemented module set. Omission requests an audited
standalone Entity or inheritance family; only explicit opt-out forms an
unaudited mapping. A surface that does not implement Audit Provenance may accept
only mappings that explicitly opt out. It rejects an omitted audit declaration
as an unsupported request rather than reinterpreting it as absence. A
Conformance Slice remains a coverage claim and never acts as an authoring or
Formation Profile.

Every frontend expands the audited default into ordinary unresolved attribute
declarations and Audit Metadata before Model Formation, so accepted metadata
remains explicit and representation-independent. The canonical descriptor's
opt-out-only spelling is `audit: false`; omission means audited and `audit:
true` is rejected. Python spells the same root-owned override
`audit=NO_AUDIT`; there is no `Audit(...)` configuration object or audit-column
override. Descendants inherit the root decision and cannot redeclare it.

Accepted metadata contains Audit Metadata or its absence, never an audit
boolean. Canonical export reconstructs the portable authoring form solely from
that accepted fact: present Audit Metadata exports by omission, while absence
exports as `audit: false`. Re-import therefore preserves the accepted model and
canonicalization remains idempotent without retaining a source spelling,
Formation Profile, or capability marker.

An audited Entity reserves the complete conventional audit vocabulary even when
its temporal shape does not use every attribute; user-authored members cannot be
silently adopted as framework provenance. An explicitly unaudited Entity
releases those names for ordinary domain use. Python applies the same
conditional-reservation pattern to temporal vocabulary: any temporal shape
reserves all four conventional axis properties, while a Non-Temporal Entity may
use them ordinarily.

Applicable Audit Attributes participate in full entity reads, relationship fetches, snapshots, inheritance projections, predicates, and ordering like ordinary scalar attributes. They materialize from the same row rather than through a hidden or lazy secondary fetch. Enabling the audit modules in a Conformance Slice therefore updates that slice's complete read projections, golden SQL, fixtures, and physical schemas; opting out removes the attributes entirely.

The default also applies to read-only Entities because Audit Metadata describes mapped row shape rather than write permission. Reads never synthesize or backfill absent provenance: fixtures and physical tables supply every applicable non-null value, and a legacy read-only mapping without those columns opts out explicitly.

Repository fixture provenance is explicit deterministic historical data, not a
side effect of fixture loading. General seed rows use a stable Subject Identity
such as `fixture:seed` and authored fixed Non-Temporal instants; temporal
revision time remains the row's authored Transaction-Time start. Dedicated
Audit Provenance cases use distinct identities to prove authorship transitions.
Fixture loading itself remains Principal-free and Clock-Strategy-free.

Principal propagation and Audit Provenance are lifecycle-neutral common-runtime
behavior in every slice that claims them. Both `slice-snapshot-1` and
`slice-managed-1` claim `m-principal` and `m-audit-provenance`; lifecycle
extensions do not acquire incompatible database-boundary signatures or model
defaults. A future slice may omit Audit Provenance while retaining Principal
propagation, but every model in that slice must opt out explicitly.

Adoption is a breaking mapped-schema and database-boundary API change. Repository-owned descriptors, provisioned test DDL, fixtures, expected table states, and golden SQL move together, but production `ALTER TABLE`, historical backfill, and application migration tooling are outside this decision. Existing applications migrate and backfill before enabling the audited mapping or opt out explicitly.
