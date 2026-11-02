import { Template } from "aws-cdk-lib/assertions";
import { CONFIGURATION_CONTEXT_KEY, environmentConfiguration } from "../src/configuration.ts";
import { deployRoleConditions } from "../src/access-policies.ts";
import { CONVERGED_ROLE_FACTS } from "../src/role-bootstrap.ts";
import { ROLLOUT_CONTEXT_KEY, rolloutConfiguration } from "../src/rollout-configuration.ts";
import { defineStacks } from "../src/stacks.ts";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  BOUNDARY_POLICY_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_STACK_NAME,
  EXECUTION_POLICY_NAME,
  GITHUB_OIDC_AUDIENCE,
  GITHUB_OIDC_ISSUER,
  trustAnchors,
} from "../src/trust.ts";
import {
  BOOTSTRAP_VARIANT,
  bootstrapPermissions,
  pinnedBootstrapTemplate,
} from "../tools/bootstrap-template.ts";
import {
  DEPLOYMENT_BRANCH_POLICY,
  FORK_APPROVAL_POLICY,
  SETTINGS_TOKEN_SECRET,
} from "../tools/github-assessment.ts";
import { rolloutContext, type RolloutContext } from "../tools/rollout-context.ts";
import type { Completed, Invocation, Shell } from "../tools/shell.ts";
import { committedApp, committedContext } from "./committed-app.ts";

export const CONFIGURATION = environmentConfiguration(
  committedContext()[CONFIGURATION_CONTEXT_KEY],
);
export const ROLLOUT = rolloutConfiguration(committedContext()[ROLLOUT_CONTEXT_KEY], CONFIGURATION);
export const ANCHORS = trustAnchors(CONFIGURATION, ROLLOUT);
export const ACCOUNT = ANCHORS.account;
export const REVISION = "0123456789abcdef0123456789abcdef01234567";
export const REPOSITORY = `repos/${ANCHORS.repository}`;
export const ENVIRONMENT = `${REPOSITORY}/environments/${ROLLOUT.deployEnvironment}`;
export const IMAGE = "ami-0123456789abcdef0";

/** A command's scripted answer: the JSON it prints, a whole result, or a function of the command answering one. */
export type Reply = Completed | { readonly json: unknown } | ((invocation: Invocation) => Reply);

export const json = (value: unknown): Reply => ({ json: value });
export const failed = (stderr: string, status = 254): Reply => ({ status, stdout: "", stderr });
export const ABSENT_STACK = (name: string): Reply =>
  failed(
    `An error occurred (ValidationError) when calling the DescribeStacks operation: Stack with id ${name} does not exist`,
  );

function stack(status: string, extra: Record<string, unknown>): Reply {
  return json({ Stacks: [{ StackStatus: status, EnableTerminationProtection: true, ...extra }] });
}

const trust = (principal: unknown): Reply =>
  json({
    Role: {
      AssumeRolePolicyDocument: {
        Version: "2012-10-17",
        Statement: [{ Effect: "Allow", Principal: principal, Action: "sts:AssumeRole" }],
      },
    },
  });

interface PolicyResource {
  readonly Type: string;
  readonly Properties: {
    readonly ManagedPolicyName?: string;
    readonly PolicyDocument?: unknown;
    readonly Policies?: readonly { PolicyDocument: unknown }[];
  };
}

/** The access stack's policy documents as CloudFormation hands them to IAM: synthesized, not as authored. */
const ACCESS_RESOURCES = Object.values(
  Template.fromStack(defineStacks(committedApp()).access).toJSON()["Resources"] as Record<
    string,
    PolicyResource
  >,
);
const managedDocument = (name: string): unknown =>
  ACCESS_RESOURCES.find((resource) => resource.Properties.ManagedPolicyName === name)?.Properties
    .PolicyDocument;
const DEPLOY_ROLE_POLICY = ACCESS_RESOURCES.find((resource) => resource.Type === "AWS::IAM::Role")
  ?.Properties.Policies?.[0]?.PolicyDocument;

/** The bootstrap's file-asset encryption as the pinned CLI chooses it on a first bootstrap. */
export const BOOTSTRAP_KEY = { keyId: "AWS_MANAGED_KEY", keyArn: "AWS_MANAGED_KEY" } as const;
export const BOOTSTRAP_PERMISSIONS = bootstrapPermissions(
  pinnedBootstrapTemplate(),
  ANCHORS,
  BOOTSTRAP_KEY,
);

