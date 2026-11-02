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

interface RequiredCheck {
  readonly context?: unknown;
  readonly app_id?: unknown;
}

interface RequiredChecks {
  readonly strict?: unknown;
  readonly checks?: readonly RequiredCheck[];
}

const protectionPath = (context: RolloutContext): string =>
  `repos/${context.anchors.repository}/branches/${context.rollout.deployBranch}/protection/required_status_checks`;

function requiredChecks(context: RolloutContext): RequiredChecks {
  return context.read.github(protectionPath(context)) as RequiredChecks;
}

/** Whether the deploy branch requires the cloud verdict, from GitHub Actions alone. */
export function requiredCheckFinding(context: RolloutContext): Finding {
  const verdict = (requiredChecks(context).checks ?? []).find(
    (check) => check.context === VERDICT_JOB,
  );
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

/**
 * Require the cloud verdict on the deploy branch, keeping every check already
 * required and whether branches must be up to date. It adds; it never removes.
 */
export function requireCloudVerdict(context: RolloutContext): number {
  const current = requiredChecks(context);
  const kept = (current.checks ?? []).filter((check) => check.context !== VERDICT_JOB);
  const body = join(mkdtempSync(join(tmpdir(), "parallax-required-check-")), "checks.json");
  writeFileSync(
    body,
    JSON.stringify({
      strict: current.strict ?? true,
      checks: [...kept, { context: VERDICT_JOB, app_id: ACTIONS_APP_ID }],
    }),
  );
  succeeded(context.shell, {
    program: "gh",
    args: ["api", "--method", "PATCH", protectionPath(context), "--input", body],
  });
  return 0;
}
