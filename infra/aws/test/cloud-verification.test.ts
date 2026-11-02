import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { systemClock } from "../tools/clock.ts";
import {
  CLOUD_WORKFLOW,
  DISCOVERY_DEADLINE,
  DISPATCHER,
  ENVIRONMENT_VERSION_INPUT,
  POLL_INTERVAL,
  VERDICT_DEADLINE,
  VERDICT_JOB,
  verifyCloud,
} from "../tools/cloud-verification.ts";
import { main } from "../tools/rollout.ts";
import {
  failed,
  json,
  readsOnly,
  REPOSITORY,
  REVISION,
  ScriptedClock,
  world,
  type Reply,
} from "./rollout-world.ts";

let log: MockInstance<(...data: unknown[]) => void>;
let errors: MockInstance<(...data: unknown[]) => void>;

beforeEach(() => {
  log = vi.spyOn(console, "log").mockImplementation(() => undefined);
  errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

const printed = (spy: MockInstance<(...data: unknown[]) => void>): string =>
  spy.mock.calls.map(([line]) => String(line)).join("\n");

const HEAD = `GET ${REPOSITORY}/commits/main`;
const DISPATCH = `POST ${REPOSITORY}/actions/workflows/${CLOUD_WORKFLOW}/dispatches`;
const RUNS = `GET ${REPOSITORY}/actions/workflows/${CLOUD_WORKFLOW}/runs?event=workflow_dispatch&branch=main&head_sha=${REVISION}&per_page=100`;
const JOBS = `GET ${REPOSITORY}/actions/runs/77/attempts/1/jobs?per_page=100`;
const RUN_URL = "https://github.com/davidsunglee/parallax/actions/runs/77";
const DISPATCHED = new Date(ScriptedClock.START).toISOString();

const dispatchedRun = (changes: Record<string, unknown> = {}): Record<string, unknown> => ({
  id: 77,
  html_url: RUN_URL,
  created_at: DISPATCHED,
  head_sha: REVISION,
  event: "workflow_dispatch",
  actor: { login: DISPATCHER },
  ...changes,
});

const verdict = (status: string, conclusion: string | null = null): Reply =>
  json({
    jobs: [
      { name: "python-check-cloud (aws)", status: "completed", conclusion: "success" },
      { name: VERDICT_JOB, status, conclusion },
    ],
  });

/** A reply giving each of *replies* in turn, then the last one for good. */
function inTurn(...replies: Reply[]): Reply {
  let next = 0;
  return () => {
    const reply = replies[Math.min(next, replies.length - 1)];
    next += 1;
    if (reply === undefined) throw new Error("no reply scripted");
    return reply;
  };
}

const HEALTHY: Record<string, Reply> = {
  [HEAD]: json({ sha: REVISION }),
  [DISPATCH]: { status: 0, stdout: "", stderr: "" },
  [RUNS]: json({ workflow_runs: [dispatchedRun()] }),
  [JOBS]: verdict("completed", "success"),
};

const NONE_YET = json({ workflow_runs: [] });

/**
 * The scripted world, in which the runs listing answers *replies*' listing only
 * once the dispatch was made, and *earlier* before it.
 */
function dispatching(replies: Record<string, Reply> = {}, earlier: Reply = NONE_YET) {
  const table = { ...HEALTHY, ...replies };
  const [dispatch, listed] = [table[DISPATCH], table[RUNS]];
  if (dispatch === undefined || listed === undefined) throw new Error("no reply scripted");
  let dispatched = false;
  return world({
    ...table,
    [DISPATCH]: () => {
      dispatched = true;
      return dispatch;
    },
    [RUNS]: () => (dispatched ? listed : earlier),
  });
}

function verified(replies: Record<string, Reply> = {}, earlier: Reply = NONE_YET) {
  const scripted = dispatching(replies, earlier);
  return { ...scripted, ...verifyCloud(scripted.context, REVISION, scripted.clock) };
}

describe("proving a deployment through the cloud path", () => {
  it("dispatches the cloud path for the deployed record and reads its verdict", () => {
    const { verification, problems, captured } = verified();
    expect(problems).toEqual([]);
    expect(verification).toEqual({
      revision: REVISION,
      environmentVersion: 3,
      run: RUN_URL,
      verdict: "success",
    });
    const writes = captured.filter((invocation) => !readsOnly(invocation));
    expect(writes).toEqual([
      {
        program: "gh",
        args: [
          "api",
          "--method",
          "POST",
          `${REPOSITORY}/actions/workflows/${CLOUD_WORKFLOW}/dispatches`,
          "-f",
          "ref=main",
          "-f",
          `inputs[${ENVIRONMENT_VERSION_INPUT}]=3`,
        ],
      },
    ]);
  });

  it("waits for the dispatched run to appear and for its verdict to finish", () => {
    const { problems, clock } = verified({
      [RUNS]: inTurn(json({ workflow_runs: [] }), json({ workflow_runs: [dispatchedRun()] })),
      [JOBS]: inTurn(json({ jobs: [] }), verdict("in_progress"), verdict("completed", "success")),
    });
    expect(problems).toEqual([]);
    expect(clock.slept).toEqual([POLL_INTERVAL, POLL_INTERVAL, POLL_INTERVAL]);
  });

  it("retries a failed read within the deadline", () => {
    const { problems } = verified({
      [JOBS]: inTurn(failed("HTTP 502"), verdict("completed", "success")),
    });
    expect(problems).toEqual([]);
  });

  it("refuses when the branch moved past the deployed revision, dispatching nothing", () => {
    const { problems, captured } = verified({ [HEAD]: json({ sha: "feedface" }) });
    expect(problems).toEqual([`main is at feedface, not the deployed ${REVISION}`]);
    expect(captured.every(readsOnly)).toBe(true);
  });

  it("refuses when the published record carries no version", () => {
    const { problems, verification } = verified({
      "ssm get-parameter --name /parallax/ci/aws/test-environment": json({ Parameter: {} }),
    });
    expect(problems).toEqual(["the published TestEnvironment carries no version"]);
    expect(verification.environmentVersion).toBeNull();
  });

  it("reports a refused dispatch", () => {
    const { problems } = verified({ [DISPATCH]: failed("HTTP 403: Resource not accessible") });
    expect(problems).toEqual([
      `gh api --method POST ${REPOSITORY}/actions/workflows/${CLOUD_WORKFLOW}/dispatches failed: HTTP 403: Resource not accessible`,
    ]);
  });

  it("refuses to choose between two runs this dispatch could be", () => {
    const { problems } = verified({
      [RUNS]: json({ workflow_runs: [dispatchedRun(), dispatchedRun({ id: 78 })] }),
    });
    expect(problems).toEqual(["2 dispatched runs match; none is this one"]);
  });

  it("never takes a run listed before its dispatch for the one it dispatched", () => {
    const earlier = dispatchedRun({
      id: 70,
      html_url: "https://github.com/davidsunglee/parallax/actions/runs/70",
      created_at: new Date(ScriptedClock.START - 30_000).toISOString(),
    });
    const { problems, verification } = verified(
      {
        [RUNS]: inTurn(
          json({ workflow_runs: [earlier] }),
          json({ workflow_runs: [dispatchedRun(), earlier] }),
        ),
      },
      json({ workflow_runs: [earlier] }),
    );
    expect(problems).toEqual([]);
    expect(verification.run).toBe(RUN_URL);
  });

  it("dispatches nothing when it cannot list the runs already there", () => {
    const { problems, captured } = verified({}, failed("HTTP 500"));
    expect(problems).toEqual([`gh api --method GET ${RUNS.slice(4)} failed: HTTP 500`]);
    expect(captured.every(readsOnly)).toBe(true);
  });

  it("accepts no run another actor, event, commit, or an earlier dispatch started", () => {
    const { problems, clock } = verified({
      [RUNS]: json({
        workflow_runs: [
          dispatchedRun({ actor: { login: "davidsunglee" } }),
          dispatchedRun({ event: "push" }),
          dispatchedRun({ head_sha: "feedface" }),
          dispatchedRun({ created_at: "2026-11-02T11:58:00Z" }),
        ],
      }),
    });
    expect(problems).toEqual([`no dispatched ${CLOUD_WORKFLOW} run appeared`]);
    expect(clock.elapsed).toBeGreaterThanOrEqual(DISCOVERY_DEADLINE);
    expect(clock.elapsed).toBeLessThan(DISCOVERY_DEADLINE + 2 * POLL_INTERVAL);
  });

  it("reports the last failure when reads fail until the deadline", () => {
    const { problems } = verified({ [RUNS]: failed("HTTP 500") });
    expect(problems).toEqual([
      `no dispatched ${CLOUD_WORKFLOW} run appeared (last failure: gh api --method GET ${RUNS.slice(4)} failed: HTTP 500)`,
    ]);
  });

  it("fails on any verdict but success", () => {
    for (const conclusion of ["failure", "cancelled", "skipped"]) {
      const { problems, verification } = verified({ [JOBS]: verdict("completed", conclusion) });
      expect(problems).toEqual([`${VERDICT_JOB} concluded ${conclusion}`]);
      expect(verification.run).toBe(RUN_URL);
    }
  });

  it("fails when the verdict does not finish within its deadline", () => {
    const { problems, clock } = verified({ [JOBS]: verdict("queued") });
    expect(problems).toEqual([`${VERDICT_JOB} concluded unfinished`]);
    expect(clock.elapsed).toBeGreaterThanOrEqual(VERDICT_DEADLINE);
  });

  it("lets anything but a failed command escape", () => {
    const thrown = (): Reply => {
      throw new TypeError("not a command failure");
    };
    expect(() => verified({ [JOBS]: thrown })).toThrow(TypeError);
    expect(() => verified({ [DISPATCH]: thrown })).toThrow(TypeError);
  });
});

describe("the verify-cloud command", () => {
  function run(argv: readonly string[], replies: Record<string, Reply> = {}) {
    const scripted = dispatching(replies);
    return main(argv, scripted.shell, scripted.context.root, scripted.clock);
  }

  it("prints what it found and succeeds on a successful verdict", () => {
    expect(run(["verify-cloud", "--revision", REVISION])).toBe(0);
    expect(printed(log)).toContain(`"run": "${RUN_URL}"`);
  });

  it("fails with each problem on its own line", () => {
    expect(
      run(["verify-cloud", "--revision", REVISION], { [JOBS]: verdict("completed", "failure") }),
    ).toBe(1);
    expect(printed(errors)).toBe(`verify-cloud: ${VERDICT_JOB} concluded failure`);
  });

  it("needs the deployed revision", () => {
    expect(run(["verify-cloud"])).toBe(2);
  });
});

describe("the system clock", () => {
  it("reads wall time, never goes back, and sleeps", () => {
    const before = Date.now();
    const start = systemClock.monotonic();
    systemClock.sleep(1);
    expect(systemClock.monotonic()).toBeGreaterThan(start);
    expect(systemClock.wall()).toBeGreaterThanOrEqual(before);
  });
});
