# Entity symbols provide all and none predicates

Generated TypeScript entity symbols expose `all()` and `none()` constructors for identity predicates, and `find()` without a predicate is shorthand for `find(Entity.all())`. Keeping these on the entity symbol makes dynamic predicate construction explicit without adding global helpers.
