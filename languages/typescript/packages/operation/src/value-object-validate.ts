/**
 * Model-aware value-object validation for the `rejected` case shape
 * (m-value-object / m-op-algebra, resolved Q7) — the TypeScript mirror of the
 * reference harness's `op_validate` / `write_validate` / `value_object_resolve`.
 *
 * A `rejected` case carries a SCHEMA-VALID input a model-aware validator MUST
 * refuse **before any SQL is emitted**, naming the violated normative rule in
 * `then.rejectedRule`. This module walks an operation tree / a write row against
 * the queried entity's DECLARED recursive value-object structure and throws a
 * {@link RejectionError} carrying the rule id — the same refusal every language
 * implementation must make, not merely grading machinery.
 *
 * Scope (mirrors the harness): value-object rules are enforced at ANY depth within
 * the queried entity's OWN operation tree — the walk descends the same-entity
 * boolean combinators (`and` / `or` / `not` / `group`) and the directive / temporal
 * wrappers — but NOT into a related-entity navigation sub-operation (a tracked
 * future extension; no corpus case exercises it, and value objects are never
 * navigation targets).
 */
import type { EntityMetadata, NormalizedValueObjectMember } from "@parallax/metamodel";

// --- rule vocabulary (lockstep with core/schemas/compatibility-case.schema.json) ---

/** The closed set of `then.rejectedRule` identifiers a model-aware validator emits. */
export const RejectedRule = {
  /** A nested path's first segment names no declared value object on the queried entity. */
  NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT: "nested-path-first-segment-not-value-object",
  /** An intermediate names no nested value object, or a leaf names no attribute. */
  NESTED_PATH_UNKNOWN_MEMBER: "nested-path-unknown-member",
  /** A nested comparison / membership literal mismatches the leaf attribute's declared type. */
  NESTED_LITERAL_TYPE_MISMATCH: "nested-literal-type-mismatch",
  /** A `deepFetch` path segment names a value object. */
  DEEP_FETCH_VALUE_OBJECT_SEGMENT: "deep-fetch-value-object-segment",
  /** A `navigate` / `exists` / `notExists` targets a value object. */
  NAVIGATE_VALUE_OBJECT_TARGET: "navigate-value-object-target",
  /** A `find()` is rooted at a value object (an attr reference whose class is a value object). */
  FIND_ROOT_VALUE_OBJECT: "find-root-value-object",
  /** A required (`nullable:false`) attribute is absent (or null) at some depth. */
  WRITE_REQUIRED_ATTRIBUTE_MISSING: "write-required-attribute-missing",
  /** A required nested value object is absent (or null); a required `many` array is absent. */
  WRITE_REQUIRED_VALUE_OBJECT_MISSING: "write-required-value-object-missing",
  /** A document field value's type differs from the declared attribute's neutral type. */
  WRITE_VALUE_TYPE_MISMATCH: "write-value-type-mismatch",
} as const;

/** A `then.rejectedRule` identifier. */
export type RejectedRuleId = (typeof RejectedRule)[keyof typeof RejectedRule];

/**
 * A model-aware validator refused an input pre-SQL; `rule` names the violated
 * normative rule (asserted equal to the case's `then.rejectedRule`).
 */
export class RejectionError extends Error {
  readonly rule: RejectedRuleId;
  constructor(rule: RejectedRuleId, detail: string) {
    super(`${rule}: ${detail}`);
    this.name = "RejectionError";
    this.rule = rule;
  }
}

// --- typed-literal checking -------------------------------------------------

const STRING_TYPES = new Set(["string", "text", "char", "varchar", "uuid"]);
const TEMPORAL_TYPES = new Set(["timestamp", "date", "time", "datetime"]);
const INT_TYPES = new Set(["int8", "int16", "int32", "int64", "int", "integer"]);
const FLOAT_TYPES = new Set(["float32", "float64", "float", "double", "decimal", "numeric"]);
const BOOL_TYPES = new Set(["boolean", "bool"]);

