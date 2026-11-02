import { CommandError, readJson, type Shell } from "./shell.ts";

/**
 * What one check found:
 * - `verified` — live configuration matches the approved inputs;
 * - `pending` — something approved is not in place yet, and a named setup
 *   step or a reviewed input supplies it;
 * - `drift` — live configuration contradicts the approved inputs, so nothing
 *   that depends on it may proceed;
 * - `unavailable` — the check could not read what it needed;
 * - `confirm` — only a human can establish it, and no API reports it.
 */
export type FindingState = "verified" | "pending" | "drift" | "unavailable" | "confirm";

export interface Finding {
  readonly check: string;
  readonly state: FindingState;
  readonly detail: string;
}

export const CHECK = {
  identity: "aws-identity",
  provider: "oidc-provider",
  connection: "source-connection",
  offering: "aurora-offering",
  natImage: "nat-image",
  accessStack: "access-stack",
  bootstrap: "bootstrap",
  budget: "budget",
  recipients: "budget-recipients",
  repository: "github-repository",
  forkApproval: "fork-approval",
  environment: "deploy-environment",
  branches: "deploy-branches",
  subject: "oidc-subject",
  token: "settings-token",
} as const;

/** One condition a check requires, and what to report when it does not hold. */
export type Expectation = readonly [holds: boolean, otherwise: string];

/** *check* as drift on its first expectation that does not hold, otherwise verified. */
export function judged(
  check: string,
  expectations: readonly Expectation[],
  detail: string,
): Finding {
  const failed = expectations.find(([holds]) => !holds);
  return failed === undefined
    ? { check, state: "verified", detail }
    : { check, state: "drift", detail: failed[1] };
}

/** The findings *assess* returns, or one unavailable finding for *check* when a command it needed failed. */
export function guarded(check: string, assess: () => Finding | readonly Finding[]): Finding[] {
  try {
    return ([] as Finding[]).concat(assess());
  } catch (error) {
    if (!(error instanceof CommandError)) throw error;
    return [{ check, state: "unavailable", detail: error.message }];
  }
}

/** Everything a check may read: AWS through the CLI, GitHub through `gh api`, and only ever by reading. */
export interface Sources {
  /** The JSON an `aws` read prints, or `undefined` when it fails saying what *absent* matches. */
  aws(args: readonly string[], absent?: RegExp): unknown;
  /** The JSON a GitHub REST `GET` of *path* returns, or `undefined` when *optional* and it is not found. */
  github(path: string, optional?: boolean): unknown;
}

const NOT_FOUND = /HTTP 404/;

export function sources(shell: Shell, region: string): Sources {
  return {
    aws: (args, absent) =>
      readJson(
        shell,
        { program: "aws", args: [...args, "--region", region, "--output", "json"] },
        absent,
      ),
    github: (path, optional = false) =>
      readJson(
        shell,
        { program: "gh", args: ["api", "--method", "GET", path] },
        optional ? NOT_FOUND : undefined,
      ),
  };
}

const ORDER: readonly FindingState[] = ["verified", "confirm", "pending", "drift", "unavailable"];

const HEADINGS: Readonly<Record<FindingState, string>> = {
  verified: "Verified",
  confirm: "For a human to confirm",
  pending: "Pending",
  drift: "Drift",
  unavailable: "Could not check",
};

/**
 * Print *findings* grouped by state, then *liveProofs*, the facts only a live
 * deployment and cloud run can establish. Returns whether nothing is pending,
 * drifted, or unchecked.
 */
export function report(findings: readonly Finding[], liveProofs: readonly string[]): boolean {
  for (const state of ORDER) {
    const group = findings.filter((found) => found.state === state);
    if (group.length === 0) continue;
    console.log(`${HEADINGS[state]}:`);
    for (const found of group) console.log(`  ${found.check}: ${found.detail}`);
  }
  if (liveProofs.length > 0) {
    console.log("Proven only by the protected deployment and the cloud run:");
    for (const proof of liveProofs) console.log(`  ${proof}`);
  }
  return findings.every((found) => found.state === "verified" || found.state === "confirm");
}
