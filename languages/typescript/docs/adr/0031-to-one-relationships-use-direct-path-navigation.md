# To-one relationships use direct path navigation

TypeScript predicates allow direct attribute path navigation through to-one relationships, while to-many relationships require an explicit quantifier such as `exists`. This keeps common to-one filters concise and autocomplete-friendly without hiding existential semantics for collection-valued relationships.
