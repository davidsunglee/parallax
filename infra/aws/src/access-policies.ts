import { Effect, PolicyDocument, PolicyStatement } from "aws-cdk-lib/aws-iam";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  ENVIRONMENT_STACK_NAME,
  GITHUB_OIDC_AUDIENCE,
  GITHUB_OIDC_ISSUER,
  type TrustAnchors,
} from "./trust.ts";

/** The services an environment deployment creates resources in. */
const ENVIRONMENT_SERVICES = [
  "ec2:*",
  "rds:*",
  "secretsmanager:*",
  "logs:*",
  "cloudwatch:*",
] as const;

/** What reading the source through the existing connection takes, under either service prefix. */
export const SOURCE_USE_ACTIONS = [
  "codeconnections:GetConnection",
  "codeconnections:GetConnectionToken",
  "codeconnections:UseConnection",
  "codestar-connections:GetConnection",
  "codestar-connections:GetConnectionToken",
  "codestar-connections:UseConnection",
] as const;

/** The services an environment-created role is used with. */
const PASSED_TO_SERVICES = [
  "lambda.amazonaws.com",
  "ec2.amazonaws.com",
  "codebuild.amazonaws.com",
] as const;

/** Every service whose key the environment's resources encrypt with. */
function keyServices(region: string): string[] {
  return ["rds", "secretsmanager", "s3"].map((service) => `${service}.${region}.amazonaws.com`);
}

function trustAnchorResources(anchors: TrustAnchors): string[] {
  return [
    anchors.deployRoleArn,
    anchors.bootstrapRolePattern,
    anchors.executionPolicyArn,
    anchors.boundaryPolicyArn,
    anchors.oidcProviderArn,
  ];
}

const serviceLinkedRoles = (anchors: TrustAnchors): string =>
  `arn:aws:iam::${anchors.account}:role/aws-service-role/*`;

function trustStacks(anchors: TrustAnchors): string[] {
  return [anchors.stackArn(ACCESS_STACK_NAME), anchors.stackArn(BOOTSTRAP_STACK_NAME)];
}

/** Who may assume the deploy role: one protected GitHub environment of one repository. */
export function deployRoleConditions(anchors: TrustAnchors): Record<string, unknown> {
  return {
    StringEquals: {
      [`${GITHUB_OIDC_ISSUER}:aud`]: GITHUB_OIDC_AUDIENCE,
      [`${GITHUB_OIDC_ISSUER}:sub`]: anchors.deploySubject,
    },
  };
}

/**
 * The deploy role's whole capability: assume the bootstrap's deploy and
 * file-publishing roles, and read what the deploy workflow checks and records.
 * It can change nothing itself, and no grant elsewhere can widen it to another
 * role, to IAM, or to the stacks that define the trust path.
 */
export function deployRolePolicy(anchors: TrustAnchors): PolicyDocument {
  const deploymentRoles = [
    anchors.bootstrapRoleArn("deploy"),
    anchors.bootstrapRoleArn("file-publishing"),
  ];
  return new PolicyDocument({
    statements: [
      new PolicyStatement({
        sid: "AssumeDeploymentRoles",
        actions: ["sts:AssumeRole"],
        resources: deploymentRoles,
      }),
      new PolicyStatement({
        sid: "CheckOffering",
        actions: [
          "rds:DescribeDBEngineVersions",
          "rds:DescribeOrderableDBInstanceOptions",
          "ec2:DescribeImages",
        ],
        resources: ["*"],
      }),
      new PolicyStatement({
        sid: "ObserveEnvironmentStack",
        actions: ["cloudformation:DescribeStacks", "cloudformation:DescribeStackResources"],
        resources: [anchors.stackArn(ENVIRONMENT_STACK_NAME)],
      }),
      new PolicyStatement({
        sid: "ReadTestEnvironment",
        actions: ["ssm:GetParameter"],
        resources: [anchors.testEnvironmentParameterArn],
      }),
      new PolicyStatement({
        sid: "ObserveRunner",
        actions: ["codebuild:BatchGetProjects"],
        resources: [anchors.runnerProjectArn],
      }),
      new PolicyStatement({
        sid: "AssumeNoOtherRole",
        effect: Effect.DENY,
        actions: ["sts:AssumeRole"],
        notResources: deploymentRoles,
      }),
      new PolicyStatement({
        sid: "AdministerNothing",
        effect: Effect.DENY,
        actions: ["iam:*", "organizations:*", "account:*", "budgets:*"],
        resources: ["*"],
      }),
      new PolicyStatement({
        sid: "LeaveTrustStacksAlone",
        effect: Effect.DENY,
        actions: ["cloudformation:*"],
        resources: trustStacks(anchors),
      }),
    ],
  });
}

