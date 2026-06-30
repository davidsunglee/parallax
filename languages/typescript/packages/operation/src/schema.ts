/**
 * ajv-backed validation of operation nodes against
 * `core/schemas/operation.schema.json` (Draft 2020-12 via `Ajv2020`).
 * Mirrors the validator seam in `@parallax/metamodel` / `@parallax/conformance`.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import addFormatsModule, { type FormatsPlugin } from "ajv-formats";

const addFormats = ((addFormatsModule as unknown as { default?: FormatsPlugin }).default ??
  (addFormatsModule as unknown as FormatsPlugin)) as FormatsPlugin;

/** Resolve `core/schemas/operation.schema.json` from this module's location. */
function resolveSchemaPath(): string {
  const here = fileURLToPath(import.meta.url);
  const repoRoot = fileURLToPath(new URL("../../../../../", new URL(`file://${here}`)));
  return `${repoRoot}core/schemas/operation.schema.json`;
}

let cachedValidate: ValidateFunction | undefined;

/** Compile (once) and return the operation-node validator. */
export function operationValidator(): ValidateFunction {
  if (cachedValidate) {
    return cachedValidate;
  }
  const schema = JSON.parse(readFileSync(resolveSchemaPath(), "utf8")) as object;
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

/** Validate an operation node against the operation schema. */
export function validateOperation(operation: unknown): ValidationResult {
  const validate = operationValidator();
  const valid = validate(operation) as boolean;
  const errors = (validate.errors ?? []).map(
    (e) => `${e.instancePath || "/"} ${e.message ?? "is invalid"}`,
  );
  return { valid, errors };
}

/** Validate an operation, throwing with collected errors if it does not conform. */
export function assertValidOperation<T>(operation: T): T {
  const { valid, errors } = validateOperation(operation);
  if (!valid) {
    throw new Error(
      `operation does not validate against operation.schema.json:\n  ${errors.join("\n  ")}`,
    );
  }
  return operation;
}
