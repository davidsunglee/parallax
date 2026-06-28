# ParallaxList is an async iterable

`ParallaxList` implements JavaScript async iteration and resolves its backing operation on first async access, materializing a stable in-memory result for subsequent iteration and helper methods. It exposes explicit async helpers `toArray`, `first`, `firstOrNull`, `single`, `singleOrNull`, `count`, `isEmpty`, and `notEmpty`; it does not emulate arrays, so `length`, numeric indexing, and synchronous iteration are left to normal TypeScript and JavaScript behavior rather than being trapped with proxies or custom runtime errors.

`count`, `isEmpty`, and `notEmpty` may use optimized SQL when the list is unresolved and do not mark the list resolved; once a list is resolved, they answer from the stable in-memory result. Object-returning helpers such as `first`, `firstOrNull`, `single`, and `singleOrNull` resolve the list so their returned object remains consistent with later iteration of the same list.

`first` throws `ParallaxNotFoundError` when the list is empty. `single` throws `ParallaxNotFoundError` when empty and `ParallaxTooManyResultsError` when more than one object exists. The `OrNull` variants return `null` for empty lists and still throw `ParallaxTooManyResultsError` for multiple results.