/**
 * What the bootstrap's CloudFormation execution role may do on the
 * environment stack's behalf: create and maintain that stack's own resources,
 * and the roles they run as, which must carry the boundary.
 */
export function executionPolicy(anchors: TrustAnchors): PolicyDocument {
  const inRegion = { StringEquals: { "aws:RequestedRegion": anchors.region } };
  const regional = (service: string, resource: string): string =>
    `arn:aws:${service}:${anchors.region}:${anchors.account}:${resource}`;
  return new PolicyDocument({
    statements: [
      new PolicyStatement({
        sid: "EnvironmentServices",
        actions: [...ENVIRONMENT_SERVICES],
        resources: ["*"],
        conditions: inRegion,
      }),
      new PolicyStatement({
        sid: "EnvironmentFunctions",
        actions: ["lambda:*"],
        resources: [anchors.environmentFunctionPattern],
      }),
      new PolicyStatement({
        sid: "RunnerProject",
        actions: ["codebuild:*"],
        resources: [anchors.runnerProjectArn],
      }),
      new PolicyStatement({
        // CloudFormation resolves the stack's SSM-typed BootstrapVersion
        // parameter as this role when it creates a change set.
        sid: "BootstrapVersion",
        actions: ["ssm:GetParameters"],
        resources: [anchors.bootstrapVersionParameterArn],
      }),
      new PolicyStatement({
        sid: "TestEnvironmentRecord",
        actions: ["ssm:*"],
        resources: [regional("ssm", "parameter/parallax/ci/*")],
      }),
      new PolicyStatement({
        sid: "CreateBoundedRoles",
        actions: ["iam:CreateRole", "iam:PutRolePermissionsBoundary"],
        resources: [anchors.environmentRolePattern],
        conditions: { StringEquals: { "iam:PermissionsBoundary": anchors.boundaryPolicyArn } },
      }),
      new PolicyStatement({
        sid: "MaintainEnvironmentRoles",
        actions: [
          "iam:GetRole",
          "iam:DeleteRole",
          "iam:UpdateRole",
          "iam:UpdateRoleDescription",
          "iam:UpdateAssumeRolePolicy",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:ListRoleTags",
          "iam:GetRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:ListRolePolicies",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
        ],
        resources: [anchors.environmentRolePattern],
      }),
      new PolicyStatement({
        sid: "EnvironmentInstanceProfiles",
        actions: [
          "iam:GetInstanceProfile",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:TagInstanceProfile",
          "iam:UntagInstanceProfile",
        ],
        resources: [anchors.environmentInstanceProfilePattern],
      }),
      new PolicyStatement({
        sid: "PassEnvironmentRoles",
        actions: ["iam:PassRole"],
        resources: [anchors.environmentRolePattern],
        conditions: { StringEquals: { "iam:PassedToService": [...PASSED_TO_SERVICES] } },
      }),
      new PolicyStatement({
        // RDS's role for the cluster, and CloudWatch's role for the NAT
        // instance's recover alarm action, each created on first use.
        sid: "ServiceLinkedRoles",
        actions: ["iam:CreateServiceLinkedRole"],
        resources: [serviceLinkedRoles(anchors)],
        conditions: {
          StringEquals: { "iam:AWSServiceName": ["rds.amazonaws.com", "events.amazonaws.com"] },
        },
      }),
      new PolicyStatement({
        sid: "AssetCode",
        actions: ["s3:GetObject"],
        resources: [`${anchors.stagingBucketArn}/*`],
      }),
      new PolicyStatement({
        sid: "ServiceKeys",
        actions: ["kms:DescribeKey", "kms:CreateGrant", "kms:Decrypt", "kms:GenerateDataKey*"],
        resources: ["*"],
        conditions: { StringEquals: { "kms:ViaService": keyServices(anchors.region) } },
      }),
      new PolicyStatement({
        sid: "SourceConnection",
        actions: [
          ...SOURCE_USE_ACTIONS,
          "codeconnections:PassConnection",
          "codestar-connections:PassConnection",
        ],
        resources: [anchors.sourceConnectionArn],
      }),
    ],
  });
}

