# Table-per-hierarchy shared table mapping is root-owned

Under table-per-hierarchy, the Abstract Root Type declares the inheritance
family's one shared `table` mapping while remaining non-instantiable and
rowless. Concrete subtypes inherit that physical mapping and do not repeat a
`table` property. This treats the table as the family-level fact it is, removes
duplicated truth and the corresponding same-table invariant, and keeps `table`
in the same top-level metadata position used by ordinary entities and
table-per-concrete-subtype concrete subtypes.

This ownership is specific to the mapping strategy. A table-per-concrete-
subtype root and its abstract subtypes declare no table mapping; each concrete
subtype declares its own. In canonical descriptors and language frontends,
therefore, `table` appears on an ordinary entity, on a table-per-hierarchy
Abstract Root, or on a table-per-concrete-subtype Concrete Subtype—never nested
inside the inheritance block and never repeated across one table-per-hierarchy
family.
