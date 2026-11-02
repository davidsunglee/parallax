import { TEST_ENVIRONMENT_PARAMETER } from "../src/test-environment.ts";
import type { Clock } from "./clock.ts";
import type { RolloutContext } from "./rollout-context.ts";
import { CommandError, succeeded } from "./shell.ts";

/** The workflow whose cloud path proves a deployment. */
export const CLOUD_WORKFLOW = "ci.yml";

/** Its dispatch input naming the TestEnvironment version the cloud run must observe. */
export const ENVIRONMENT_VERSION_INPUT = "environment-version";

/** Its required status, which a dispatched run's proof is read from. */
export const VERDICT_JOB = "cloud-verdict";

/** The actor a dispatch made with the workflow's own token is recorded under. */
export const DISPATCHER = "github-actions[bot]";

/** How long a dispatched run may take to appear, and its verdict to finish. */
export const DISCOVERY_DEADLINE = 10 * 60_000;
export const VERDICT_DEADLINE = 140 * 60_000;
export const POLL_INTERVAL = 30_000;

/** How far the API's clock may run behind this one when a run's creation is compared with the dispatch. */
const CLOCK_SKEW = 60_000;

/** What a deployment's cloud verification found. */
export interface CloudVerification {
  readonly revision: string;
  readonly environmentVersion: number | null;
  readonly run: string | null;
  readonly verdict: string | null;
}

interface WorkflowRun {
  readonly id?: unknown;
  readonly html_url?: unknown;
  readonly created_at?: unknown;
  readonly head_sha?: unknown;
  readonly event?: unknown;
  readonly actor?: { readonly login?: unknown };
}

interface Job {
  readonly name?: unknown;
  readonly status?: unknown;
  readonly conclusion?: unknown;
}

function environmentVersion(context: RolloutContext): number | null {
  const { Parameter: parameter } = context.read.aws([
    "ssm",
    "get-parameter",
    "--name",
    TEST_ENVIRONMENT_PARAMETER,
  ]) as { Parameter?: { Version?: unknown } };
  return typeof parameter?.Version === "number" ? parameter.Version : null;
}

function branchHead(context: RolloutContext): unknown {
  const { repository } = context.anchors;
  const { deployBranch } = context.rollout;
  return (context.read.github(`repos/${repository}/commits/${deployBranch}`) as { sha?: unknown })
    .sha;
}

function dispatch(context: RolloutContext, version: number): void {
  const { repository } = context.anchors;
  const { deployBranch } = context.rollout;
  succeeded(context.shell, {
    program: "gh",
    args: [
      "api",
      "--method",
      "POST",
      `repos/${repository}/actions/workflows/${CLOUD_WORKFLOW}/dispatches`,
      "-f",
      `ref=${deployBranch}`,
      "-f",
      `inputs[${ENVIRONMENT_VERSION_INPUT}]=${String(version)}`,
    ],
  });
}

/** The runs this tool's dispatch of *revision* since *since* can be. */
function dispatchedRuns(context: RolloutContext, revision: string, since: number): WorkflowRun[] {
  const { repository } = context.anchors;
  const { deployBranch } = context.rollout;
  const { workflow_runs: runs = [] } = context.read.github(
    `repos/${repository}/actions/workflows/${CLOUD_WORKFLOW}/runs?event=workflow_dispatch&branch=${deployBranch}&head_sha=${revision}&per_page=100`,
  ) as { workflow_runs?: readonly WorkflowRun[] };
  return runs.filter(
    (run) =>
      run.event === "workflow_dispatch" &&
      run.head_sha === revision &&
      run.actor?.login === DISPATCHER &&
      Date.parse(String(run.created_at)) >= since - CLOCK_SKEW,
  );
}

/**
 * Poll *attempt* until it returns a settled answer or *deadline* passes; a
 * command that fails meanwhile is retried within the deadline.
 */
