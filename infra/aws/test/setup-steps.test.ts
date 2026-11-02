import { readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  BOUNDARY_POLICY_NAME,
  DEPLOY_ROLE_NAME,
} from "../src/trust.ts";
import { BOOTSTRAP_VARIANT } from "../tools/bootstrap-template.ts";
import { CDK_CLI, PACKAGE_ROOT } from "../tools/rollout-context.ts";
import { applyStep, revisionProblems, SETUP_STEPS } from "../tools/setup-steps.ts";
import type { Invocation } from "../tools/shell.ts";
import {
  ABSENT_STACK,
  ACCOUNT,
  ANCHORS,
  ENVIRONMENT,
  failed,
  json,
  readsOnly,
  REPOSITORY,
  REVISION,
  world,
  type Reply,
} from "./rollout-world.ts";

let errors: MockInstance<(...data: unknown[]) => void>;

beforeEach(() => {
  errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.restoreAllMocks();
});

const refusals = (): string => errors.mock.calls.map(([line]) => String(line)).join("\n");

const apply = (
  replies: Record<string, Reply>,
  name: string,
  attach?: (invocation: Invocation) => number,
) => {
  const scripted = world(replies, attach);
  return { ...scripted, status: applyStep(scripted.context, name, name, REVISION) };
};

describe("every setup step", () => {
  it("is refused without its own authorization", () => {
    for (const name of Object.keys(SETUP_STEPS)) {
      const { context, attached } = world();
      expect(applyStep(context, name, "everything", REVISION)).toBe(1);
      expect(attached).toEqual([]);
    }
    expect(applyStep(world().context, "deploy-environment", "deploy-environment", REVISION)).toBe(
      1,
    );
    expect(refusals()).toContain("each step needs its own --authorize");
  });

  it("is refused outside the reviewed, unmodified main revision", () => {
    const { context } = world({
      "git rev-parse HEAD": { status: 0, stdout: "feedface\n", stderr: "" },
      "git status --porcelain": { status: 0, stdout: " M infra/aws/cdk.json\n", stderr: "" },
      "git merge-base --is-ancestor HEAD origin/main": { status: 1, stdout: "", stderr: "" },
    });
    expect(revisionProblems(context, REVISION)).toEqual([
      `HEAD is feedface, not the authorized ${REVISION}`,
      "the checkout has uncommitted changes",
      "HEAD is not on origin/main",
    ]);
    expect(revisionProblems(world().context, REVISION)).toEqual([]);
    for (const name of Object.keys(SETUP_STEPS)) {
      const { context: dirty, attached } = world({
        "git status --porcelain": { status: 0, stdout: "?? x\n", stderr: "" },
      });
      expect(applyStep(dirty, name, name, REVISION)).toBe(1);
      expect(attached).toEqual([]);
    }
  });
});

