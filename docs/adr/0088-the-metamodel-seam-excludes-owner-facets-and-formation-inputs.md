# The Metamodel seam excludes owner facets and formation inputs

The metamodel protocol seam is the `Metamodel` and `EntityMetadata`. Owner facets
stay as rules and vocabulary in the modules that own them, and each binding chooses
how a consumer reaches them. Their member lists, `FacetKey<T>`, and `Metamodel.facet`
are no longer portable requirements. The Unresolved boundary is likewise not a seam
for third-party frontends, so its exact input protocols give way to outcomes. This
narrows what [ADR 0030](0030-model-formation-is-explicitly-composed.md) fixed as
protocol. It leaves [ADR 0028](0028-behavioral-modules-depend-on-the-metamodel-interface.md)
standing: behavioral modules still depend on the Metamodel Interface.

Facets are derived views that no schema, case, or adapter output names. Three
readings of the same pattern had reached three different answers, and the lists had
drifted from the one binding they described. Treating them as a cross-binding seam
would have meant repairing them against Python and holding every language to its
accessors, with nothing able to grade the result. The rules consumers actually rely
on, such as how a position's Member Placement is found, stay stated.

`m-model-formation` keeps its manifest table, and so its `FacetKey` cells, because
the dependency check parses them, along with the composition mechanism ADR 0030
chose. How much of that mechanism a binding owes is deferred, because the answer
matters only once a second binding exists. Until then the module describes more than
the seam requires.

Python keeps `FacetKey`, `Metamodel.facet`, and its typed views as its own design.
Whether those names belong on its application-facing surface is a separate question.

*Superseded in part (2026-11, [Python ADR 0016](../../languages/python/docs/adr/0016-applications-spell-names-from-roots-and-vocabulary-modules.md)):*
Python's accepted Metamodel is a concrete first-party class without a `facet`
member; generic facet access is private behind each owner's typed accessor, and
none of these names is application API. The seam decision stands.
