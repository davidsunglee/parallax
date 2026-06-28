# Find returns result collections

Core `find` operations return a result collection rather than special-casing zero, one, or many matches. This keeps query semantics uniform and lets each language decide the idiomatic collection API.