/** The reads naming role *name*'s inline policies, their documents, and its managed policies. */
function rolePolicies(
  name: string,
  inline: Readonly<Record<string, unknown>>,
  managed: readonly string[],
): Record<string, Reply> {
  return {
    [`iam list-role-policies --role-name ${name}`]: json({ PolicyNames: Object.keys(inline) }),
    ...Object.fromEntries(
      Object.entries(inline).map(([policy, document]) => [
        `iam get-role-policy --role-name ${name} --policy-name ${policy}`,
        json({ RoleName: name, PolicyName: policy, PolicyDocument: document }),
      ]),
    ),
    [`iam list-attached-role-policies --role-name ${name}`]: json({
      AttachedPolicies: managed.map((arn) => ({ PolicyArn: arn })),
    }),
  };
}

/** The reads of managed policy *arn*'s default version. */
function managedPolicy(arn: string, document: unknown): Record<string, Reply> {
  return {
    [`iam get-policy --policy-arn ${arn}`]: json({ Policy: { Arn: arn, DefaultVersionId: "v2" } }),
    [`iam get-policy-version --policy-arn ${arn} --version-id v2`]: json({
      PolicyVersion: { Document: document, VersionId: "v2", IsDefaultVersion: true },
    }),
  };
}

/** Every read a fully set-up rollout answers, keyed as {@link replyKey} names commands. */
export function healthyReplies(): Record<string, Reply> {
  const role = (kind: string): string => ANCHORS.bootstrapRoleName(kind as "deploy");
  return {
    "sts get-caller-identity": json({
      Account: ACCOUNT,
      Arn: `arn:aws:sts::${ACCOUNT}:assumed-role/AWSReservedSSO_AdministratorAccess_1/david`,
    }),
    "iam get-open-id-connect-provider": json({
      Url: GITHUB_OIDC_ISSUER,
      ClientIDList: [GITHUB_OIDC_AUDIENCE],
    }),
    "codeconnections get-connection": json({
      Connection: {
        ConnectionStatus: "AVAILABLE",
        ProviderType: "GitHub",
        OwnerAccountId: ACCOUNT,
      },
    }),
    "rds describe-db-engine-versions": json({
      DBEngineVersions: [
        {
          EngineVersion: "18.6",
          ServerlessV2FeaturesSupport: { MinCapacity: 0, MaxCapacity: 256 },
        },
      ],
    }),
    "rds describe-orderable-db-instance-options": json({
      OrderableDBInstanceOptions: [
        {
          StorageType: "aurora",
          SupportsIAMDatabaseAuthentication: true,
          AvailabilityZones: [{ Name: "us-east-2a" }, { Name: "us-east-2b" }],
        },
        {
          StorageType: "aurora-iopt1",
          SupportsIAMDatabaseAuthentication: true,
          AvailabilityZones: [{ Name: "us-east-2c" }],
        },
      ],
    }),
    "ssm get-parameter": json({ Parameter: { Value: IMAGE } }),
    "ec2 describe-images": json({
      Images: [
        {
          State: "available",
          Architecture: "arm64",
          Name: "al2023-ami-2023.9.20261020.0-kernel-6.12-arm64",
        },
      ],
    }),
    "budgets describe-budgets": json({
      Budgets: [
        {
          BudgetName: "parallax-ci-monthly",
          BudgetType: "COST",
          TimeUnit: "MONTHLY",
          BudgetLimit: { Amount: "50.0", Unit: "USD" },
        },
      ],
    }),
    "budgets describe-notifications-for-budget": json({
      Notifications: [
        { NotificationType: "ACTUAL", ComparisonOperator: "GREATER_THAN", Threshold: 85 },
        {
          NotificationType: "FORECASTED",
          ComparisonOperator: "GREATER_THAN",
          Threshold: 100,
          ThresholdType: "PERCENTAGE",
        },
      ],
    }),
    "budgets describe-subscribers-for-notification": json({
      Subscribers: [
        { SubscriptionType: "EMAIL", Address: "owner@example.com" },
        { SubscriptionType: "SNS", Address: "arn:aws:sns:topic" },
      ],
    }),
    [`cloudformation describe-stack-resources --stack-name ${ACCESS_STACK_NAME}`]: json({
      StackResources: [{ ResourceType: "AWS::IAM::Role", PhysicalResourceId: DEPLOY_ROLE_NAME }],
    }),
    [`cloudformation describe-stacks --stack-name ${ACCESS_STACK_NAME}`]: stack("CREATE_COMPLETE", {
      Outputs: [
        { OutputKey: "DeployRoleArn", OutputValue: ANCHORS.deployRoleArn },
        { OutputKey: "ExecutionPolicyArn", OutputValue: ANCHORS.executionPolicyArn },
        { OutputKey: "BoundaryPolicyArn", OutputValue: ANCHORS.boundaryPolicyArn },
      ],
    }),
    [`iam get-role --role-name ${DEPLOY_ROLE_NAME}`]: json({
      Role: {
        AssumeRolePolicyDocument: {
          Version: "2012-10-17",
          Statement: [
            {
              Effect: "Allow",
              Principal: { Federated: ANCHORS.oidcProviderArn },
              Action: "sts:AssumeRoleWithWebIdentity",
              Condition: deployRoleConditions(ANCHORS),
            },
          ],
        },
      },
    }),
    ...rolePolicies(DEPLOY_ROLE_NAME, { deploy: DEPLOY_ROLE_POLICY }, []),
    ...managedPolicy(ANCHORS.executionPolicyArn, managedDocument(EXECUTION_POLICY_NAME)),
    ...managedPolicy(ANCHORS.boundaryPolicyArn, managedDocument(BOUNDARY_POLICY_NAME)),
    [`cloudformation describe-stacks --stack-name ${BOOTSTRAP_STACK_NAME}`]: stack(
      "UPDATE_COMPLETE",
      {
        Parameters: [
          { ParameterKey: "BootstrapVariant", ParameterValue: BOOTSTRAP_VARIANT },
          { ParameterKey: "Qualifier", ParameterValue: ANCHORS.qualifier },
          {
            ParameterKey: "CloudFormationExecutionPolicies",
            ParameterValue: ANCHORS.executionPolicyArn,
          },
          { ParameterKey: "InputPermissionsBoundary", ParameterValue: BOUNDARY_POLICY_NAME },
          { ParameterKey: "FileAssetsBucketKmsKeyId", ParameterValue: BOOTSTRAP_KEY.keyId },
        ],
        Outputs: [{ OutputKey: "FileAssetKeyArn", OutputValue: BOOTSTRAP_KEY.keyArn }],
      },
    ),
    ...Object.fromEntries(
      ["deploy", "file-publishing", "image-publishing", "lookup"].map((kind) => [
        `iam get-role --role-name ${role(kind)}`,
        trust({ AWS: ANCHORS.deployRoleArn }),
      ]),
    ),
    [`iam get-role --role-name ${role("cfn-exec")}`]: json({
      Role: {
        AssumeRolePolicyDocument: BOOTSTRAP_PERMISSIONS.executionTrust,
        PermissionsBoundary: { PermissionsBoundaryArn: ANCHORS.boundaryPolicyArn },
      },
    }),
    ...rolePolicies(
      role("deploy"),
      BOOTSTRAP_PERMISSIONS.deployInline,
      BOOTSTRAP_PERMISSIONS.deployManaged,
    ),
    ...rolePolicies(role("file-publishing"), BOOTSTRAP_PERMISSIONS.filePublishingInline, []),
    ...rolePolicies(role("cfn-exec"), {}, [ANCHORS.executionPolicyArn]),
    [`cloudformation describe-stacks --stack-name ${ENVIRONMENT_STACK_NAME}`]: stack(
      "UPDATE_COMPLETE",
      {
        StackId: `arn:aws:cloudformation:us-east-2:${ACCOUNT}:stack/${ENVIRONMENT_STACK_NAME}/1`,
        LastUpdatedTime: "2026-11-01T00:00:00Z",
        Outputs: [
          { OutputKey: "RoleBootstrapFacts", OutputValue: JSON.stringify(CONVERGED_ROLE_FACTS) },
          { OutputKey: "RoleBootstrapRevision", OutputValue: REVISION },
        ],
      },
    ),
    [`cloudformation describe-stack-resources --stack-name ${ENVIRONMENT_STACK_NAME}`]: json({
      StackResources: [
        { ResourceType: "AWS::RDS::DBCluster", ResourceStatus: "CREATE_COMPLETE" },
        {
          ResourceType: "Custom::RoleBootstrap",
          ResourceStatus: "UPDATE_COMPLETE",
          Timestamp: "2026-11-01T00:00:00Z",
        },
      ],
    }),
    [`ssm get-parameter --name /parallax/ci/aws/test-environment`]: json({
      Parameter: { Version: 3, Value: JSON.stringify({ schema: 1, cluster_id: "parallax-ci" }) },
    }),
    "codebuild batch-get-projects": json({
      projects: [{ name: "parallax-ci", webhook: { filterGroups: [] } }],
    }),
    [`GET ${REPOSITORY}`]: json({ full_name: ANCHORS.repository, default_branch: "main" }),
    [`GET ${REPOSITORY}/actions/permissions/fork-pr-contributor-approval`]: json({
      approval_policy: FORK_APPROVAL_POLICY,
    }),
    [`GET ${ENVIRONMENT}`]: json({
      can_admins_bypass: false,
      deployment_branch_policy: DEPLOYMENT_BRANCH_POLICY,
      protection_rules: [
        { type: "wait_timer" },
        {
          type: "required_reviewers",
          reviewers: [{ type: "User", reviewer: { login: ROLLOUT.reviewer } }],
        },
      ],
    }),
    [`GET ${ENVIRONMENT}/deployment-branch-policies`]: json({
      branch_policies: [{ name: "main", type: "branch" }],
    }),
    [`GET ${REPOSITORY}/actions/oidc/customization/sub`]: json({ use_default: true }),
    [`GET ${ENVIRONMENT}/secrets`]: json({
      secrets: [{ name: "OTHER" }, { name: SETTINGS_TOKEN_SECRET }],
    }),
    [`GET users/${ROLLOUT.reviewer}`]: json({ id: 42 }),
    "git rev-parse HEAD": { status: 0, stdout: `${REVISION}\n`, stderr: "" },
    "git status --porcelain": { status: 0, stdout: "", stderr: "" },
    "git merge-base --is-ancestor HEAD origin/main": { status: 0, stdout: "", stderr: "" },
  };
}