/**
 * Whether a literal / document value is compatible with a declared neutral type.
 * A `null` is always acceptable (nullability is a SEPARATE check), and an UNKNOWN
 * neutral type is accepted rather than guessed — the validator never false-rejects
 * a type it does not model (mirrors the harness's `literal_matches_type`).
 */
export function literalMatchesType(value: unknown, neutralType: string | undefined): boolean {
  if (value === null || value === undefined) {
    return true;
  }
  const kind = (neutralType ?? "").toLowerCase();
  if (STRING_TYPES.has(kind) || TEMPORAL_TYPES.has(kind)) {
    return typeof value === "string";
  }
  if (INT_TYPES.has(kind)) {
    return typeof value === "number" && Number.isInteger(value);
  }
  if (FLOAT_TYPES.has(kind)) {
    return typeof value === "number";
  }
  if (BOOL_TYPES.has(kind)) {
    return typeof value === "boolean";
  }
  return true;
}

// --- declared-structure lookups & path resolution ---------------------------

/** The single tag key of a one-key tagged node, or `undefined` for any other shape. */
function tagOf(node: unknown): string | undefined {
  if (node === null || typeof node !== "object" || Array.isArray(node)) {
    return undefined;
  }
  const keys = Object.keys(node as Record<string, unknown>);
  return keys.length === 1 ? keys[0] : undefined;
}

/** A nested value object declared inside `member`, or `undefined`. */
function findNested(
  member: NormalizedValueObjectMember,
  name: string,
): NormalizedValueObjectMember | undefined {
  return member.valueObjects.find((vo) => vo.name === name);
}

/** A typed attribute declared on `member`, or `undefined`. */
function findAttribute(member: NormalizedValueObjectMember, name: string) {
  return member.attributes.find((attr) => attr.name === name);
}

/**
 * Resolve a `Class.valueObject.field(.field)*` path to its LEAF attribute, raising
 * on the first undeclared segment: the first segment must name a declared value
 * object, each intermediate a nested value object, and the leaf an attribute.
 */
function resolveNestedRef(entity: EntityMetadata, path: string): { readonly type: string } {
  const [, first, ...rest] = path.split(".");
  const top = first === undefined ? undefined : entity.findValueObject(first);
  if (top === undefined) {
    throw new RejectionError(
      RejectedRule.NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
      `${path}: '${String(first)}' is not a value object declared on ${entity.name}`,
    );
  }
  const leaf = rest[rest.length - 1] as string;
  const intermediates = rest.slice(0, -1);
  let current: NormalizedValueObjectMember = top;
  for (const segment of intermediates) {
    const nested = findNested(current, segment);
    if (nested === undefined) {
      throw new RejectionError(
        RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
        `${path}: '${segment}' is not a nested value object of '${current.name}'`,
      );
    }
    current = nested;
  }
  const attribute = findAttribute(current, leaf);
  if (attribute === undefined) {
    throw new RejectionError(
      RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
      `${path}: '${leaf}' is not an attribute of '${current.name}'`,
    );
  }
  return attribute;
}

/**
 * Resolve a `Class.valueObject(.valueObject)*` path to its TERMINAL value object
 * (a `nestedExists` / `nestedNotExists` path ends at a value object, not an
 * attribute). Raises on the first undeclared segment.
 */
function resolveValueObjectRef(entity: EntityMetadata, path: string): NormalizedValueObjectMember {
  const [, first, ...rest] = path.split(".");
  const top = first === undefined ? undefined : entity.findValueObject(first);
  if (top === undefined) {
    throw new RejectionError(
      RejectedRule.NESTED_PATH_FIRST_SEGMENT_NOT_VALUE_OBJECT,
      `${path}: '${String(first)}' is not a value object declared on ${entity.name}`,
    );
  }
  let current: NormalizedValueObjectMember = top;
  for (const segment of rest) {
    const nested = findNested(current, segment);
    if (nested === undefined) {
      throw new RejectionError(
        RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
        `${path}: '${segment}' is not a nested value object of '${current.name}'`,
      );
    }
    current = nested;
  }
  return current;
}