describe("the access-stack step", () => {
  it("builds in isolation, then deploys only the access stack for a maintainer to approve", () => {
    const { status, attached } = apply({}, "access-stack");
    expect(status).toBe(0);
    expect(attached).toEqual([
      {
        program: process.execPath,
        args: [expect.stringMatching(/infra\/tools\/build\.ts$/) as string],
        cwd: expect.stringMatching(/infra$/) as string,
      },
      {
        program: process.execPath,
        args: [
          CDK_CLI,
          "deploy",
          ACCESS_STACK_NAME,
          "--app",
          "cdk.out",
          "--exclusively",
          "--require-approval",
          "any-change",
          "--no-notices",
        ],
        cwd: PACKAGE_ROOT,
      },
    ]);
  });

  it("deploys nothing when the build fails, and reports a failed deploy", () => {
    expect(apply({}, "access-stack", () => 2)).toMatchObject({
      status: 2,
      attached: [expect.anything()],
    });
    let calls = 0;
    expect(apply({}, "access-stack", () => (calls++ === 0 ? 0 : 3)).status).toBe(3);
    expect(refusals()).toContain("the step exited 3");
  });

  it("is refused as the deploy role, against a drifted provider, or with an unsettled guardrail", () => {
    const cases: Record<string, Reply>[] = [
      {
        "sts get-caller-identity": json({
          Account: ACCOUNT,
          Arn: `arn:aws:sts::${ACCOUNT}:assumed-role/${DEPLOY_ROLE_NAME}/x`,
        }),
      },
      { "iam get-open-id-connect-provider": json({ Url: "elsewhere" }) },
      { "codeconnections get-connection": failed("AccessDenied") },
      { "budgets describe-budgets": json({ Budgets: [] }) },
      { "budgets describe-budgets": failed("AccessDenied") },
    ];
    for (const replies of cases) {
      const { status, attached } = apply(replies, "access-stack");
      expect(status).toBe(1);
      expect(attached).toEqual([]);
    }
    expect(refusals()).toContain("budget: no monthly cost budget guards the account");
  });

  it("proceeds while the guardrail transition is merely pending", () => {
    const pendingTransition = world({}, () => 0);
    const configured = {
      ...pendingTransition.context,
      rollout: {
        ...pendingTransition.context.rollout,
        budget: {
          ownership: "stack",
          name: "parallax-ci-tagged",
          limitUsd: 50,
          recipients: ["owner@example.com"],
        },
      },
    } as const;
    expect(applyStep(configured, "access-stack", "access-stack", REVISION)).toBe(0);
  });

  it("fails when the deployed stack does not verify afterwards", () => {
    expect(
      apply(
        {
          [`cloudformation describe-stacks --stack-name ${ACCESS_STACK_NAME}`]:
            ABSENT_STACK(ACCESS_STACK_NAME),
        },
        "access-stack",
      ).status,
    ).toBe(1);
  });
});

describe("the bootstrap step", () => {
  it("bootstraps the narrowed template with the bounded policy and boundary, outside the app", () => {
    const { status, attached } = apply({}, "bootstrap");
    expect(status).toBe(0);
    const [command] = attached;
    expect(command?.cwd?.startsWith(tmpdir())).toBe(true);
    const args = command?.args ?? [];
    expect(args.slice(0, 3)).toEqual([CDK_CLI, "bootstrap", `aws://${ACCOUNT}/us-east-2`]);
    const flag = (name: string): string | undefined => args[args.indexOf(name) + 1];
    expect(flag("--qualifier")).toBe(ANCHORS.qualifier);
    expect(flag("--toolkit-stack-name")).toBe(BOOTSTRAP_STACK_NAME);
    expect(flag("--cloudformation-execution-policies")).toBe(ANCHORS.executionPolicyArn);
    expect(flag("--custom-permissions-boundary")).toBe(BOUNDARY_POLICY_NAME);
    expect(args).toEqual(
      expect.arrayContaining(["--termination-protection", "--no-previous-parameters"]),
    );
    expect(args).not.toContain("--trust");
    const template = readFileSync(String(flag("--template")), "utf8");
    expect(template).toContain(BOOTSTRAP_VARIANT);
    expect(template).not.toContain("AdministratorAccess");
  });

  it("waits for the access stack that holds the role and policies it names", () => {
    const { status, attached } = apply(
      {
        [`cloudformation describe-stacks --stack-name ${ACCESS_STACK_NAME}`]:
          ABSENT_STACK(ACCESS_STACK_NAME),
      },
      "bootstrap",
    );
    expect(status).toBe(1);
    expect(attached).toEqual([]);
    expect(refusals()).toContain("access-stack: deploy ParallaxCiAccessStack");
  });
});

