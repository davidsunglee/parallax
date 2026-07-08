/**
 * Pure unit tests for the `json` / `jsonb` bind serializer (`serializeJson`) — the
 * fail-safe-by-default fix (Docker-free).
 *
 * `serializeJson` is the serializer porsager runs for a parameter bound to a
 * `json`/`jsonb` column (routed by the server-described column OID, so it runs for
 * every JS shape at that position). It is **safe by default**: it JSON-encodes every
 * bare value, so no bind can reach the wire as invalid raw text. Exactly one shape
 * escapes that default — a {@link rawJson} sentinel (the value-object to-many read's
 * empty-array guard `'[]'`), which passes through VERBATIM. The regression this pins:
 * an ordinary json string scalar `"hello"` must be ENCODED to the jsonb string
 * `"hello"` (never bound as the raw, invalid-JSON text `hello`), WHILE the sentinel-
 * wrapped guard `'[]'` still passes raw so `jsonb_array_elements` accepts it.
 */
import { rawJson } from "@parallax/dialect";
import { describe, expect, it } from "vitest";
import { serializeJson } from "../src/oids.js";

describe("serializeJson — a bare value is JSON-ENCODED by default (fail-safe)", () => {
  it("encodes a string scalar to quoted JSON (the missed-path fix)", () => {
    // The bug: an ordinary json string "hello" was bound as the raw text `hello`
    // (invalid JSON, rejected by Postgres). The safe default now encodes it to the
    // jsonb string `"hello"` — even a DIRECT adapter bind (no marker) is safe.
    expect(serializeJson("hello")).toBe('"hello"');
  });

  it("encodes number / boolean / object / array values", () => {
    expect(serializeJson(42)).toBe("42");
    expect(serializeJson(true)).toBe("true");
    expect(serializeJson({ a: 1, b: "x" })).toBe('{"a":1,"b":"x"}');
    expect(serializeJson([1, 2, 3])).toBe("[1,2,3]");
  });

  it("stringifies a value-object document bound atomically", () => {
    expect(serializeJson({ street: "12 Aurora Ave", city: "Tromso" })).toBe(
      '{"street":"12 Aurora Ave","city":"Tromso"}',
    );
    expect(serializeJson([{ type: "home" }, { type: "work" }])).toBe(
      '[{"type":"home"},{"type":"work"}]',
    );
  });

  it("encodes a string that LOOKS like the guard — only the sentinel escapes the default", () => {
    // A written json value that happens to be the text "[]" is a jsonb STRING scalar
    // `"[]"`, NOT an empty array. Without the sentinel it takes the safe (encoding)
    // default, so a bare "[]" is quoted — the sentinel (below), not the content, decides.
    expect(serializeJson("[]")).toBe('"[]"');
  });
});

describe("serializeJson — a rawJson sentinel passes through RAW (already-JSON-text)", () => {
  it("returns the guard literal '[]' verbatim (the read-side array guard)", () => {
    // cast(? as jsonb) binds rawJson('[]'); re-encoding it to the jsonb string scalar
    // `"[]"` would make jsonb_array_elements reject it. It must stay the canonical array text.
    expect(serializeJson(rawJson("[]"))).toBe("[]");
    expect(serializeJson(rawJson('{"already":"json"}'))).toBe('{"already":"json"}');
  });
});

describe("serializeJson — null / undefined bind as SQL NULL", () => {
  it("passes null / undefined through unchanged", () => {
    expect(serializeJson(null)).toBeNull();
    expect(serializeJson(undefined)).toBeUndefined();
  });
});
