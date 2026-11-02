import { cpSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_STACK_NAME,
} from "../src/trust.ts";
import { CONVERGED_ROLE_FACTS } from "../src/role-bootstrap.ts";
import { rolloutEvidence } from "../tools/deployment.ts";
import { LIVE_PROOFS, main } from "../tools/rollout.ts";
import { CDK_CLI, deployInputs, PACKAGE_ROOT } from "../tools/rollout-context.ts";
import type { Invocation } from "../tools/shell.ts";
import { PACKAGE_ROOT as TEST_PACKAGE_ROOT } from "./committed-app.ts";
import {
  ABSENT_STACK,
  ACCOUNT,
  failed,
  IMAGE,
  json,
  readsOnly,
  REVISION,
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

/** A copy of the package's committed inputs, with the reviewed NAT image set to *image*. */
function packageWithImage(image: string | null): string {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "parallax-rollout-")));
  cpSync(join(TEST_PACKAGE_ROOT, "cdk.json"), join(root, "cdk.json"));
  writeFileSync(join(root, "deploy-inputs.json"), JSON.stringify({ natInstanceImage: image }));
  return root;
}

const DEPLOY_CALLER: Record<string, Reply> = {
  "sts get-caller-identity": json({
    Account: ACCOUNT,
    Arn: `arn:aws:sts::${ACCOUNT}:assumed-role/${DEPLOY_ROLE_NAME}/infra-deploy`,
  }),
};

function run(
  argv: readonly string[],
  replies: Record<string, Reply> = {},
  root?: string,
  attach?: (invocation: Invocation) => number,
) {
  const scripted = world(replies, attach, root ?? packageWithImage(IMAGE));
  return { ...scripted, status: main(argv, scripted.shell, scripted.context.root) };
}

describe("the deploy inputs", () => {
  it("hold a reviewed image ID, or none yet", () => {
    expect(deployInputs({ natInstanceImage: null })).toEqual({ natInstanceImage: null });
    expect(deployInputs({ natInstanceImage: IMAGE })).toEqual({ natInstanceImage: IMAGE });
    expect(deployInputs({ natInstanceImage: "ami-12345678" })).toEqual({
      natInstanceImage: "ami-12345678",
    });
    for (const value of [{}, null, { natInstanceImage: "ami-xyz" }, { natInstanceImage: 7 }]) {
      expect(() => deployInputs(value)).toThrow("natInstanceImage must be null or an image ID");
    }
  });

  it("are committed with a reviewed image chosen", () => {
    expect(world().context.inputs.natInstanceImage).toMatch(/^ami-/);
    expect(world().context.root).toBe(PACKAGE_ROOT);
  });
});

describe("the preflight", () => {
  it("is the default, only reads, and is ready when every approved input holds", () => {
    const { status, captured, attached } = run([]);
    expect(status).toBe(0);
    expect(attached).toEqual([]);
    expect(captured.length).toBeGreaterThan(20);
    expect(captured.filter((invocation) => !readsOnly(invocation))).toEqual([]);
    const output = printed(log);
    expect(output).toContain(
      "For a human to confirm:\n  budget-recipients: confirm owner@example.com",
    );
    for (const proof of LIVE_PROOFS) expect(output).toContain(proof);
    expect(output).not.toMatch(/^(Pending|Drift|Could not check):/m);
  });

  it("reports every missing input and authorization together", () => {
    const { status, attached } = run(
      ["preflight"],
      {
        [`cloudformation describe-stacks --stack-name ${ACCESS_STACK_NAME}`]:
          ABSENT_STACK(ACCESS_STACK_NAME),
        [`cloudformation describe-stacks --stack-name ${BOOTSTRAP_STACK_NAME}`]:
          ABSENT_STACK(BOOTSTRAP_STACK_NAME),
        [`GET repos/davidsunglee/parallax/environments/aws-deploy`]: failed("HTTP 404", 1),
        [`GET repos/davidsunglee/parallax/environments/aws-deploy/secrets`]: json({ secrets: [] }),
        "budgets describe-budgets": failed("AccessDenied"),
      },
      packageWithImage(null),
    );
    expect(status).toBe(1);
    expect(attached).toEqual([]);
    const output = printed(log);
    for (const expected of [
      "nat-image: commit a reviewed natInstanceImage",
      "access-stack: deploy ParallaxCiAccessStack: apply access-stack",
      "bootstrap: bootstrap ParallaxCiBootstrap: apply bootstrap",
      "deploy-environment: create aws-deploy: apply github-settings",
      "settings-token: place REPOSITORY_SETTINGS_READ_TOKEN: apply settings-token",
      "budget: aws budgets describe-budgets failed: AccessDenied",
    ]) {
      expect(output).toContain(expected);
    }
  });
});

