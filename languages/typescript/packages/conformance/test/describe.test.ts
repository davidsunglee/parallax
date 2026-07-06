import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, describe as group, it } from "vitest";
import {
  describe as buildDescribe,
  SLICE_MVP_1_CAPABILITIES,
  TYPESCRIPT_ADAPTER,
  validateEnvelope,
} from "../src/index.js";

/**
 * Resolve a repo-root-relative path from this test file. The conformance
 * package sits at `languages/typescript/packages/conformance/test/`, so the
 * repo root is five directories up.
 */
function repoPath(relative: string): string {
  const repoRoot = fileURLToPath(new URL("../../../../../", import.meta.url));
  return `${repoRoot}${relative}`;
}

/**
 * Extract the embedded canonical `describe` JSON block from
 * `core/spec/slices.md` — the single source of truth for the slice.
 */
function canonicalSliceCapabilities(): unknown {
  const md = readFileSync(repoPath("core/spec/slices.md"), "utf8");
  const start = md.indexOf("First-implementation Conformance Slice");
  expect(start, "slice heading present in scope-and-tiers.md").toBeGreaterThan(-1);
  const fenceOpen = md.indexOf("```json", start);
  expect(fenceOpen, "json fence present after slice heading").toBeGreaterThan(-1);
  const bodyStart = fenceOpen + "```json".length;
  const fenceClose = md.indexOf("```", bodyStart);
  const block = md.slice(bodyStart, fenceClose).trim();
  const parsed = JSON.parse(block) as { capabilities: unknown };
  return parsed.capabilities;
}

group("describe", () => {
  it("emits the canonical claim with the TypeScript adapter identity", () => {
    const envelope = buildDescribe(TYPESCRIPT_ADAPTER);

    expect(envelope).toEqual({
      schemaVersion: "1",
      command: "describe",
      status: "ok",
      adapter: {
        language: "typescript",
        name: "@parallax/typescript",
        version: "0.1.0",
      },
      capabilities: SLICE_MVP_1_CAPABILITIES,
    });
  });

  it("claims exactly the canonical slice capabilities (anti-drift)", () => {
    // Only the adapter identity may differ from the reference claim; the
    // capabilities must match the embedded block byte-for-byte in meaning.
    expect(SLICE_MVP_1_CAPABILITIES).toEqual(canonicalSliceCapabilities());
  });

  it("validates against conformance-adapter.schema.json", () => {
    const envelope = buildDescribe(TYPESCRIPT_ADAPTER);
    const result = validateEnvelope(envelope);
    expect(result.errors).toEqual([]);
    expect(result.valid).toBe(true);
  });

  it("rejects a malformed envelope (negative control)", () => {
    const broken = { schemaVersion: "1", command: "describe", status: "ok" };
    expect(validateEnvelope(broken).valid).toBe(false);
  });
});