/** How a scripted reply names a command: an AWS read by its arguments, a GitHub call by method and path, git by its arguments. */
export function replyKey(invocation: Invocation): string {
  const { program, args } = invocation;
  if (program === "aws") return args.slice(0, -4).join(" ");
  if (program === "gh" && args[0] === "api") return `${String(args[2])} ${String(args[3])}`;
  return [program, ...args].join(" ");
}

/** The two-word form of a key, for replies that answer every resource of one operation. */
const operation = (key: string): string => key.split(" ").slice(0, 2).join(" ");

export interface World {
  /** The replies in force, which a test may change as the scripted world changes. */
  readonly replies: Record<string, Reply>;
  readonly shell: Shell;
  readonly context: RolloutContext;
  readonly captured: Invocation[];
  readonly attached: Invocation[];
}

/**
 * A scripted outside world: *replies* override the healthy ones, an
 * unscripted command fails, and every attached command exits with what
 * *attach* returns.
 */
export function world(
  replies: Readonly<Record<string, Reply>> = {},
  attach: (invocation: Invocation) => number = () => 0,
  root?: string,
): World {
  const table: Record<string, Reply> = { ...healthyReplies(), ...replies };
  const answer = (reply: Reply, invocation: Invocation): Completed => {
    if (typeof reply === "function") return answer(reply(invocation), invocation);
    return "json" in reply ? { status: 0, stdout: JSON.stringify(reply.json), stderr: "" } : reply;
  };
  const captured: Invocation[] = [];
  const attached: Invocation[] = [];
  const shell: Shell = {
    capture: (invocation) => {
      captured.push(invocation);
      const key = replyKey(invocation);
      return answer(
        table[key] ?? table[operation(key)] ?? failed(`unscripted: ${key}`, 1),
        invocation,
      );
    },
    attach: (invocation) => {
      attached.push(invocation);
      return attach(invocation);
    },
  };
  return { replies: table, shell, context: rolloutContext(shell, root), captured, attached };
}

/** Whether *invocation* only reads: an AWS describe, get, or list; a GitHub GET; or a read-only git query. */
export function readsOnly(invocation: Invocation): boolean {
  const { program, args } = invocation;
  if (program === "aws") return /^(get|describe|list|batch-get)-/.test(String(args[1]));
  if (program === "gh") return args[0] === "api" && args[1] === "--method" && args[2] === "GET";
  return program === "git" && ["rev-parse", "status", "merge-base"].includes(String(args[0]));
}