describe("the deploy workflow's gates", () => {
  it("verify the repository protections by reading alone", () => {
    const { status, captured } = run(["verify-github"]);
    expect(status).toBe(0);
    expect(
      captured.every((invocation) => invocation.program === "gh" && readsOnly(invocation)),
    ).toBe(true);
    expect(
      run(["verify-github"], {
        "GET repos/davidsunglee/parallax/actions/oidc/customization/sub": json({
          use_default: false,
        }),
      }).status,
    ).toBe(1);
  });

  it("verify the deploy role, the offering, and the reviewed image", () => {
    expect(run(["verify-aws"], DEPLOY_CALLER).status).toBe(0);
    expect(run(["verify-aws"]).status).toBe(1);
    expect(run(["verify-aws"], DEPLOY_CALLER, packageWithImage(null)).status).toBe(1);
    expect(
      run(["verify-aws"], { ...DEPLOY_CALLER, "rds describe-db-engine-versions": json({}) }).status,
    ).toBe(1);
  });
});

describe("deploying", () => {
  it("deploys only the environment stack, from the synthesized assembly, with the reviewed image and its revision", () => {
    const root = packageWithImage(IMAGE);
    const { status, attached } = run(["deploy", "--revision", REVISION], {}, root, () => 0);
    expect(status).toBe(0);
    expect(attached).toEqual([
      {
        program: process.execPath,
        args: [
          CDK_CLI,
          "deploy",
          ENVIRONMENT_STACK_NAME,
          "--app",
          "cdk.out",
          "--exclusively",
          "--require-approval",
          "never",
          "--no-rollback",
          "--ci",
          "--no-notices",
          "--progress",
          "events",
          "--parameters",
          `${ENVIRONMENT_STACK_NAME}:NatInstanceImage=${IMAGE}`,
          "--parameters",
          `${ENVIRONMENT_STACK_NAME}:DeployedRevision=${REVISION}`,
        ],
        cwd: root,
      },
    ]);
  });

  it("propagates the CLI's failure", () => {
    expect(run(["deploy", "--revision", REVISION], {}, undefined, () => 7).status).toBe(7);
  });

  it("refuses another revision, or no reviewed image", () => {
    const other = run(["deploy", "--revision", "feedface"]);
    expect(other.status).toBe(1);
    expect(other.attached).toEqual([]);
    const unchosen = run(["deploy", "--revision", REVISION], {}, packageWithImage(null));
    expect(unchosen.status).toBe(1);
    expect(unchosen.attached).toEqual([]);
    expect(printed(errors)).toContain(
      "HEAD is 0123456789abcdef0123456789abcdef01234567, not feedface",
    );
    expect(printed(errors)).toContain("no reviewed natInstanceImage is committed");
  });
});

