import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import { SETTINGS_TOKEN_SECRET } from "../tools/github-assessment.ts";
import { PACKAGE_ROOT } from "./committed-app.ts";
import { ANCHORS, ROLLOUT } from "./rollout-world.ts";

interface Step {
  readonly name?: string;
  readonly uses?: string;
  readonly run?: string;
  readonly shell?: string;
  readonly with?: Record<string, unknown>;
  readonly env?: Record<string, unknown>;
  readonly "continue-on-error"?: unknown;
}

interface Workflow {
  readonly on: Record<string, unknown>;
  readonly permissions: unknown;
  readonly concurrency: Record<string, unknown>;
  readonly jobs: Record<string, Record<string, unknown>>;
}

const WORKFLOW_PATH = join(PACKAGE_ROOT, "../../.github/workflows/infra-deploy.yml");
const source = readFileSync(WORKFLOW_PATH, "utf8");
const workflow = parse(source) as Workflow;
const [jobName, job] = Object.entries(workflow.jobs)[0] ?? ["", {}];
const steps = job["steps"] as Step[];
const index = (predicate: (step: Step) => boolean): number => steps.findIndex(predicate);
const running = (command: string) => (step: Step) => step.run?.includes(command) === true;

describe("the deploy workflow", () => {
  it("runs on main pushes that touch deployment inputs, and on dispatch, never on pull requests", () => {
    expect(Object.keys(workflow.on).sort()).toEqual(["push", "workflow_dispatch"]);
    expect(workflow.on["workflow_dispatch"]).toBeNull();
    const push = workflow.on["push"] as { branches: string[]; paths: string[] };
    expect(push.branches).toEqual([ROLLOUT.deployBranch]);
    expect(push.paths).toEqual(
      expect.arrayContaining([
        "infra/**",
        ".github/workflows/infra-deploy.yml",
        "pnpm-lock.yaml",
        "justfile",
      ]),
    );
    for (const untrusted of [
      "pull_request",
      "pull_request_target",
      "github.head_ref",
      "github.event.pull_request",
      "workflow_run",
    ]) {
      expect(source).not.toContain(untrusted);
    }
  });

  it("has one job, gated to main and to the protected environment, with only OIDC and read access", () => {
    expect(Object.keys(workflow.jobs)).toEqual([jobName]);
    expect(workflow.permissions).toEqual({});
    expect(job["if"]).toBe("github.ref == 'refs/heads/main'");
    expect(job["environment"]).toBe(ROLLOUT.deployEnvironment);
    expect(job["permissions"]).toEqual({ contents: "read", "id-token": "write" });
    expect(job["timeout-minutes"]).toEqual(expect.any(Number));
    expect(steps[0]?.run).toBe('test "$GITHUB_REF" = refs/heads/main');
  });

  it("deploys one rollout at a time and never cancels one in progress", () => {
    expect(workflow.concurrency).toEqual({ group: "infra-deploy", "cancel-in-progress": false });
  });

  it("checks out exactly the triggering main commit and keeps no git credential", () => {
    const checkout = steps.find((step) => step.uses?.startsWith("actions/checkout@") === true);
    expect(checkout?.with).toEqual({ ref: "${{ github.sha }}", "persist-credentials": false });
  });

  it("verifies protections, then synthesizes, before it holds any AWS credential", () => {
    const credentials = index(
      (step) => step.uses?.startsWith("aws-actions/configure-aws-credentials@") === true,
    );
    expect(index(running("rollout.ts verify-github"))).toBeLessThan(credentials);
    expect(index(running("just infra-build"))).toBeLessThan(credentials);
    expect(credentials).toBeLessThan(index(running("rollout.ts verify-aws")));
    expect(index(running("rollout.ts verify-aws"))).toBeLessThan(
      index(running("rollout.ts deploy")),
    );
    expect(index(running("rollout.ts deploy"))).toBeLessThan(index(running("rollout.ts evidence")));
  });

  it("assumes only the pinned deploy role, in the configured account and Region", () => {
    const credentials = steps.find(
      (step) => step.uses?.startsWith("aws-actions/configure-aws-credentials@") === true,
    );
    expect(credentials?.with).toMatchObject({
      "role-to-assume": ANCHORS.deployRoleArn,
      "allowed-account-ids": ANCHORS.account,
      "aws-region": ANCHORS.region,
      "role-skip-session-tagging": true,
    });
    expect(credentials?.with).not.toHaveProperty("aws-access-key-id");
  });

  it("hands the settings token to the protection check alone", () => {
    const holders = steps.filter((step) => JSON.stringify(step).includes("secrets."));
    expect(holders.map((step) => step.name)).toEqual(["Verify repository protections"]);
    expect(holders[0]?.env).toEqual({ GH_TOKEN: `\${{ secrets.${SETTINGS_TOKEN_SECRET} }}` });
  });

  it("deploys through the tool, which names the environment stack alone, and lets every failure fail the job", () => {
    const deploy = steps.find(running("rollout.ts deploy"));
    expect(deploy?.run).toBe('node infra/aws/tools/rollout.ts deploy --revision "$GITHUB_SHA"');
    expect(source).not.toMatch(/cdk (deploy|destroy|bootstrap)/);
    for (const step of steps) expect(step["continue-on-error"], step.name).toBeUndefined();
    const evidence = steps.find(running("rollout.ts evidence"));
    expect(evidence?.shell).toBe("bash");
    expect(evidence?.run).toContain('| tee -a "$GITHUB_STEP_SUMMARY"');
  });
});
