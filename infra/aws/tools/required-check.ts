import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { VERDICT_JOB } from "./cloud-verification.ts";
import { judged, type Finding } from "./findings.ts";
import type { RolloutContext } from "./rollout-context.ts";
import { readLine, succeeded } from "./shell.ts";

/** GitHub Actions' app ID, the one source a required check here may come from. */
export const ACTIONS_APP_ID = 15368;

/** The cloud class's cell whose success on a commit is live evidence that the cloud path ran. */
export const CLOUD_CELL = "python-check-cloud (aws)";

export const REQUIRED_CHECK = "required-check";
export const CLOUD_EVIDENCE = "cloud-evidence";

/** One required check; a `null` app accepts the check from any source. */
interface RequiredCheck {
  readonly context: unknown;
  readonly app_id: unknown;
}

interface RequiredChecks {
  readonly strict: unknown;
  readonly checks: readonly RequiredCheck[];
}

/** What `required_status_checks` replies, in either of the forms it may list a check. */
interface RequiredChecksReply {
  readonly strict?: unknown;
  readonly contexts?: readonly unknown[];
  readonly checks?: readonly { readonly context?: unknown; readonly app_id?: unknown }[];
}

/** The `app_id` a PATCH takes to accept a check from any source. */
const ANY_APP = -1;

const protectionPath = (context: RolloutContext): string =>
  `repos/${context.anchors.repository}/branches/${context.rollout.deployBranch}/protection/required_status_checks`;

/**
 * Every check the deploy branch requires, whichever form lists it: a legacy
 * context with no matching check is required from any source, as it was.
 */
function requiredChecks(context: RolloutContext): RequiredChecks {
  const reply = context.read.github(protectionPath(context)) as RequiredChecksReply;
  const checks = (reply.checks ?? []).map((check) => ({
    context: check.context,
    app_id: check.app_id === undefined || check.app_id === ANY_APP ? null : check.app_id,
  }));
  const legacy = (reply.contexts ?? [])
    .filter((name) => !checks.some((check) => check.context === name))
    .map((name) => ({ context: name, app_id: null }));
  return { strict: reply.strict, checks: [...checks, ...legacy] };
}

/** Whether the deploy branch requires the cloud verdict, from GitHub Actions alone. */
export function requiredCheckFinding(context: RolloutContext): Finding {
  const verdict = requiredChecks(context).checks.find((check) => check.context === VERDICT_JOB);
  if (verdict === undefined) {
    return {
      check: REQUIRED_CHECK,
      state: "pending",
      detail: `${VERDICT_JOB} is not required yet; apply ${REQUIRED_CHECK} adds it`,
    };
  }
  return judged(
    REQUIRED_CHECK,
    [[verdict.app_id === ACTIONS_APP_ID, `${VERDICT_JOB} is required from another source`]],
    `${context.rollout.deployBranch} requires ${VERDICT_JOB} from GitHub Actions`,
  );
}

/** Whether the authorized commit carries live evidence: its AWS cloud cell ran and succeeded. */
export function cloudEvidenceFinding(context: RolloutContext): Finding {
  const head = readLine(context.shell, {
    program: "git",
    args: ["rev-parse", "HEAD"],
    cwd: context.root,
  });
  const { check_runs: runs = [] } = context.read.github(
    `repos/${context.anchors.repository}/commits/${head}/check-runs?check_name=${encodeURIComponent(CLOUD_CELL)}&filter=latest`,
  ) as {
    check_runs?: readonly { status?: unknown; conclusion?: unknown; app?: { id?: unknown } }[];
  };
  const proven = runs.some(
    (run) =>
      run.status === "completed" && run.conclusion === "success" && run.app?.id === ACTIONS_APP_ID,
  );
  return proven
    ? { check: CLOUD_EVIDENCE, state: "verified", detail: `${CLOUD_CELL} succeeded on ${head}` }
    : {
        check: CLOUD_EVIDENCE,
        state: "pending",
        detail: `${CLOUD_CELL} has not succeeded on ${head}; requiring the verdict waits for live evidence`,
      };
}

const sameCheck = (one: RequiredCheck, other: RequiredCheck): boolean =>
  one.context === other.context && one.app_id === other.app_id;

/**
 * Require the cloud verdict on the deploy branch, keeping every check already
 * required and whether branches must be up to date. It adds; it never removes,
 * and it fails unless the requirement reads back with nothing lost.
 */
export function requireCloudVerdict(context: RolloutContext): number {
  const current = requiredChecks(context);
  const strict = current.strict ?? true;
  const intended = [
    ...current.checks.filter((check) => check.context !== VERDICT_JOB),
    { context: VERDICT_JOB, app_id: ACTIONS_APP_ID },
  ];
  const body = join(mkdtempSync(join(tmpdir(), "parallax-required-check-")), "checks.json");
  writeFileSync(
    body,
    JSON.stringify({
      strict,
      checks: intended.map((check) => ({
        context: check.context,
        app_id: check.app_id ?? ANY_APP,
      })),
    }),
  );
  succeeded(context.shell, {
    program: "gh",
    args: ["api", "--method", "PATCH", protectionPath(context), "--input", body],
  });
  const after = requiredChecks(context);
  const lost = intended.filter((check) => !after.checks.some((kept) => sameCheck(kept, check)));
  const missing = [
    ...lost.map((check) => String(check.context)),
    ...(after.strict === strict ? [] : ["its up-to-date rule"]),
  ];
  if (missing.length > 0) {
    console.error(`${REQUIRED_CHECK}: the requirement read back without ${missing.join(", ")}`);
    return 1;
  }
  return 0;
}
