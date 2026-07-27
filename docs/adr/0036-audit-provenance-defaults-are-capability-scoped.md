# Audit provenance defaults are capability-scoped

Audit defaulting is capability-scoped. In a Conformance Slice or language
profile that includes `m-audit-provenance`, every standalone Entity and
inheritance family is audited by default and an explicit opt-out is required to
form an unaudited model. In a profile that omits the module, omission produces
no Audit Metadata and explicit audit authoring is unsupported. This lets a
smaller slice omit audit entirely without depending on or partially
implementing it.

An audit-capable frontend expands the default into ordinary unresolved
attribute declarations and Audit Metadata before Model Formation, so accepted
metadata remains explicit and representation-independent. The canonical
descriptor's opt-out-only spelling is `audit: false`; omission means audited
when the capability is active and `audit: true` is rejected. Python spells the
same root-owned override `audit=NO_AUDIT`; there is no `Audit(...)`
configuration object or audit-column override. Descendants inherit the root
decision and cannot redeclare it. The authoring control disappears during
expansion: accepted metadata contains Audit Metadata or its absence, never an
audit boolean.

An audited Entity reserves the complete conventional audit vocabulary even when its temporal shape does not use every attribute; user-authored members cannot be silently adopted as framework provenance. An unaudited Entity, including every Entity in a profile without the audit capability, releases those names for ordinary domain use. Python applies the same conditional-reservation pattern to temporal vocabulary: any temporal shape reserves all four conventional axis properties, while a Non-Temporal Entity may use them ordinarily.

Applicable Audit Attributes participate in full entity reads, relationship fetches, snapshots, inheritance projections, predicates, and ordering like ordinary scalar attributes. They materialize from the same row rather than through a hidden or lazy secondary fetch. Enabling the audit modules in a Conformance Slice therefore updates that slice's complete read projections, golden SQL, fixtures, and physical schemas; opting out removes the attributes entirely.

The default also applies to read-only Entities because Audit Metadata describes mapped row shape rather than write permission. Reads never synthesize or backfill absent provenance: fixtures and physical tables supply every applicable non-null value, and a legacy read-only mapping without those columns opts out explicitly.

Repository fixture provenance is explicit deterministic historical data, not a
side effect of fixture loading. General seed rows use a stable Subject Identity
such as `fixture:seed` and authored fixed Non-Temporal instants; temporal
revision time remains the row's authored Transaction-Time start. Dedicated
Audit Provenance cases use distinct identities to prove authorship transitions.
Fixture loading itself remains Principal-free and Clock-Strategy-free.

Principal propagation and Audit Provenance are lifecycle-neutral common-runtime behavior in every slice that claims them. Both `slice-snapshot-1` and `slice-managed-1` claim `m-principal` and `m-audit-provenance`; lifecycle extensions do not acquire incompatible database-boundary signatures or model defaults. A different conforming slice may omit Audit Provenance while retaining Principal propagation.

Adoption is a breaking mapped-schema and database-boundary API change. Repository-owned descriptors, provisioned test DDL, fixtures, expected table states, and golden SQL move together, but production `ALTER TABLE`, historical backfill, and application migration tooling are outside this decision. Existing applications migrate and backfill before enabling the audited mapping or opt out explicitly.

Staged implementation does not use opt-out as a general compatibility escape.
The Non-Temporal delivery converts every Non-Temporal corpus model to the
audited default except one intentional unaudited witness. It may add only
enumerated temporary opt-outs to temporal corpus models, each carrying the
acceptance condition that the temporal delivery removes it. That final delivery
removes every temporary opt-out and updates the affected fixtures, projections,
DML, and table states.
