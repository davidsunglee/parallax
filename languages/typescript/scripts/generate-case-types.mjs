/**
 * Generate the static TypeScript view of the compatibility-case format from the
 * canonical JSON Schema (`core/schemas/compatibility-case.schema.json`), the single
 * source of truth the `@parallax/conformance` loader validates against at load.
 *
 * The output — `packages/conformance/src/case-format.generated.ts` — is checked in
 * and kept fresh by a regenerate + `git diff --exit-code` gate wired into
 * `ts:generate-case-types:check` (run by `just ts-lint` / CI). It replaces the
 * hand-written `Raw*` interfaces and inline `as` casts the loader once carried:
 * the schema is the only description of the case shape, and these types are derived
 * from it rather than mirrored by hand.
 *
 * A Zod schema built at runtime from the JSON file cannot drive `z.infer`, and the
 * loader validates with Ajv (reusing the `schema.ts` Ajv2020 compile pattern), so
 * the static types come from `json-schema-to-typescript` over the same schema.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

/** The repo root, resolved from this script (`languages/typescript/scripts/`). */
const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const schemaPath = `${repoRoot}core/schemas/compatibility-case.schema.json`;
const outPath = `${repoRoot}languages/typescript/packages/conformance/src/case-format.generated.ts`;

const schema = JSON.parse(readFileSync(schemaPath, "utf8"));

const banner = [
  "/**",
  " * GENERATED — do not edit by hand.",
  " *",
  " * The static TypeScript view of the compatibility-case format, derived from",
  " * `core/schemas/compatibility-case.schema.json` (the single source of truth the",
  " * `@parallax/conformance` loader validates each document against with Ajv). Run",
  " * `pnpm run ts:generate-case-types` to regenerate; CI enforces freshness with a",
  " * `git diff --exit-code` gate (`ts:generate-case-types:check`).",
  " */",
  "",
].join("\n");

const body = await compile(schema, "CaseDocument", {
  // The case schema `$ref`s sibling schemas by relative path (e.g.
  // `write-instruction.schema.json#/$defs/*`, m-unit-work's write-instruction
  // vocabulary); resolve them from `core/schemas/`, not the process CWD.
  cwd: `${repoRoot}core/schemas/`,
  bannerComment: "",
  additionalProperties: false,
  declareExternallyReferenced: true,
  enableConstEnums: false,
  style: {
    // Match the repo's Biome formatting so the checked-in artifact is diff-stable.
    semi: true,
    singleQuote: false,
    trailingComma: "all",
    printWidth: 100,
  },
});

writeFileSync(outPath, `${banner}${body}`);
