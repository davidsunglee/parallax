/**
 * Value-object materialization for the m-conformance-adapter run lane
 * (m-value-object, "Materialization and navigation contract").
 *
 * A value-object read projects the owning entity's ONE structured-document column
 * with the owner in a single round trip — there is no child fetch. This module
 * decodes that column and projects it to the DECLARED value-object shape the typed
 * getters expose: only declared members appear (undeclared JSON keys drop), every
 * declared member is always present (null where the document does not supply it),
 * and the absence states collapse exactly as the read predicates do (resolved
 * Q5): a null / missing / JSON-null / non-object `one` member materializes as
 * `null`, and a null / missing / non-array `many` member materializes as `[]`.
 *
 * It is the TypeScript mirror of the reference harness's `_decode_document` /
 * `_project_value_object` / `_materialize_owner_node`.
 */
import type { Row } from "@parallax/core";
import type { EntityMetadata, NormalizedValueObjectMember } from "@parallax/operation";

/** A non-null, non-array plain object. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * Decode a structured-document column value to a plain JS structure. Postgres
 * returns its `jsonb` column already parsed (an object / array); MariaDB returns
 * its `json` column as raw JSON text (a string, or bytes) that needs parsing.
 * Both collapse to the same structure here; a SQL-NULL column is `null`.
 */
export function decodeDocument(raw: unknown): unknown {
  if (raw === null || raw === undefined) {
    return null;
  }
  if (raw instanceof Uint8Array) {
    return decodeDocument(new TextDecoder().decode(raw));
  }
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  }
  return raw;
}

/**
 * Project a decoded document slot to its declared value-object shape. A `one`
 * member is a nested object when the slot is a JSON object, else `null`; a `many`
 * member is the collection of its element projections when the slot is a JSON
 * array, else `[]`. Element order within a `many` member is semantic and is
 * preserved exactly from the authored/wire document.
 */
export function projectValueObject(vo: NormalizedValueObjectMember, decoded: unknown): unknown {
  if (vo.multiplicity === "many") {
    return Array.isArray(decoded) ? decoded.map((element) => projectMembers(vo, element)) : [];
  }
  return isPlainObject(decoded) ? projectMembers(vo, decoded) : null;
}

/**
 * Build the declared-member projection of one value-object document object. Each
 * declared attribute contributes its leaf value (`null` for a missing key or a
 * JSON `null`); each declared nested value object recurses. A non-object element
 * yields all-null declared members. Undeclared keys are omitted, so the node's
 * key set is exactly the declared members — the shape the typed getters expose.
 */
function projectMembers(vo: NormalizedValueObjectMember, obj: unknown): Record<string, unknown> {
  const source = isPlainObject(obj) ? obj : {};
  const node: Record<string, unknown> = {};
  for (const attribute of vo.attributes) {
    node[attribute.name] = source[attribute.name] ?? null;
  }
  for (const nested of vo.valueObjects) {
    node[nested.name] = projectValueObject(nested, source[nested.name]);
  }
  return node;
}

/**
 * A read row with its top-level value-object columns decoded + projected. Scalar
 * columns pass through under their result-column name; each declared top-level
 * value object's document column is decoded and replaced by its declared
 * projection, keyed by the value-object name. A value-object column the golden
 * SELECT did not project is left untouched (no synthetic null).
 */
export function materializeOwnerNode(entity: EntityMetadata, row: Row): Row {
  const node: Record<string, unknown> = { ...row };
  for (const vo of entity.valueObjects()) {
    if (!(vo.column in node)) {
      continue;
    }
    const decoded = decodeDocument(node[vo.column]);
    delete node[vo.column];
    node[vo.name] = projectValueObject(vo, decoded);
  }
  return node as Row;
}

/** Decode every top-level value-object document column of a table-state read row. */
export function decodeTableStateRow(entity: EntityMetadata, row: Row): Row {
  const node: Record<string, unknown> = { ...row };
  for (const vo of entity.valueObjects()) {
    if (vo.column in node) {
      node[vo.column] = decodeDocument(node[vo.column]);
    }
  }
  return node as Row;
}
