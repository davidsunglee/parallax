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
  readonly tags?: readonly string[] | undefined;
  readonly operation?: unknown;
  readonly equivalentEncodings?: readonly unknown[] | undefined;
}

/**
 * The grouped case layout carries the action under test and its alternate
 * surface encodings under the `when` group.
 */
interface RawCaseDoc {
  readonly tags?: readonly string[];
  readonly when?: {
    readonly operation?: unknown;
    readonly equivalentEncodings?: readonly unknown[];
  };
}

/** Parse a case YAML from disk, projecting the `when` group into a flat view. */
function loadCase(name: string): CaseDoc {
  const text = readFileSync(`${CASES_DIR}/${name}`, "utf8");
  const raw = deserialize(text, "yaml") as RawCaseDoc;
  return {
    tags: raw.tags,
    operation: raw.when?.operation,
    equivalentEncodings: raw.when?.equivalentEncodings,
  };
}

/**
 * Every corpus case that carries an `operation` the compile path will consume:
 * the `slice-mvp-1` `m-op-algebra` read family PLUS the `m-value-object` family
 * (nested-predicate reads, temporal reads, and the schema-valid `rejected`
 * operations). The value-object cases are NOT yet `slice-mvp-1`-tagged — that
 * lands in Phase 11 — so they gate on the presence of an `operation` rather than
 * the slice tag; the write / rejected-write shapes carry no `operation` and drop
 * out naturally.
 */
function claimedReadCases(): readonly { name: string; doc: CaseDoc }[] {
  return readdirSync(CASES_DIR)
    .filter((name) => /^(m-op-algebra|m-value-object)-\d{3}-.*\.ya?ml$/.test(name))
    .sort()
    .map((name) => ({ name, doc: loadCase(name) }))
    .filter(({ name, doc }) => {
      if (doc.operation === undefined) {
        return false;
      }
      // m-value-object operations join the sweep on operation-presence alone
      // (Phase-11 slice tagging is still pending); m-op-algebra reads keep the
      // slice-mvp-1 gate.
      return name.startsWith("m-value-object-") || (doc.tags ?? []).includes("slice-mvp-1");
    });
}

const READ_CASES = claimedReadCases();

group("operation round-trip", () => {
  it("discovers the claimed m-op-algebra and m-value-object read operations", () => {
    // Sanity: the corpus carries the families we expect (find-all, eq, and the
    // single-entity algebra) AND the value-object nested-predicate family now
    // joins the serde round-trip sweep.
    expect(READ_CASES.length).toBeGreaterThanOrEqual(20);
    const valueObjectCases = READ_CASES.filter((c) => c.name.startsWith("m-value-object-"));
    expect(valueObjectCases.length).toBeGreaterThan(0);
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

group("m-op-algebra-024 equivalentEncodings collapse to the canonical operation", () => {
  const NAME = "m-op-algebra-024-group-precedence-grouped.yaml";

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