function polled<T>(
  clock: Clock,
  deadline: number,
  attempt: () => T | undefined,
  expired: (failure: string | undefined) => T,
): T {
  let failure: string | undefined;
  for (;;) {
    try {
      const settled = attempt();
      if (settled !== undefined) return settled;
    } catch (error) {
      if (!(error instanceof CommandError)) throw error;
      failure = error.message;
    }
    if (clock.monotonic() >= deadline) return expired(failure);
    clock.sleep(POLL_INTERVAL);
  }
}

const because = (failure: string | undefined): string =>
  failure === undefined ? "" : ` (last failure: ${failure})`;

/** The run this tool's dispatch created: a candidate not already listed before it dispatched. */
function discovered(
  context: RolloutContext,
  revision: string,
  since: number,
  earlier: ReadonlySet<unknown>,
  clock: Clock,
): WorkflowRun | string {
  return polled<WorkflowRun | string>(
    clock,
    clock.monotonic() + DISCOVERY_DEADLINE,
    () => {
      const runs = dispatchedRuns(context, revision, since).filter((run) => !earlier.has(run.id));
      if (runs.length > 1) return `${String(runs.length)} dispatched runs match; none is this one`;
      return runs[0];
    },
    (failure) => `no dispatched ${CLOUD_WORKFLOW} run appeared${because(failure)}`,
  );
}

/** The verdict job's conclusion in *run*'s first attempt, once it finished. */
function verdictOf(context: RolloutContext, run: WorkflowRun, clock: Clock): string {
  const path = `repos/${context.anchors.repository}/actions/runs/${String(run.id)}/attempts/1/jobs?per_page=100`;
  return polled(
    clock,
    clock.monotonic() + VERDICT_DEADLINE,
    () => {
      const { jobs = [] } = context.read.github(path) as { jobs?: readonly Job[] };
      const verdict = jobs.find((job) => job.name === VERDICT_JOB);
      return verdict?.status === "completed" ? String(verdict.conclusion) : undefined;
    },
    (failure) => `unfinished${because(failure)}`,
  );
}

/**
 * Prove the deployment of *revision* through the cloud path: dispatch it on
 * the deploy branch, requiring the run to observe the TestEnvironment version
 * this deployment published, and wait for that run's verdict. A run already
 * listed before the dispatch is an earlier dispatch's, never this one's, since
 * a run does not report the inputs it was dispatched with. It refuses when the
 * branch has moved past *revision*, since the dispatched run would test another
 * commit; the next deployment's run then verifies the environment.
 */
export function verifyCloud(
  context: RolloutContext,
  revision: string,
  clock: Clock,
): { verification: CloudVerification; problems: string[] } {
  const version = environmentVersion(context);
  const found = (run: string | null, verdict: string | null): CloudVerification => ({
    revision,
    environmentVersion: version,
    run,
    verdict,
  });
  if (version === null) {
    return {
      verification: found(null, null),
      problems: ["the published TestEnvironment carries no version"],
    };
  }
  const head = branchHead(context);
  if (head !== revision) {
    const branch = context.rollout.deployBranch;
    return {
      verification: found(null, null),
      problems: [`${branch} is at ${String(head)}, not the deployed ${revision}`],
    };
  }
  const since = clock.wall();
  let earlier: ReadonlySet<unknown>;
  try {
    earlier = new Set(dispatchedRuns(context, revision, since).map((run) => run.id));
    dispatch(context, version);
  } catch (error) {
    if (!(error instanceof CommandError)) throw error;
    return { verification: found(null, null), problems: [error.message] };
  }
  const run = discovered(context, revision, since, earlier, clock);
  if (typeof run === "string") return { verification: found(null, null), problems: [run] };
  const verdict = verdictOf(context, run, clock);
  return {
    verification: found(String(run.html_url), verdict),
    problems: verdict === "success" ? [] : [`${VERDICT_JOB} concluded ${verdict}`],
  };
}