describe("the github-settings step", () => {
  it("changes nothing that already holds", () => {
    const { status, captured } = apply({}, "github-settings");
    expect(status).toBe(0);
    expect(captured.every(readsOnly)).toBe(true);
  });

  it("converges the approval policy, the environment, and its branch rule, then verifies them", () => {
    const changes: string[] = [];
    let applied = false;
    const record = (invocation: Invocation): Reply => {
      changes.push(`${String(invocation.args[2])} ${String(invocation.args[3])}`);
      applied = true;
      return { status: 0, stdout: "", stderr: "" };
    };
    const beforeAndAfter = (before: Reply) => (invocation: Invocation) =>
      applied ? (world().replies[`GET ${String(invocation.args[3])}`] ?? before) : before;
    const scripted = world({
      [`GET ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: beforeAndAfter(
        json({ approval_policy: "first_time_contributors" }),
      ),
      [`GET ${ENVIRONMENT}`]: beforeAndAfter(failed("gh: Not Found (HTTP 404)", 1)),
      [`GET ${ENVIRONMENT}/deployment-branch-policies`]: beforeAndAfter(
        failed("gh: Not Found (HTTP 404)", 1),
      ),
      [`PUT ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: record,
      [`PUT ${ENVIRONMENT}`]: (invocation) => {
        const body = JSON.parse(readFileSync(String(invocation.args[5]), "utf8")) as unknown;
        expect(body).toEqual({
          reviewers: [{ type: "User", id: 42 }],
          prevent_self_review: false,
          can_admins_bypass: false,
          deployment_branch_policy: { protected_branches: false, custom_branch_policies: true },
        });
        return record(invocation);
      },
      [`POST ${ENVIRONMENT}/deployment-branch-policies`]: (invocation) => {
        expect(invocation.args.slice(4)).toEqual(["-f", "name=main", "-f", "type=branch"]);
        return record(invocation);
      },
    });
    expect(applyStep(scripted.context, "github-settings", "github-settings", REVISION)).toBe(0);
    expect(changes).toEqual([
      `PUT ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`,
      `PUT ${ENVIRONMENT}`,
      `POST ${ENVIRONMENT}/deployment-branch-policies`,
    ]);
  });

  it("never deletes a branch rule it did not add", () => {
    const { status, captured } = apply(
      {
        [`GET ${ENVIRONMENT}/deployment-branch-policies`]: json({
          branch_policies: [{ name: "*", type: "branch" }],
        }),
      },
      "github-settings",
    );
    expect(status).toBe(1);
    expect(captured.every(readsOnly)).toBe(true);
    expect(refusals()).toContain("setup never deletes them");
  });

  it("stops at a refused change, leaving the postcondition unmet", () => {
    const { status } = apply(
      {
        [`GET ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: json({
          approval_policy: "never",
        }),
        [`PUT ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: failed(
          "gh: Must have admin rights (HTTP 403)",
          1,
        ),
      },
      "github-settings",
    );
    expect(status).toBe(1);
    expect(refusals()).toContain(
      `gh api --method PUT ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval failed: gh: Must have admin rights (HTTP 403)`,
    );
  });

  it("is refused for another repository", () => {
    expect(
      apply(
        { [`GET ${REPOSITORY}`]: json({ full_name: "someone/fork", default_branch: "main" }) },
        "github-settings",
      ).status,
    ).toBe(1);
  });
});

describe("the settings-token step", () => {
  it("hands the secret's value from the terminal straight to gh, into the deploy environment only", () => {
    const { status, attached } = apply({}, "settings-token");
    expect(status).toBe(0);
    expect(attached).toEqual([
      {
        program: "gh",
        args: [
          "secret",
          "set",
          "REPOSITORY_SETTINGS_READ_TOKEN",
          "--repo",
          ANCHORS.repository,
          "--env",
          "aws-deploy",
        ],
      },
    ]);
  });

  it("needs the protected environment first", () => {
    expect(
      apply({ [`GET ${ENVIRONMENT}`]: failed("gh: Not Found (HTTP 404)", 1) }, "settings-token")
        .status,
    ).toBe(1);
  });
});
