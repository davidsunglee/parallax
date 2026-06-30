import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { assertRoundTrip, canonical, canonicallyEqual, deserialize } from "@parallax/serde";
import { expect, describe as group, it } from "vitest";
import { operationTag, parseOperation, validateOperation } from "../src/index.js";

/**
 * Resolve a repo-root-relative path from this test file. The operation package
 * sits at `languages/typescript/packages/operation/test/`, so the repo root is
 * five directories up.
 */
function repoPath(relative: string): string {
  const repoRoot = fileURLToPath(new URL("../../../../../", import.meta.url));
  return `${repoRoot}${relative}`;
}

const CASES_DIR = repoPath("core/compatibility/cases");

interface CaseDoc {
  readonly tags?: readonly string[];
  readonly operation?: unknown;
  readonly equivalentEncodings?: readonly unknown[];
}

/** Parse a case YAML from disk. */
function loadCase(name: string): CaseDoc {
  const text = readFileSync(`${CASES_DIR}/${name}`, "utf8");
  return deserialize(text, "yaml") as CaseDoc;
}

/**
 * The `first-implementation-mvp` cases that carry an `operation` (the read
 * shape) from the 0001 / 0002 / 02xx families — exactly the operations the
 * compile path will consume.
 */
function claimedReadCases(): readonly { name: string; doc: CaseDoc }[] {
  return readdirSync(CASES_DIR)
    .filter((name) => /^(0001|0002|02\d\d)-.*\.ya?ml$/.test(name))
    .sort()
    .map((name) => ({ name, doc: loadCase(name) }))
    .filter(
      ({ doc }) =>
        doc.operation !== undefined && (doc.tags ?? []).includes("first-implementation-mvp"),
    );
}

const READ_CASES = claimedReadCases();

group("operation round-trip", () => {
  it("discovers the claimed 0001/0002/02xx read operations", () => {
    // Sanity: the corpus carries the families we expect (find-all, eq, and the
    // 02xx single-entity algebra).
    expect(READ_CASES.length).toBeGreaterThanOrEqual(20);
  });

  it.each(
    READ_CASES.map((c) => c.name),
  )("%s operation validates against operation.schema.json", (name) => {
    const { operation } = loadCase(name);
    const { valid, errors } = validateOperation(operation);
    expect(errors).toEqual([]);
    expect(valid).toBe(true);
  });

  it.each(
    READ_CASES.map((c) => c.name),
  )("%s operation parses to a single-key tagged node", (name) => {
    const { operation } = loadCase(name);
    const parsed = parseOperation(operation);
    // Every node is a single-key tagged object; the tag is recoverable.
    expect(typeof operationTag(parsed)).toBe("string");
  });

  it.each(
    READ_CASES.map((c) => c.name),
  )("%s operation round-trips losslessly through JSON and YAML", (name) => {
    const { operation } = loadCase(name);
    expect(() => assertRoundTrip(operation)).not.toThrow();
  });
});

group("0222 equivalentEncodings collapse to the canonical operation", () => {
  const NAME = "0222-group-precedence-grouped.yaml";

  it("the case carries a prefix and a fluent equivalent encoding", () => {
    const doc = loadCase(NAME);
    expect(doc.operation).toBeDefined();
    expect(doc.equivalentEncodings).toBeDefined();
    expect(doc.equivalentEncodings?.length).toBe(2);
  });

  it("every equivalent encoding canonicalizes to the case operation", () => {
    const doc = loadCase(NAME);
    const canonicalOp = canonical(doc.operation);
    for (const encoding of doc.equivalentEncodings ?? []) {
      // The prefix / fluent surfaces differ only in object-key authoring order;
      // recursive key-sort canonicalization must collapse both to `operation`.
      expect(canonicallyEqual(encoding, doc.operation)).toBe(true);
      expect(canonical(encoding)).toEqual(canonicalOp);
    }
  });

  it("a genuinely different tree is NOT an equivalent encoding (negative control)", () => {
    const doc = loadCase(NAME);
    // Drop the `group` node — precedence is carried, not erased, so this must
    // not canonicalize to the grouped operation.
    const ungrouped = {
      and: {
        operands: [
          {
            or: {
              operands: [
                { greaterThanEquals: { attr: "Order.qty", value: 25 } },
                { lessThanEquals: { attr: "Order.qty", value: 5 } },
              ],
            },
          },
          { eq: { attr: "Order.active", value: true } },
        ],
      },
    };
    expect(canonicallyEqual(ungrouped, doc.operation)).toBe(false);
  });
});
