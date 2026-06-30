/**
 * ajv-backed validation of adapter envelopes against
 * `core/schemas/conformance-adapter.schema.json`.
 *
 * The core schemas are Draft 2020-12, which ajv exposes through the `Ajv2020`
 * build (`ajv/dist/2020`); a default `Ajv` instance cannot validate 2020-12.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
// ajv 8 ships the `Ajv2020` class as a CommonJS named export; ajv-formats ships
// its plugin as the CommonJS default. Both are resolved as CJS under NodeNext.
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";

// Under NodeNext the ajv-formats default import surfaces as the namespace; the
// callable plugin is its `.default`, falling back to the namespace itself.
const addFormats = ((addFormatsModule as unknown as { default?: FormatsPlugin }).default ??
  (addFormatsModule as unknown as FormatsPlugin)) as FormatsPlugin;

/**
 * Resolve `core/schemas/conformance-adapter.schema.json` from this module's
 * location. From `languages/typescript/packages/conformance/{src,dist}/` the
 * repo root is five directories up.
 */
function resolveSchemaPath(): string {
  const here = fileURLToPath(import.meta.url);
  const repoRoot = fileURLToPath(new URL("../../../../../", new URL(`file://${here}`)));
  return `${repoRoot}core/schemas/conformance-adapter.schema.json`;
}

let cachedValidate: ValidateFunction | undefined;

/** Compile (once) and return the adapter-envelope validator. */
export function conformanceAdapterValidator(): ValidateFunction {
  if (cachedValidate) {
    return cachedValidate;
  }
  const schema = JSON.parse(readFileSync(resolveSchemaPath(), "utf8")) as object;
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  const validate = ajv.compile(schema);
  cachedValidate = validate;
  return validate;
}

/** Validation outcome with collected error messages. */
export interface ValidationResult {
  readonly valid: boolean;
  readonly errors: readonly string[];
}

/** Validate an adapter envelope against the conformance-adapter schema. */
export function validateEnvelope(envelope: unknown): ValidationResult {
  const validate = conformanceAdapterValidator();
  const valid = validate(envelope) as boolean;
  const errors = (validate.errors ?? []).map(
    (e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`,
  );
  return { valid, errors };
}

/**
 * Validate an envelope, throwing with the collected ajv errors if it does not
 * conform. Returns the envelope unchanged for fluent use.
 */
export function assertValidEnvelope<T>(envelope: T): T {
  const { valid, errors } = validateEnvelope(envelope);
  if (!valid) {
    throw new Error(
      `envelope does not validate against conformance-adapter.schema.json:\n  ${errors.join("\n  ")}`,
    );
  }
  return envelope;
}
