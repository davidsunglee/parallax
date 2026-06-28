# Generated Parallax barrel re-exports runtime types

The generated `#parallax` barrel is the normal application import surface. It exports the generated domain API and re-exports public runtime types and errors so application code does not need to import from both `#parallax` and `@parallax/typescript`.

The barrel exports:

- `parallax`
- `Parallax`
- `ParallaxTransaction`
- generated entity symbol values, such as `Order`
- managed object types, such as `type Order`
- entity input validators and types, such as `OrderInput` and `type OrderInput`
- snapshot types, such as `type OrderSnapshot`
- public runtime types, such as `ParallaxList`, `ParallaxDecimal`, and `ParallaxJsonValue`
- public error classes, such as `ParallaxError`, `ParallaxValidationError`, `ParallaxNotFoundError`, `ParallaxTooManyResultsError`, and `ParallaxOptimisticLockError`

TypeScript's value/type namespace overlap is accepted for generated entity names. Documentation may alias managed object types when clarity matters:

```ts
import { Order, type Order as OrderObject } from "#parallax";
```

The barrel does not export generated enum types or structured value-object
interfaces in V1. Those shapes are not present in the canonical core descriptor,
so applications use scalar string values for string-coded states and
`ParallaxJsonValue` for value objects until core adds schema for richer generated
types.
