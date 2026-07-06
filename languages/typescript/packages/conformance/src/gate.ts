/**
 * The six-condition in-claim / out-of-claim gate (m-case-format routing contract).
 *
 * A case is **in claim** iff every condition holds (a conjunction):
 *   1. the command is claimed (`command ∈ commands`);
 *   2. the dialect is claimed (`dialect ∈ dialects`);
 *   3. the case shape is claimed (`shape ∈ caseShapes`);
 *   4. every `m*` module tag the case carries is claimed (`m*-tags ⊆ modules`);
 *   5. an include tag is present (when `caseTags.include` is declared);
 *   6. no exclude tag is present (when `caseTags.exclude` is declared).
 *
 * In claim ⇒ the adapter MUST attempt the case and return `ok` / `error`
 * (returning `unsupported` for an in-claim case is itself a conformance
 * failure). Out of claim ⇒ `unsupported`, with a diagnostic naming the **first**
 * failed filter (deterministic, in the order above).
 */
import type { Capabilities, Command } from "@parallax/core";

/** The outcome of the gate: in-claim, or out-of-claim with a reason. */
export type GateResult =
  | { readonly inClaim: true }
  | { readonly inClaim: false; readonly code: GateDiagnosticCode; readonly message: string };

/** The diagnostic codes the gate emits, one per failable condition. */
export type GateDiagnosticCode =
  | "unsupported-command"
  | "unsupported-dialect"
  | "unsupported-shape"
  | "unsupported-case-tag"
  | "missing-include-tag"
  | "excluded-case-tag";

/** A case's gating-relevant fields. */
export interface GateCase {
  readonly shape: string;
  readonly tags: readonly string[];
}

/** Every `m-<slug>` module tag a case carries. */
function moduleTags(tags: readonly string[]): readonly string[] {
  return tags.filter((tag) => /^m-[a-z0-9]+(-[a-z0-9]+)*$/.test(tag));
}

/**
 * Evaluate the six-condition gate. Conditions are checked in the fixed order
 * above so the first failure is deterministic.
 */
export function inClaim(
  c: GateCase,
  command: Command,
  dialect: string,
  caps: Capabilities,
): GateResult {
  if (!caps.commands.includes(command)) {
    return out("unsupported-command", `command '${command}' is not claimed`);
  }
  if (!caps.dialects.includes(dialect)) {
    return out("unsupported-dialect", `dialect '${dialect}' is not claimed`);
  }
  if (!caps.caseShapes.includes(c.shape as (typeof caps.caseShapes)[number])) {
    return out("unsupported-shape", `case shape '${c.shape}' is not claimed`);
  }
  for (const tag of moduleTags(c.tags)) {
    if (!caps.modules.includes(tag as (typeof caps.modules)[number])) {
      return out("unsupported-case-tag", `module tag '${tag}' is not claimed`);
    }
  }
  const include = caps.caseTags?.include;
  if (include && include.length > 0 && !c.tags.some((tag) => include.includes(tag))) {
    return out(
      "missing-include-tag",
      `case carries no required include tag (${include.join(", ")})`,
    );
  }
  const exclude = caps.caseTags?.exclude;
  if (exclude && exclude.length > 0) {
    const hit = c.tags.find((tag) => exclude.includes(tag));
    if (hit !== undefined) {
      return out("excluded-case-tag", `case carries excluded tag '${hit}'`);
    }
  }
  return { inClaim: true };
}

/** Build an out-of-claim gate result. */
function out(code: GateDiagnosticCode, message: string): GateResult {
  return { inClaim: false, code, message };
}
