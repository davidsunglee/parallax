# TypeScript separates entity symbols from operation surfaces

Generated entity symbols such as `Order` are pure expression and metadata surfaces, while database work goes through explicit operation surfaces such as `px.orders` and `tx.orders`. This keeps predicate authoring autocomplete-friendly without relying on ambient sessions, and it leaves room for multiple databases, transaction scoping, test isolation, and future source or tenant routing.

The generated API accepts TypeScript's value/type namespace overlap for ergonomics: `Order` is the entity symbol value used for predicates and paths, and `type Order` is also the managed domain object type. Documentation may alias the managed object type when clarity matters, but everyday code should not have to write noisier names such as `OrderEntity.status.eq(...)`.