describe("rollout evidence", () => {
  const url = "https://github.com/davidsunglee/parallax/actions/runs/1/attempts/1";

  it("records the deployed revision, stack, role bootstrap, published record, and runner", () => {
    const { status, captured } = run(["evidence", "--revision", REVISION, "--run-url", url]);
    expect(status).toBe(0);
    expect(captured.every(readsOnly)).toBe(true);
    const recorded = JSON.parse(printed(log).replace(/^```json\n|\n```$/g, "")) as unknown;
    expect(recorded).toEqual({
      revision: REVISION,
      runUrl: url,
      stack: {
        name: ENVIRONMENT_STACK_NAME,
        id: `arn:aws:cloudformation:us-east-2:${ACCOUNT}:stack/${ENVIRONMENT_STACK_NAME}/1`,
        status: "UPDATE_COMPLETE",
        updated: "2026-11-01T00:00:00Z",
      },
      roleBootstrap: {
        status: "UPDATE_COMPLETE",
        updated: "2026-11-01T00:00:00Z",
        revision: REVISION,
        facts: CONVERGED_ROLE_FACTS,
      },
      testEnvironment: {
        parameter: "/parallax/ci/aws/test-environment",
        version: 3,
        schema: 1,
        clusterId: "parallax-ci",
      },
      runner: { project: "parallax-ci", webhook: true },
    });
  });

  it("fails on anything incomplete, still printing what it found", () => {
    const { status } = run(["evidence", "--revision", REVISION, "--run-url", url], {
      [`cloudformation describe-stacks --stack-name ${ENVIRONMENT_STACK_NAME}`]: json({
        Stacks: [{ StackStatus: "UPDATE_ROLLBACK_COMPLETE", CreationTime: "t" }],
      }),
      [`cloudformation describe-stack-resources --stack-name ${ENVIRONMENT_STACK_NAME}`]: json({}),
      "ssm get-parameter --name /parallax/ci/aws/test-environment": json({}),
      "codebuild batch-get-projects": json({ projects: [{}] }),
    });
    expect(status).toBe(1);
    expect(printed(log)).toContain('"updated": "t"');
    expect(printed(errors).split("\n")).toEqual([
      `evidence: ${ENVIRONMENT_STACK_NAME} is UPDATE_ROLLBACK_COMPLETE`,
      "evidence: the role bootstrap is undefined",
      `evidence: the role bootstrap last ran for undefined, not ${REVISION}`,
      "evidence: the role bootstrap read back facts other than the converged ones",
      "evidence: the published TestEnvironment names no schema version",
      "evidence: parallax-ci has no webhook",
    ]);
    const empty = world({
      [`cloudformation describe-stacks --stack-name ${ENVIRONMENT_STACK_NAME}`]: json({}),
      "codebuild batch-get-projects": json({}),
    });
    expect(rolloutEvidence(empty.context, REVISION, url).problems).toHaveLength(1 + 2 + 1);
  });

  it("fails unless this revision's bootstrap read back the converged facts", () => {
    const withOutputs = (outputs: Record<string, string>) => ({
      [`cloudformation describe-stacks --stack-name ${ENVIRONMENT_STACK_NAME}`]: json({
        Stacks: [
          {
            StackStatus: "UPDATE_COMPLETE",
            Outputs: Object.entries(outputs).map(([OutputKey, OutputValue]) => ({
              OutputKey,
              OutputValue,
            })),
          },
        ],
      }),
    });
    const problems = (outputs: Record<string, string>) =>
      rolloutEvidence(world(withOutputs(outputs)).context, REVISION, url).problems;
    const converged = JSON.stringify(CONVERGED_ROLE_FACTS);
    expect(problems({ RoleBootstrapFacts: converged, RoleBootstrapRevision: REVISION })).toEqual(
      [],
    );
    expect(problems({ RoleBootstrapFacts: converged, RoleBootstrapRevision: "feedface" })).toEqual([
      `the role bootstrap last ran for feedface, not ${REVISION}`,
    ]);
    for (const facts of [
      JSON.stringify({ ...CONVERGED_ROLE_FACTS, memberships: ["rds_iam"] }),
      "not json",
    ]) {
      expect(problems({ RoleBootstrapFacts: facts, RoleBootstrapRevision: REVISION })).toEqual([
        "the role bootstrap read back facts other than the converged ones",
      ]);
    }
  });
});

describe("the command line", () => {
  it("applies a step only through apply, with its revision", () => {
    expect(
      run(["apply", "settings-token", "--authorize", "settings-token", "--revision", REVISION])
        .status,
    ).toBe(0);
    expect(run(["apply", "settings-token", "--revision", REVISION]).status).toBe(1);
  });

  it.each([
    [["unknown"]],
    [["preflight", "extra"]],
    [["apply"]],
    [["apply", "bootstrap"]],
    [["apply", "bootstrap", "more", "--revision", REVISION]],
    [["deploy"]],
    [["evidence", "--revision", REVISION]],
    [["preflight", "--unknown"]],
  ])("refuses %j as a usage error", (argv) => {
    expect(run(argv).status).toBe(2);
    expect(printed(errors)).toContain("usage: node aws/tools/rollout.ts");
  });
});
