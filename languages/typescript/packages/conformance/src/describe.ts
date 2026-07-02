/**
 * The canonical `describe` capability claim for the TypeScript adapter.
 *
 * TypeScript V1 *is* the canonical `slice-mvp-1` Conformance Slice
 * (`core/spec/scope-and-tiers.md`): the adapter reports exactly that slice's
 * capabilities and differs from the reference claim only in the `adapter`
 * identity. The slice is include-driven (`caseTags.include:
 * ["slice-mvp-1"]`), so V1 claims precisely the tagged cases and
 * returns `unsupported` for everything else.
 */
import type { AdapterIdentity, Capabilities, DescribeOk } from "@parallax/core";
import { SCHEMA_VERSION } from "@parallax/core";

/**
 * The canonical `slice-mvp-1` capabilities, verbatim from
 * `scope-and-tiers.md`. This object is the single source of truth for what the
 * TypeScript adapter claims; only the `adapter` identity is supplied per call.
 */
export const SLICE_MVP_1_CAPABILITIES: Capabilities = {
  modules: ["m0", "m1", "m2", "m3", "m4", "m5", "m7", "m8", "m10", "m11", "m12"],
  dialects: ["postgres"],
  caseShapes: ["read", "writeSequence", "scenario", "conflict"],
  caseTags: { include: ["slice-mvp-1"] },
  commands: ["describe", "compile", "run"],
  provisioning: "self-managed",
};

/** The TypeScript adapter identity carried by every envelope. */
export const TYPESCRIPT_ADAPTER: AdapterIdentity = {
  language: "typescript",
  name: "@parallax/typescript",
  version: "0.1.0",
};

/**
 * Build the canonical `describe` envelope for the given adapter identity.
 *
 * The returned document is the in-memory mirror of a `describeOk` envelope; the
 * caller serializes it as the single JSON document on stdout and exits `0`.
 */
export function describe(adapter: AdapterIdentity): DescribeOk {
  return {
    schemaVersion: SCHEMA_VERSION,
    command: "describe",
    status: "ok",
    adapter,
    capabilities: SLICE_MVP_1_CAPABILITIES,
  };
}
