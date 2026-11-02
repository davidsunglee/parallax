import { NAT_IMAGE_PARAMETER } from "../src/environment-stack.ts";
import { TEST_ENVIRONMENT_PARAMETER } from "../src/test-environment.ts";
import { ENVIRONMENT_STACK_NAME, RUNNER_PROJECT_NAME } from "../src/trust.ts";
import { CDK_CLI, type RolloutContext } from "./rollout-context.ts";
import { readLine } from "./shell.ts";

/**
 * Deploy the environment stack, and only it, from the assembly the isolated
 * build synthesized, as the checked-out *revision*, supplying the reviewed
 * NAT image.
 *
 * Exit codes: 0 — deployed; 1 — refused; otherwise the CLI's own status.
 */
export function deploy(context: RolloutContext, revision: string): number {
  const head = readLine(context.shell, {
    program: "git",
    args: ["rev-parse", "HEAD"],
    cwd: context.root,
  });
  const image = context.inputs.natInstanceImage;
  if (head !== revision || image === null) {
    console.error(
      head === revision
        ? "deploy: refused; no reviewed natInstanceImage is committed"
        : `deploy: refused; HEAD is ${head}, not ${revision}`,
    );
    return 1;
  }
  return context.shell.attach({
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
      "--ci",
      "--no-notices",
      "--progress",
      "events",
      "--parameters",
      `${ENVIRONMENT_STACK_NAME}:${NAT_IMAGE_PARAMETER}=${image}`,
    ],
    cwd: context.root,
  });
}

/** What one protected deployment left behind, as the rollout's record of it. */
export interface RolloutEvidence {
  readonly revision: string;
  readonly runUrl: string;
  readonly stack: { name: string; id: string; status: string; updated: string };
  readonly roleBootstrap: { status: string; updated: string };
  readonly testEnvironment: {
    parameter: string;
    version: number;
    schema: unknown;
    clusterId: unknown;
  };
  readonly runner: { project: string; webhook: boolean };
}

const COMPLETE = /^(CREATE|UPDATE)_COMPLETE$/;
const STACK = ["--stack-name", ENVIRONMENT_STACK_NAME];

function stackEvidence(context: RolloutContext): RolloutEvidence["stack"] {
  const { Stacks: [stack = {}] = [] } = context.read.aws([
    "cloudformation",
    "describe-stacks",
    ...STACK,
  ]) as {
    Stacks?: readonly {
      StackId?: string;
      StackStatus?: string;
      LastUpdatedTime?: string;
      CreationTime?: string;
    }[];
  };
  return {
    name: ENVIRONMENT_STACK_NAME,
    id: String(stack.StackId),
    status: String(stack.StackStatus),
    updated: String(stack.LastUpdatedTime ?? stack.CreationTime),
  };
}

function roleBootstrapEvidence(context: RolloutContext): RolloutEvidence["roleBootstrap"] {
  const { StackResources: resources = [] } = context.read.aws([
    "cloudformation",
    "describe-stack-resources",
    ...STACK,
  ]) as {
    StackResources?: readonly {
      ResourceType?: string;
      ResourceStatus?: string;
      Timestamp?: string;
    }[];
  };
  const bootstrap = resources.find((resource) => resource.ResourceType === "Custom::AWS");
  return { status: String(bootstrap?.ResourceStatus), updated: String(bootstrap?.Timestamp) };
}

function testEnvironmentEvidence(context: RolloutContext): RolloutEvidence["testEnvironment"] {
  const { Parameter: parameter } = context.read.aws([
    "ssm",
    "get-parameter",
    "--name",
    TEST_ENVIRONMENT_PARAMETER,
  ]) as {
    Parameter?: { Version?: number; Value?: string };
  };
  const record = JSON.parse(parameter?.Value ?? "{}") as { schema?: unknown; cluster_id?: unknown };
  return {
    parameter: TEST_ENVIRONMENT_PARAMETER,
    version: Number(parameter?.Version),
    schema: record.schema,
    clusterId: record.cluster_id,
  };
}

function runnerEvidence(context: RolloutContext): RolloutEvidence["runner"] {
  const { projects: [project] = [] } = context.read.aws([
    "codebuild",
    "batch-get-projects",
    "--names",
    RUNNER_PROJECT_NAME,
  ]) as {
    projects?: readonly { webhook?: unknown }[];
  };
  return { project: RUNNER_PROJECT_NAME, webhook: project?.webhook !== undefined };
}

function evidenceProblems(evidence: RolloutEvidence): string[] {
  return [
    COMPLETE.test(evidence.stack.status)
      ? undefined
      : `${ENVIRONMENT_STACK_NAME} is ${evidence.stack.status}`,
    COMPLETE.test(evidence.roleBootstrap.status)
      ? undefined
      : `the role bootstrap is ${evidence.roleBootstrap.status}`,
    typeof evidence.testEnvironment.schema === "number"
      ? undefined
      : "the published TestEnvironment names no schema version",
    evidence.runner.webhook ? undefined : `${RUNNER_PROJECT_NAME} has no webhook`,
  ].filter((problem) => problem !== undefined);
}

/** The evidence the deployed environment presents for *revision*, and what it lacks. */
export function rolloutEvidence(
  context: RolloutContext,
  revision: string,
  runUrl: string,
): { evidence: RolloutEvidence; problems: string[] } {
  const evidence: RolloutEvidence = {
    revision,
    runUrl,
    stack: stackEvidence(context),
    roleBootstrap: roleBootstrapEvidence(context),
    testEnvironment: testEnvironmentEvidence(context),
    runner: runnerEvidence(context),
  };
  return { evidence, problems: evidenceProblems(evidence) };
}