/** Resolve an ELEMENT-RELATIVE path (no `Class.valueObject` prefix) to its leaf attribute. */
function resolveElementRef(
  valueObject: NormalizedValueObjectMember,
  path: string,
): { readonly type: string } {
  const segments = path.split(".");
  const leaf = segments[segments.length - 1] as string;
  const intermediates = segments.slice(0, -1);
  let current = valueObject;
  for (const segment of intermediates) {
    const nested = findNested(current, segment);
    if (nested === undefined) {
      throw new RejectionError(
        RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
        `element path ${path}: '${segment}' is not a nested value object of '${current.name}'`,
      );
    }
    current = nested;
  }
  const attribute = findAttribute(current, leaf);
  if (attribute === undefined) {
    throw new RejectionError(
      RejectedRule.NESTED_PATH_UNKNOWN_MEMBER,
      `element path ${path}: '${leaf}' is not an attribute of '${current.name}'`,
    );
  }
  return attribute;
}

// --- operation validation ---------------------------------------------------

const NESTED_COMPARISON_TAGS = new Set([
  "nestedEq",
  "nestedNotEq",
  "nestedGt",
  "nestedGte",
  "nestedLt",
  "nestedLte",
]);
const ATTR_TAGS = new Set([
  "eq",
  "notEq",
  "greaterThan",
  "greaterThanEquals",
  "lessThan",
  "lessThanEquals",
  "isNull",
  "isNotNull",
  "like",
  "notLike",
  "startsWith",
  "endsWith",
  "contains",
  "in",
  "notIn",
  "between",
]);

/**
 * Reject `operation` pre-SQL if it misuses a value object, else return quietly.
 * Throws a {@link RejectionError} (`.rule` one of the operation rules) on the first
 * violation. Used ONLY for `rejected` cases, so it need not fully validate every
 * valid operation — only refuse the negatives the corpus pins.
 */
export function validateOperationValueObjects(entity: EntityMetadata, operation: unknown): void {
  walkOperation(entity, operation);
}

function walkOperation(entity: EntityMetadata, node: unknown): void {
  const tag = tagOf(node);
  if (tag === undefined) {
    return;
  }
  const body = (node as Record<string, unknown>)[tag] as Record<string, unknown>;
  if (NESTED_COMPARISON_TAGS.has(tag)) {
    checkNestedComparison(entity, body);
  } else if (tag === "nestedIn") {
    checkNestedMembership(entity, body);
  } else if (tag === "nestedIsNull" || tag === "nestedIsNotNull") {
    resolveNestedRef(entity, String(body.path));
  } else if (tag === "nestedExists" || tag === "nestedNotExists") {
    checkNestedExists(entity, body);
  } else if (tag === "navigate" || tag === "exists" || tag === "notExists") {
    checkNavigation(entity, body);
  } else if (tag === "deepFetch") {
    checkDeepFetch(entity, body);
    walkOperation(entity, body.operand);
  } else if (ATTR_TAGS.has(tag)) {
    checkFindRoot(entity, body.attr);
  } else if (tag === "and" || tag === "or") {
    for (const operand of (body.operands as unknown[] | undefined) ?? []) {
      walkOperation(entity, operand);
    }
  } else if (tag === "not" || tag === "group" || tag === "distinct") {
    walkOperation(entity, body.operand);
  } else if (tag === "orderBy") {
    walkOperation(entity, body.operand);
    for (const key of (body.keys as Record<string, unknown>[] | undefined) ?? []) {
      checkFindRoot(entity, key.attr);
    }
  } else if (tag === "limit") {
    walkOperation(entity, body.operand);
  } else if (tag === "asOf" || tag === "asOfRange" || tag === "history") {
    walkOperation(entity, body.operand);
  }
  // all / none / aggregation nodes carry no value-object reference to validate.
}

