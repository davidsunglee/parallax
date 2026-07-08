/**
 * A **raw-JSON sentinel** — a pre-serialized JSON string the adapter's `json` /
 * `jsonb` bind serializer must emit VERBATIM instead of JSON-encoding it
 * (m-value-object / m-core json).
 *
 * The json bind serializer is **fail-safe by default**: it `JSON.stringify`s every
 * bare bind value, so an ordinary `json` write scalar `"hello"` lands as the jsonb
 * string `"hello"` (never the raw, invalid-JSON text `hello`), and a number /
 * boolean / object / array lands as its jsonb form. Exactly one bind must ESCAPE
 * that default — the value-object to-many read's empty-array GUARD literal `'[]'`,
 * cast to jsonb (`cast(? as jsonb)`): re-encoding it to the jsonb string scalar
 * `"[]"` would make `jsonb_array_elements` reject it ("cannot extract elements from a
 * scalar"). The dialect binds that guard literal wrapped in this sentinel so it
 * passes through raw; every other json bind takes the safe default. Inverting the
 * marker this way (default = encode, sentinel = raw) makes a direct `@parallax/
 * db-postgres` use or a missed provider path SAFE by default, rather than silently
 * sending invalid raw text.
 *
 * The sentinel is an in-memory marker only. The frozen conformance schema and the
 * hand-authored goldens carry the plain string `"[]"`, and a `RawJson` instance
 * JSON-serializes to `{}` (its brand is a Symbol-keyed property), so
 * {@link canonicalBind} collapses the sentinel back to its inner JSON string
 * wherever a compiled bind is REPORTED into an envelope or COMPARED to a golden. The
 * marker is branded with a well-known symbol (not `instanceof`) so the guard is
 * robust across a duplicated package copy.
 */
const RAW_JSON = Symbol.for("@parallax/dialect:raw-json");

/** A pre-serialized JSON string the json bind serializer emits verbatim. */
export class RawJson {
  /** The brand the {@link isRawJson} guard tests (package-copy safe). */
  readonly [RAW_JSON] = true;

  constructor(
    /** The already-canonical JSON text bound verbatim (e.g. the array literal `[]`). */
    readonly json: string,
  ) {}
}

/** Wrap a pre-serialized JSON string so the adapter binds it verbatim (no re-encoding). */
export function rawJson(json: string): RawJson {
  return new RawJson(json);
}

/** Whether `value` is a {@link RawJson} sentinel (brand check, not `instanceof`). */
export function isRawJson(value: unknown): value is RawJson {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<symbol, unknown>)[RAW_JSON] === true
  );
}

/**
 * Canonicalize one compiled bind for REPORTING / golden comparison: a {@link RawJson}
 * sentinel collapses to its inner JSON string (the scalar the frozen schema and the
 * goldens carry); every other bind passes through unchanged. This is the single
 * shared `rawJson → its string` canonicalizer applied wherever a `compile()`-output
 * bind is serialized into an envelope or compared to a golden.
 */
export function canonicalBind(bind: unknown): unknown {
  return isRawJson(bind) ? bind.json : bind;
}

/** Canonicalize a compiled bind list (element-wise {@link canonicalBind}). */
export function canonicalBinds(binds: readonly unknown[]): unknown[] {
  return binds.map(canonicalBind);
}
