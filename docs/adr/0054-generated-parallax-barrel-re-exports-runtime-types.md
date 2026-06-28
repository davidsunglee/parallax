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
- generated enum and value-object types
- public runtime types, such as `ParallaxList`
- public error classes, such as `ParallaxError`, `ParallaxValidationError`, `ParallaxNotFoundError`, `ParallaxTooManyResultsError`, and `ParallaxOptimisticLockError`

TypeScript's value/type namespace overlap is accepted for generated entity names. Documentation may alias managed object types when clarity matters:

```ts
import { Order, type Order as OrderObject } from "#parallax";
```