function checkNestedComparison(entity: EntityMetadata, body: Record<string, unknown>): void {
  const attribute = resolveNestedRef(entity, String(body.path));
  if (!literalMatchesType(body.value, attribute.type)) {
    throw new RejectionError(
      RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
      `${String(body.path)}: literal ${JSON.stringify(body.value)} does not match declared type '${attribute.type}'`,
    );
  }
}

function checkNestedMembership(entity: EntityMetadata, body: Record<string, unknown>): void {
  const attribute = resolveNestedRef(entity, String(body.path));
  for (const value of (body.values as unknown[] | undefined) ?? []) {
    if (!literalMatchesType(value, attribute.type)) {
      throw new RejectionError(
        RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
        `${String(body.path)}: list literal ${JSON.stringify(value)} does not match declared type '${attribute.type}'`,
      );
    }
  }
}

function checkNestedExists(entity: EntityMetadata, body: Record<string, unknown>): void {
  const valueObject = resolveValueObjectRef(entity, String(body.path));
  if (body.where !== undefined) {
    walkElement(valueObject, body.where);
  }
}

function walkElement(valueObject: NormalizedValueObjectMember, node: unknown): void {
  const tag = tagOf(node);
  if (tag === undefined) {
    return;
  }
  const body = (node as Record<string, unknown>)[tag] as Record<string, unknown>;
  if (NESTED_COMPARISON_TAGS.has(tag)) {
    const attribute = resolveElementRef(valueObject, String(body.path));
    if (!literalMatchesType(body.value, attribute.type)) {
      throw new RejectionError(
        RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
        `element ${String(body.path)}: literal ${JSON.stringify(body.value)} does not match declared type '${attribute.type}'`,
      );
    }
  } else if (tag === "nestedIn") {
    const attribute = resolveElementRef(valueObject, String(body.path));
    for (const value of (body.values as unknown[] | undefined) ?? []) {
      if (!literalMatchesType(value, attribute.type)) {
        throw new RejectionError(
          RejectedRule.NESTED_LITERAL_TYPE_MISMATCH,
          `element ${String(body.path)}: list literal ${JSON.stringify(value)} does not match declared type '${attribute.type}'`,
        );
      }
    }
  } else if (tag === "nestedIsNull" || tag === "nestedIsNotNull") {
    resolveElementRef(valueObject, String(body.path));
  } else if (tag === "and" || tag === "or") {
    for (const operand of (body.operands as unknown[] | undefined) ?? []) {
      walkElement(valueObject, operand);
    }
  } else if (tag === "not" || tag === "group") {
    walkElement(valueObject, body.operand);
  }
}

function checkNavigation(entity: EntityMetadata, body: Record<string, unknown>): void {
  const rel = String(body.rel ?? "");
  const [cls, member] = rel.split(".");
  if (cls === entity.name && member !== undefined && entity.findValueObject(member) !== undefined) {
    throw new RejectionError(
      RejectedRule.NAVIGATE_VALUE_OBJECT_TARGET,
      `relationship navigation targets value object '${member}' on ${entity.name} — a value ` +
        `object has no identity to correlate and is never a navigation target`,
    );
  }
}

function checkDeepFetch(entity: EntityMetadata, body: Record<string, unknown>): void {
  // A path segment is a closed object `{ rel, narrow? }` (m-op-algebra); the
  // value-object misuse rule is about the traversed relationship ref.
  for (const path of (body.paths as { rel?: string }[][] | undefined) ?? []) {
    for (const segment of path) {
      const rel = segment?.rel ?? "";
      const [cls, member] = rel.split(".");
      if (
        cls === entity.name &&
        member !== undefined &&
        entity.findValueObject(member) !== undefined
      ) {
        throw new RejectionError(
          RejectedRule.DEEP_FETCH_VALUE_OBJECT_SEGMENT,
          `deepFetch path segment '${rel}' names value object '${member}' — a value-object ` +
            `segment is invalid in a deep-fetch path`,
        );
      }
    }
  }
}

