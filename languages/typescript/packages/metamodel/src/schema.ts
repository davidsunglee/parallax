/**
 * ajv-backed validation of model descriptors against
 * `core/schemas/metamodel.schema.json`.
 *
 * The core schemas are Draft 2020-12, which ajv exposes through the `Ajv2020`
 * build (`ajv/dist/2020`); a default `Ajv` instance cannot validate 2020-12.
 * (Mirrors the validator seam in `@parallax/conformance`.)
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";

// Under NodeNext the ajv-formats default import surfaces as the namespace; the
// callable plugin is its `.default`, falling back to the namespace itself.
const addFormats = ((addFormatsModule as unknown as { default?: FormatsPlugin }).default ??
  (addFormatsModule as unknown as FormatsPlugin)) as FormatsPlugin;

/**
 * Resolve a `core/schemas/*.json` path from this module's location. From
 * `languages/typescript/packages/metamodel/{src,dist}/` the repo root is five
 * directories up.
 */
function resolveSchemaPath(name: string): string {
  const here = fileURLToPath(import.meta.url);
  const repoRoot = fileURLToPath(new URL("../../../../../", new URL(`file://${here}`)));
  return `${repoRoot}core/schemas/${name}`;
}

let cachedValidate: ValidateFunction | undefined;

/** Compile (once) and return the metamodel-descriptor validator. */
export function metamodelValidator(): ValidateFunction {
  if (cachedValidate) {
    return cachedValidate;
  }
  const schema = JSON.parse(
    readFileSync(resolveSchemaPath("metamodel.schema.json"), "utf8"),
  ) as object;
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  cachedValidate = ajv.compile(schema);
  return cachedValidate;
}

/** Validation outcome with collected error messages. */
export interface ValidationResult {
  readonly valid: boolean;
  readonly errors: readonly string[];
}

/** Validate a descriptor against the metamodel schema. */
export function validateDescriptor(descriptor: unknown): ValidationResult {
  const validate = metamodelValidator();
  const valid = validate(descriptor) as boolean;
  const errors = (validate.errors ?? []).map(
    (e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`,
  );
  return { valid, errors };
}

/** Validate a descriptor, throwing with collected errors if it does not conform. */
export function assertValidDescriptor<T>(descriptor: T): T {
  const { valid, errors } = validateDescriptor(descriptor);
  if (!valid) {
    throw new Error(
      `descriptor does not validate against metamodel.schema.json:\n  ${errors.join("\n  ")}`,
    );
  }
  return descriptor;
}
