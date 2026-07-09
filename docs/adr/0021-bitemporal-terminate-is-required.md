# Bitemporal terminate is required alongside terminateUntil

`m-bitemp-write` requires plain bitemporal `terminate` in addition to the
bounded `terminateUntil` shape. `terminateUntil` removes an object only for an
authored business window, preserving head and tail business history. Plain
`terminate` removes the object from the effective business date through
infinity, preserving prior business history and the processing-axis audit trail.
It is a temporal terminate, not a physical purge of history.

The omission was a spec gap rather than a deliberate exclusion. Reladomo's dated
object surface exposes both `terminate()` and `terminateUntil(...)`, and its
bitemporal director implements both. Parallax follows that semantic split while
keeping the operation names explicit, consistent with ADR 0009.

The corpus must prove plain bitemporal terminate independently of inheritance.
Inheritance then composes that required bitemporal shape with concrete subtype
table/tag routing: a `table-per-hierarchy` concrete subtype terminate includes
the metadata-derived tag guard on existing-row inactivation/close statements,
while `table-per-concrete-subtype` terminates through the concrete subtype table.