function checkFindRoot(entity: EntityMetadata, attr: unknown): void {
  if (typeof attr !== "string") {
    return;
  }
  const cls = attr.split(".")[0] as string;
  if (entity.findValueObject(cls) !== undefined) {
    throw new RejectionError(
      RejectedRule.FIND_ROOT_VALUE_OBJECT,
      `attribute reference '${attr}' roots the query at value object '${cls}' — a value object ` +
        `is not a queryable root entity; query it through its owner`,
    );
  }
}

// --- write validation -------------------------------------------------------

/**
 * Reject a write `row` pre-SQL if a value-object document is structurally invalid
 * against its declared recursive structure, else return quietly. Throws a
 * {@link RejectionError} (`.rule` one of the write rules) on the first violation.
 * Scalar-attribute presence / typing is out of scope (a value object's write
 * validation is about the DOCUMENT), so a non-value-object key is ignored.
 */
export function validateWriteValueObjects(
  entity: EntityMetadata,
  row: Record<string, unknown>,
): void {
  // A required top-level value object omitted ENTIRELY from the row is a violation
  // (a present-but-null one is caught below via `validateMember`).
  for (const valueObject of entity.valueObjects()) {
    if (!valueObject.nullable && !(valueObject.name in row)) {
      throw new RejectionError(
        RejectedRule.WRITE_REQUIRED_VALUE_OBJECT_MISSING,
        `required value object '${valueObject.name}' is absent from the write input`,
      );
    }
  }
  for (const [key, value] of Object.entries(row)) {
    if (key === "observedVersion") {
      continue;
    }
    const valueObject = entity.findValueObject(key);
    if (valueObject === undefined) {
      continue;
    }
    validateMember(valueObject, value);
  }
}

/** Validate a value at a value-object member position against its declaration. */
function validateMember(valueObject: NormalizedValueObjectMember, value: unknown): void {
  if (value === null || value === undefined) {
    if (!valueObject.nullable) {
      throw new RejectionError(
        RejectedRule.WRITE_REQUIRED_VALUE_OBJECT_MISSING,
        `required value object '${valueObject.name}' (nullable:false) is absent or null`,
      );
    }
    return;
  }
  if (valueObject.multiplicity === "many") {
    // `nullable:false` requires the ARRAY be present (satisfied — value is not null
    // here); an empty array is fine. Validate each element as a document.
    if (Array.isArray(value)) {
      for (const element of value) {
        validateDocument(valueObject, element);
      }
    }
    return;
  }
  validateDocument(valueObject, value);
}

/** Validate one document (a `one` member / a `many` element) against its members. */
function validateDocument(valueObject: NormalizedValueObjectMember, document: unknown): void {
  if (document === null || typeof document !== "object" || Array.isArray(document)) {
    // A non-object where an object is expected is out of the negatives' scope (the
    // absence-collapse rule reads it as not-present at read time).
    return;
  }
  const record = document as Record<string, unknown>;
  for (const attribute of valueObject.attributes) {
    const present = attribute.name in record && record[attribute.name] !== null;
    if (!present) {
      if (!attribute.nullable) {
        throw new RejectionError(
          RejectedRule.WRITE_REQUIRED_ATTRIBUTE_MISSING,
          `required attribute ${valueObject.name}.${attribute.name} (nullable:false) is absent or null`,
        );
      }
      continue;
    }
    if (!literalMatchesType(record[attribute.name], attribute.type)) {
      throw new RejectionError(
        RejectedRule.WRITE_VALUE_TYPE_MISMATCH,
        `${valueObject.name}.${attribute.name} value ${JSON.stringify(record[attribute.name])} does not match declared type '${attribute.type}'`,
      );
    }
  }
  for (const nested of valueObject.valueObjects) {
    validateMember(nested, record[nested.name]);
  }
}