/**
 * The most the execution role, and every role the environment stack creates,
 * may ever do. It admits only the environment's services, and IAM only over the
 * environment's own roles and instance profiles, so no role it bounds can
 * change an identity it does not own. It refuses whatever could reach the trust
 * path: its roles, policies, provider, connection, and stacks; a role without
 * this boundary; passing any role the environment does not own; and new
 * long-lived identities.
 */
export function boundaryPolicy(anchors: TrustAnchors): PolicyDocument {
  return new PolicyDocument({
    statements: [
      new PolicyStatement({
        sid: "EnvironmentCeiling",
        actions: [
          ...ENVIRONMENT_SERVICES,
          "lambda:*",
          "codebuild:*",
          "ssm:*",
          "rds-db:connect",
          "rds-data:ExecuteStatement",
          "s3:GetObject",
          "kms:DescribeKey",
          "kms:CreateGrant",
          "kms:Decrypt",
          "kms:GenerateDataKey*",
          ...SOURCE_USE_ACTIONS,
          "codeconnections:PassConnection",
          "codestar-connections:PassConnection",
        ],
        resources: ["*"],
      }),
      new PolicyStatement({
        sid: "EnvironmentIdentities",
        actions: ["iam:*"],
        resources: [anchors.environmentRolePattern, anchors.environmentInstanceProfilePattern],
      }),
      new PolicyStatement({
        sid: "ServiceLinkedRoles",
        actions: ["iam:CreateServiceLinkedRole"],
        resources: [serviceLinkedRoles(anchors)],
      }),
      new PolicyStatement({
        sid: "ProtectTrustAnchors",
        effect: Effect.DENY,
        actions: ["*"],
        resources: trustAnchorResources(anchors),
      }),
      new PolicyStatement({
        sid: "ProtectTrustStacks",
        effect: Effect.DENY,
        actions: ["cloudformation:*"],
        resources: trustStacks(anchors),
      }),
      new PolicyStatement({
        sid: "KeepSourceConnection",
        effect: Effect.DENY,
        actions: [
          "codeconnections:DeleteConnection",
          "codeconnections:UpdateConnectionInstallation",
          "codestar-connections:DeleteConnection",
          "codestar-connections:UpdateConnectionInstallation",
        ],
        resources: [anchors.sourceConnectionArn],
      }),
      new PolicyStatement({
        sid: "RequireBoundary",
        effect: Effect.DENY,
        actions: ["iam:CreateRole", "iam:PutRolePermissionsBoundary"],
        resources: ["*"],
        conditions: { StringNotEquals: { "iam:PermissionsBoundary": anchors.boundaryPolicyArn } },
      }),
      new PolicyStatement({
        sid: "KeepBoundaries",
        effect: Effect.DENY,
        actions: ["iam:DeleteRolePermissionsBoundary", "iam:DeleteUserPermissionsBoundary"],
        resources: ["*"],
      }),
      new PolicyStatement({
        sid: "PassOnlyEnvironmentRoles",
        effect: Effect.DENY,
        actions: ["iam:PassRole"],
        notResources: [anchors.environmentRolePattern],
      }),
      new PolicyStatement({
        sid: "NoNewIdentities",
        effect: Effect.DENY,
        actions: [
          "iam:CreateUser",
          "iam:CreateAccessKey",
          "iam:CreateLoginProfile",
          "iam:UpdateLoginProfile",
          "iam:CreateOpenIDConnectProvider",
          "iam:CreateSAMLProvider",
          "iam:CreatePolicyVersion",
          "iam:SetDefaultPolicyVersion",
        ],
        resources: ["*"],
      }),
    ],
  });
}
