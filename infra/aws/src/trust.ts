import type { EnvironmentConfiguration } from "./configuration.ts";
import type { RolloutConfiguration } from "./rollout-configuration.ts";
import { TEST_ENVIRONMENT_PARAMETER } from "./test-environment.ts";

/** The maintainer-deployed stack owning the deploy identity and its policies. */
export const ACCESS_STACK_NAME = "ParallaxCiAccessStack";
/** The CDK bootstrap stack every environment deployment goes through. */
export const BOOTSTRAP_STACK_NAME = "ParallaxCiBootstrap";
/** The only stack protected CI deploys. */
export const ENVIRONMENT_STACK_NAME = "ParallaxCiEnvironmentStack";

export const DEPLOY_ROLE_NAME = "parallax-ci-deploy";
export const EXECUTION_POLICY_NAME = "parallax-ci-cfn-execution";
export const BOUNDARY_POLICY_NAME = "parallax-ci-boundary";
export const RUNNER_PROJECT_NAME = "parallax-ci";

/** The tag naming the CI environment; a stack-owned budget filters spend on it. */
export const ENVIRONMENT_TAG = ["parallax:environment", "ci"] as const;

/** Cost-allocation tags every resource the CI environment owns carries. */
export const ENVIRONMENT_TAGS: Readonly<Record<string, string>> = Object.fromEntries([
  ["parallax:project", "parallax"],
  ENVIRONMENT_TAG,
]);

export const GITHUB_OIDC_ISSUER = "token.actions.githubusercontent.com";
export const GITHUB_OIDC_AUDIENCE = "sts.amazonaws.com";

/** The roles a CDK bootstrap creates, by the kind its role name carries. */
export type BootstrapRole =
  "deploy" | "file-publishing" | "image-publishing" | "lookup" | "cfn-exec";

/**
 * Every name and ARN the trust path is pinned to, derived once from the
 * environment and rollout configuration so the stacks, the bootstrap
 * template, the workflow, and the setup tools cannot disagree.
 */
export interface TrustAnchors {
  readonly account: string;
  readonly region: string;
  readonly qualifier: string;
  readonly repository: string;
  readonly deploySubject: string;
  readonly oidcProviderArn: string;
  readonly sourceConnectionArn: string;
  readonly deployRoleArn: string;
  readonly executionPolicyArn: string;
  readonly boundaryPolicyArn: string;
  /** Every role a bootstrap with this qualifier creates. */
  readonly bootstrapRolePattern: string;
  /** Every role the environment stack creates: CloudFormation names them after it. */
  readonly environmentRolePattern: string;
  readonly environmentInstanceProfilePattern: string;
  readonly stagingBucketArn: string;
  readonly bootstrapVersionParameterArn: string;
  readonly testEnvironmentParameterArn: string;
  readonly runnerProjectArn: string;
  bootstrapRoleName(role: BootstrapRole): string;
  bootstrapRoleArn(role: BootstrapRole): string;
  /** Every stack ID CloudFormation gives the stack named *name*. */
  stackArn(name: string): string;
}

export function trustAnchors(
  environment: EnvironmentConfiguration,
  rollout: RolloutConfiguration,
): TrustAnchors {
  const { account, region } = environment;
  const qualifier = rollout.bootstrapQualifier;
  const repository = `${rollout.repository.owner}/${rollout.repository.name}`;
  const iam = `arn:aws:iam::${account}`;
  const bootstrapRoleName = (role: BootstrapRole): string =>
    `cdk-${qualifier}-${role}-role-${account}-${region}`;
  return {
    account,
    region,
    qualifier,
    repository,
    deploySubject: `repo:${repository}:environment:${rollout.deployEnvironment}`,
    oidcProviderArn: rollout.oidcProviderArn,
    sourceConnectionArn: rollout.sourceConnectionArn,
    deployRoleArn: `${iam}:role/${DEPLOY_ROLE_NAME}`,
    executionPolicyArn: `${iam}:policy/${EXECUTION_POLICY_NAME}`,
    boundaryPolicyArn: `${iam}:policy/${BOUNDARY_POLICY_NAME}`,
    bootstrapRolePattern: `${iam}:role/cdk-${qualifier}-*`,
    environmentRolePattern: `${iam}:role/${ENVIRONMENT_STACK_NAME}-*`,
    environmentInstanceProfilePattern: `${iam}:instance-profile/${ENVIRONMENT_STACK_NAME}-*`,
    stagingBucketArn: `arn:aws:s3:::cdk-${qualifier}-assets-${account}-${region}`,
    bootstrapVersionParameterArn: `arn:aws:ssm:${region}:${account}:parameter/cdk-bootstrap/${qualifier}/version`,
    testEnvironmentParameterArn: `arn:aws:ssm:${region}:${account}:parameter${TEST_ENVIRONMENT_PARAMETER}`,
    runnerProjectArn: `arn:aws:codebuild:${region}:${account}:project/${RUNNER_PROJECT_NAME}`,
    bootstrapRoleName,
    bootstrapRoleArn: (role) => `${iam}:role/${bootstrapRoleName(role)}`,
    stackArn: (name) => `arn:aws:cloudformation:${region}:${account}:stack/${name}/*`,
  };
}
