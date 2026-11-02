import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { ACCESS_STACK_NAME, BOOTSTRAP_STACK_NAME, BOUNDARY_POLICY_NAME } from "../src/trust.ts";
import {
  accessStackFinding,
  bootstrapFinding,
  identityFinding,
  oidcProviderFinding,
  sourceConnectionFinding,
} from "./aws-assessment.ts";
import {
  BOOTSTRAP_KMS_KEY_ID,
  narrowedBootstrapTemplate,
  pinnedBootstrapTemplate,
} from "./bootstrap-template.ts";
import { budgetFindings, readBudgets } from "./budget-assessment.ts";
import { CHECK, guarded, report, type Finding } from "./findings.ts";
import {
  branchesFinding,
  DEPLOYMENT_BRANCH_POLICY,
  environmentFinding,
  environmentPath,
  FORK_APPROVAL_POLICY,
  forkApprovalFinding,
  repositoryFinding,
  SETTINGS_TOKEN_SECRET,
  tokenFinding,
} from "./github-assessment.ts";
import { CDK_CLI, type RolloutContext } from "./rollout-context.ts";
import { CommandError, readLine, succeeded } from "./shell.ts";

/** One separately authorized setup action: what must already hold, what it does, and what must hold after. */
interface SetupStep {
  /** Findings that must be verified before the step may run. */
  preconditions(context: RolloutContext): Finding[];
  /** Findings that must not be drift or unchecked, though they may be pending. */
  blockers(context: RolloutContext): Finding[];
  /** Runs the step, returning its exit status. */
  run(context: RolloutContext): number;
  postconditions(context: RolloutContext): Finding[];
}

const awsIdentity = (context: RolloutContext): Finding[] =>
  guarded(CHECK.identity, () => identityFinding(context, "maintainer"));

const budget = (context: RolloutContext): Finding[] =>
  guarded(CHECK.budget, () => {
    const { budgets, owned } = readBudgets(context.read, context.anchors.account);
    return budgetFindings(context.rollout.budget, budgets, owned);
  });

/** Run the pinned CDK CLI attached to the terminal, from *cwd*. */
function cdk(context: RolloutContext, args: readonly string[], cwd: string = context.root): number {
  return context.shell.attach({ program: process.execPath, args: [CDK_CLI, ...args], cwd });
}

const accessStack: SetupStep = {
  preconditions: (context) => [
    ...awsIdentity(context),
    ...guarded(CHECK.provider, () => oidcProviderFinding(context)),
    ...guarded(CHECK.connection, () => sourceConnectionFinding(context)),
  ],
  blockers: budget,
  run: (context) => {
    // The build synthesizes in its own isolated environment, so the maintainer's
    // credentials reach only the deploy that follows.
    const built = context.shell.attach({
      program: process.execPath,
      args: [join(dirname(context.root), "tools", "build.ts")],
      cwd: dirname(context.root),
    });
    if (built !== 0) return built;
    return cdk(context, [
      "deploy",
      ACCESS_STACK_NAME,
      "--app",
      "cdk.out",
      "--exclusively",
      "--require-approval",
      "any-change",
      "--no-notices",
    ]);
  },
  postconditions: (context) => guarded(CHECK.accessStack, () => accessStackFinding(context)),
};

const bootstrap: SetupStep = {
  preconditions: (context) => [
    ...awsIdentity(context),
    ...guarded(CHECK.accessStack, () => accessStackFinding(context)),
  ],
  blockers: () => [],
  run: (context) => {
    const { anchors } = context;
    const directory = mkdtempSync(join(tmpdir(), "parallax-bootstrap-"));
    const template = join(directory, "bootstrap-template.json");
    writeFileSync(
      template,
      JSON.stringify(narrowedBootstrapTemplate(pinnedBootstrapTemplate(), anchors), null, 2),
    );
    // Run outside the package so the CLI never synthesizes the app to find environments.
    return cdk(
      context,
      [
        "bootstrap",
        `aws://${anchors.account}/${anchors.region}`,
        "--qualifier",
        anchors.qualifier,
        "--toolkit-stack-name",
        BOOTSTRAP_STACK_NAME,
        "--template",
        template,
        "--cloudformation-execution-policies",
        anchors.executionPolicyArn,
        "--custom-permissions-boundary",
        BOUNDARY_POLICY_NAME,
        "--bootstrap-kms-key-id",
        BOOTSTRAP_KMS_KEY_ID,
        "--termination-protection",
        "--no-previous-parameters",
        "--no-notices",
      ],
      directory,
    );
  },
  postconditions: (context) => guarded(CHECK.bootstrap, () => bootstrapFinding(context)),
};

const githubSettings = (context: RolloutContext): Finding[] => [
  ...guarded(CHECK.forkApproval, () => forkApprovalFinding(context)),
  ...guarded(CHECK.environment, () => environmentFinding(context)),
  ...guarded(CHECK.branches, () => branchesFinding(context)),
];

function gh(context: RolloutContext, args: readonly string[]): void {
  succeeded(context.shell, { program: "gh", args: ["api", ...args] });
}

