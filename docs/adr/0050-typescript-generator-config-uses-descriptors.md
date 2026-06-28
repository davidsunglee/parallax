# TypeScript generator config uses descriptors

The TypeScript generator configuration names its canonical model inputs `descriptors`.

```ts
import { defineParallaxConfig } from "@parallax/typescript/config";

export default defineParallaxConfig({
  descriptors: ["./parallax/**/*.yaml"],
  output: "./.parallax/generated",
  importAlias: "#parallax",
});
```

`descriptors` matches the core language for YAML/JSON metamodel documents. The API avoids `specs`, which is reserved for normative core and language specifications, and avoids `models`, which is overloaded with generated entity/domain types.

The default `output` is `./.parallax/generated`, reflecting that generated code is gitignored derived output rather than user-owned source.