/** Converge each repository setting that is not yet what the rollout approves, never removing one it did not add. */
function convergeGithub(context: RolloutContext): number {
  const { rollout } = context;
  const repository = `repos/${rollout.repository.owner}/${rollout.repository.name}`;
  const current = new Map(githubSettings(context).map((found) => [found.check, found.state]));
  if (current.get(CHECK.branches) === "drift") {
    console.error(
      `${CHECK.branches}: remove the unapproved branch rules by hand; setup never deletes them`,
    );
    return 1;
  }
  if (current.get(CHECK.forkApproval) !== "verified") {
    gh(context, [
      "--method",
      "PUT",
      `${repository}/actions/permissions/fork-pr-contributor-approval`,
      "-f",
      `approval_policy=${FORK_APPROVAL_POLICY}`,
    ]);
  }
  if (current.get(CHECK.environment) !== "verified") {
    const { id } = context.read.github(`users/${rollout.reviewer}`) as { id?: number };
    const body = join(mkdtempSync(join(tmpdir(), "parallax-environment-")), "environment.json");
    writeFileSync(
      body,
      JSON.stringify({
        reviewers: [{ type: "User", id }],
        prevent_self_review: false,
        can_admins_bypass: false,
        deployment_branch_policy: DEPLOYMENT_BRANCH_POLICY,
      }),
    );
    gh(context, ["--method", "PUT", environmentPath(rollout), "--input", body]);
  }
  if (current.get(CHECK.branches) !== "verified") {
    gh(context, [
      "--method",
      "POST",
      `${environmentPath(rollout)}/deployment-branch-policies`,
      "-f",
      `name=${rollout.deployBranch}`,
      "-f",
      "type=branch",
    ]);
  }
  return 0;
}

const repository = (context: RolloutContext): Finding[] =>
  guarded(CHECK.repository, () => repositoryFinding(context));

const githubSettingsStep: SetupStep = {
  preconditions: repository,
  blockers: () => [],
  run: convergeGithub,
  postconditions: githubSettings,
};

const settingsToken: SetupStep = {
  preconditions: (context) => [
    ...repository(context),
    ...guarded(CHECK.environment, () => environmentFinding(context)),
  ],
  blockers: () => [],
  // The value comes from the terminal or a pipe straight into gh; it never
  // passes through this process, its arguments, or its output.
  run: (context) =>
    context.shell.attach({
      program: "gh",
      args: [
        "secret",
        "set",
        SETTINGS_TOKEN_SECRET,
        "--repo",
        `${context.rollout.repository.owner}/${context.rollout.repository.name}`,
        "--env",
        context.rollout.deployEnvironment,
      ],
    }),
  postconditions: (context) => guarded(CHECK.token, () => tokenFinding(context)),
};

/** Every setup step, by the name `apply` and `--authorize` both take. */
export const SETUP_STEPS: Readonly<Record<string, SetupStep>> = {
  "access-stack": accessStack,
  bootstrap,
  "github-settings": githubSettingsStep,
  "settings-token": settingsToken,
};

/**
 * Whether the checkout is the reviewed revision: *revision* is HEAD, nothing
 * is modified, and HEAD is on the deploy branch as last fetched.
 */
export function revisionProblems(context: RolloutContext, revision: string): string[] {
  const git = (args: readonly string[]) =>
    context.shell.capture({ program: "git", args, cwd: context.root });
  const head = readLine(context.shell, {
    program: "git",
    args: ["rev-parse", "HEAD"],
    cwd: context.root,
  });
  return [
    head === revision ? undefined : `HEAD is ${head}, not the authorized ${revision}`,
    git(["status", "--porcelain"]).stdout.trim() === ""
      ? undefined
      : "the checkout has uncommitted changes",
    git(["merge-base", "--is-ancestor", "HEAD", `origin/${context.rollout.deployBranch}`])
      .status === 0
      ? undefined
      : `HEAD is not on origin/${context.rollout.deployBranch}`,
  ].filter((problem) => problem !== undefined);
}

function refusing(findings: readonly Finding[], allowPending: boolean): Finding[] {
  return findings.filter(
    (found) =>
      found.state === "drift" ||
      found.state === "unavailable" ||
      (!allowPending && found.state === "pending"),
  );
}

function ranStep(step: SetupStep, context: RolloutContext): number {
  try {
    return step.run(context);
  } catch (error) {
    if (!(error instanceof CommandError)) throw error;
    console.error(error.message);
    return 1;
  }
}

/**
 * Run the setup step *name* once its explicit authorization, the reviewed
 * revision, and its preconditions all hold, then require its postconditions.
 *
 * Exit codes: 0 — applied and verified; 1 — refused, failed, or unverified afterwards.
 */
export function applyStep(
  context: RolloutContext,
  name: string,
  authorized: string,
  revision: string,
): number {
  const step = SETUP_STEPS[name];
  if (step === undefined || authorized !== name) {
    console.error(`apply ${name}: refused; each step needs its own --authorize ${name}`);
    return 1;
  }
  const problems = [
    ...revisionProblems(context, revision),
    ...refusing(step.preconditions(context), false).map(
      (found) => `${found.check}: ${found.detail}`,
    ),
    ...refusing(step.blockers(context), true).map((found) => `${found.check}: ${found.detail}`),
  ];
  if (problems.length > 0) {
    for (const problem of problems) console.error(`apply ${name}: refused; ${problem}`);
    return 1;
  }
  const status = ranStep(step, context);
  if (status !== 0) {
    console.error(`apply ${name}: the step exited ${String(status)}`);
    return status;
  }
  return report(step.postconditions(context), []) ? 0 : 1;
}
