import { Template } from "aws-cdk-lib/assertions";
import { describe, expect, it } from "vitest";
import { ACCESS_OUTPUTS } from "../src/access-stack.ts";
import { ROLLOUT_CONTEXT_KEY } from "../src/rollout-configuration.ts";
import { defineStacks } from "../src/stacks.ts";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  BOUNDARY_POLICY_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_STACK_NAME,
  ENVIRONMENT_TAGS,
  EXECUTION_POLICY_NAME,
} from "../src/trust.ts";
import { committedApp, committedContext } from "./committed-app.ts";
import { allowed, allowedWithin } from "./policy-evaluation.ts";
import { ACCOUNT, ANCHORS } from "./rollout-world.ts";

interface Resource {
  readonly Type: string;
  readonly Properties: Record<string, unknown>;
}

const stacks = defineStacks(committedApp());
const template = Template.fromStack(stacks.access);
const resources = template.toJSON()["Resources"] as Record<string, Resource>;

function only(type: string): Resource {
  const found = Object.values(resources).filter((resource) => resource.Type === type);
  if (found.length !== 1 || found[0] === undefined) throw new Error(`expected exactly one ${type}`);
  return found[0];
}

function managedPolicy(name: string): unknown[] {
  const policy = Object.values(resources).find(
    (resource) =>
      resource.Type === "AWS::IAM::ManagedPolicy" &&
      resource.Properties["ManagedPolicyName"] === name,
  );
  return (policy?.Properties["PolicyDocument"] as { Statement: unknown[] }).Statement;
}

const deployRole = only("AWS::IAM::Role").Properties;
const deployPolicy =
  (deployRole["Policies"] as { PolicyDocument: { Statement: unknown[] } }[])[0]?.PolicyDocument
    .Statement ?? [];
const execution = managedPolicy(EXECUTION_POLICY_NAME);
const boundary = managedPolicy(BOUNDARY_POLICY_NAME);

const iam = `arn:aws:iam::${ACCOUNT}`;
const environmentRole = `${iam}:role/${ENVIRONMENT_STACK_NAME}-RunnerProjectRole-ABC`;
const stack = (name: string): string => ANCHORS.stackArn(name).replace("*", "1");
const protectedRoles = [
  ANCHORS.deployRoleArn,
  ...(["deploy", "file-publishing", "image-publishing", "lookup", "cfn-exec"] as const).map(
    (role) => ANCHORS.bootstrapRoleArn(role),
  ),
];
const withBoundary = { "iam:PermissionsBoundary": ANCHORS.boundaryPolicyArn };

describe("the access stack", () => {
  it("is maintainer-deployed, protected from deletion, and needs no bootstrap", () => {
    expect(stacks.access.stackName).toBe(ACCESS_STACK_NAME);
    expect(stacks.access.terminationProtection).toBe(true);
    const json = template.toJSON() as { Parameters?: Record<string, unknown>; Rules?: unknown };
    expect(json.Parameters?.["BootstrapVersion"]).toBeUndefined();
    expect(json.Rules).toBeUndefined();
  });

  it("references the existing GitHub provider rather than creating one", () => {
    expect(
      Object.values(resources).filter(
        (resource) =>
          resource.Type === "AWS::IAM::OIDCProvider" || resource.Type.startsWith("Custom::"),
      ),
    ).toEqual([]);
    expect(
      Object.values(resources)
        .map((resource) => resource.Type)
        .sort(),
    ).toEqual(["AWS::IAM::ManagedPolicy", "AWS::IAM::ManagedPolicy", "AWS::IAM::Role"]);
  });

  it("publishes the pinned role and policy ARNs, and tags what it owns", () => {
    const outputs = template.toJSON()["Outputs"] as Record<string, { Value: unknown }>;
    expect(Object.keys(outputs).sort()).toEqual(Object.values(ACCESS_OUTPUTS).sort());
    expect(deployRole["RoleName"]).toBe(DEPLOY_ROLE_NAME);
    expect(deployRole["Tags"]).toEqual(
      Object.entries(ENVIRONMENT_TAGS)
        .map(([Key, Value]) => ({ Key, Value }))
        .sort((a, b) => a.Key.localeCompare(b.Key)),
    );
    for (const name of [EXECUTION_POLICY_NAME, BOUNDARY_POLICY_NAME]) {
      expect(managedPolicy(name).length).toBeGreaterThan(0);
    }
  });

  it("owns no budget while the manual guardrail is configured", () => {
    expect(
      Object.values(resources).some((resource) => resource.Type === "AWS::Budgets::Budget"),
    ).toBe(false);
  });
});

describe("the deploy role's trust", () => {
  it("admits only the protected environment's tokens, through the existing provider", () => {
    expect(deployRole["AssumeRolePolicyDocument"]).toEqual({
      Version: "2012-10-17",
      Statement: [
        {
          Effect: "Allow",
          Action: "sts:AssumeRoleWithWebIdentity",
          Principal: { Federated: ANCHORS.oidcProviderArn },
          Condition: {
            StringEquals: {
              "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
              "token.actions.githubusercontent.com:sub":
                "repo:davidsunglee/parallax:environment:aws-deploy",
            },
          },
        },
      ],
    });
    expect(deployRole["MaxSessionDuration"]).toBe(3600);
  });
});

describe("the deploy role's permissions", () => {
  it("assume only the bootstrap's deploy and file-publishing roles", () => {
    expect(allowed(deployPolicy, "sts:AssumeRole", ANCHORS.bootstrapRoleArn("deploy"))).toBe(true);
    expect(
      allowed(deployPolicy, "sts:AssumeRole", ANCHORS.bootstrapRoleArn("file-publishing")),
    ).toBe(true);
    for (const role of ["lookup", "image-publishing", "cfn-exec"] as const) {
      expect(allowed(deployPolicy, "sts:AssumeRole", ANCHORS.bootstrapRoleArn(role))).toBe(false);
    }
    expect(
      allowed(deployPolicy, "sts:AssumeRole", `${iam}:role/OrganizationAccountAccessRole`),
    ).toBe(false);
  });

  it("change nothing directly: no IAM, no stack, no budget, no organization", () => {
    for (const [action, resource] of [
      ["iam:UpdateAssumeRolePolicy", ANCHORS.deployRoleArn],
      ["iam:PutRolePolicy", ANCHORS.deployRoleArn],
      ["iam:PassRole", ANCHORS.bootstrapRoleArn("cfn-exec")],
      ["iam:CreatePolicyVersion", ANCHORS.boundaryPolicyArn],
      ["cloudformation:UpdateStack", stack(ACCESS_STACK_NAME)],
      ["cloudformation:DeleteStack", stack(BOOTSTRAP_STACK_NAME)],
      ["cloudformation:UpdateStack", stack(ENVIRONMENT_STACK_NAME)],
      ["cloudformation:DescribeStacks", stack(ACCESS_STACK_NAME)],
      ["budgets:ModifyBudget", "*"],
      ["ssm:PutParameter", ANCHORS.testEnvironmentParameterArn],
      ["secretsmanager:GetSecretValue", "*"],
    ]) {
      expect(
        allowed(deployPolicy, String(action), String(resource)),
        `${String(action)} ${String(resource)}`,
      ).toBe(false);
    }
  });

  it("read what the deploy workflow checks and records", () => {
    for (const [action, resource] of [
      ["rds:DescribeDBEngineVersions", "*"],
      ["rds:DescribeOrderableDBInstanceOptions", "*"],
      ["ec2:DescribeImages", "*"],
      ["cloudformation:DescribeStacks", stack(ENVIRONMENT_STACK_NAME)],
      ["cloudformation:DescribeStackResources", stack(ENVIRONMENT_STACK_NAME)],
      ["ssm:GetParameter", ANCHORS.testEnvironmentParameterArn],
      ["codebuild:BatchGetProjects", ANCHORS.runnerProjectArn],
    ]) {
      expect(allowed(deployPolicy, String(action), String(resource)), String(action)).toBe(true);
    }
  });
});

describe("the bounded execution role", () => {
  const may = (action: string, resource: string, context = {}): boolean =>
    allowedWithin(execution, boundary, action, resource, context);

  it("creates and maintains the environment's resources and bounded roles", () => {
    const inRegion = { "aws:RequestedRegion": "us-east-2" };
    expect(may("ec2:RunInstances", "*", inRegion)).toBe(true);
    expect(may("rds:CreateDBCluster", "*", inRegion)).toBe(true);
    expect(may("ec2:RunInstances", "*", { "aws:RequestedRegion": "us-east-1" })).toBe(false);
    expect(may("iam:CreateRole", environmentRole, withBoundary)).toBe(true);
    expect(may("iam:PutRolePolicy", environmentRole)).toBe(true);
    expect(
      may("iam:PassRole", environmentRole, { "iam:PassedToService": "codebuild.amazonaws.com" }),
    ).toBe(true);
    expect(
      may(
        "lambda:CreateFunction",
        `arn:aws:lambda:us-east-2:${ACCOUNT}:function:${ENVIRONMENT_STACK_NAME}-AWS679`,
      ),
    ).toBe(true);
    expect(may("codebuild:CreateProject", ANCHORS.runnerProjectArn)).toBe(true);
    expect(may("ssm:PutParameter", ANCHORS.testEnvironmentParameterArn)).toBe(true);
    expect(may("s3:GetObject", `${ANCHORS.stagingBucketArn}/asset.zip`)).toBe(true);
    expect(may("codeconnections:PassConnection", ANCHORS.sourceConnectionArn)).toBe(true);
    expect(
      may(
        "iam:CreateServiceLinkedRole",
        `${iam}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS`,
        {
          "iam:AWSServiceName": "rds.amazonaws.com",
        },
      ),
    ).toBe(true);
  });

  it("cannot reach the trust path, directly or by delegation", () => {
    for (const role of protectedRoles) {
      for (const action of [
        "iam:UpdateAssumeRolePolicy",
        "iam:PutRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DeleteRole",
        "iam:PassRole",
      ]) {
        expect(
          may(action, role, { "iam:PassedToService": "lambda.amazonaws.com" }),
          `${action} ${role}`,
        ).toBe(false);
      }
    }
    for (const policy of [ANCHORS.boundaryPolicyArn, ANCHORS.executionPolicyArn]) {
      expect(may("iam:CreatePolicyVersion", policy)).toBe(false);
      expect(may("iam:DeletePolicy", policy)).toBe(false);
    }
    expect(may("iam:UpdateOpenIDConnectProviderThumbprint", ANCHORS.oidcProviderArn)).toBe(false);
    for (const name of [ACCESS_STACK_NAME, BOOTSTRAP_STACK_NAME]) {
      expect(may("cloudformation:UpdateStack", stack(name))).toBe(false);
    }
    expect(may("codeconnections:DeleteConnection", ANCHORS.sourceConnectionArn)).toBe(false);
    expect(may("budgets:ModifyBudget", "*")).toBe(false);
  });

  it("creates no unbounded role, removes no boundary, and passes no role it does not own", () => {
    expect(may("iam:CreateRole", environmentRole)).toBe(false);
    expect(
      may("iam:CreateRole", environmentRole, { "iam:PermissionsBoundary": `${iam}:policy/Other` }),
    ).toBe(false);
    expect(may("iam:CreateRole", `${iam}:role/Escalator`, withBoundary)).toBe(false);
    expect(may("iam:DeleteRolePermissionsBoundary", environmentRole)).toBe(false);
    expect(
      may("iam:PassRole", environmentRole, {
        "iam:PassedToService": "cloudformation.amazonaws.com",
      }),
    ).toBe(false);
    expect(
      may("iam:PassRole", `${iam}:role/Admin`, { "iam:PassedToService": "lambda.amazonaws.com" }),
    ).toBe(false);
    expect(may("iam:CreateUser", `${iam}:user/backdoor`)).toBe(false);
    expect(may("iam:CreateAccessKey", `${iam}:user/backdoor`)).toBe(false);
    expect(may("sts:AssumeRole", ANCHORS.deployRoleArn)).toBe(false);
    expect(
      may("lambda:UpdateFunctionCode", `arn:aws:lambda:us-east-2:${ACCOUNT}:function:Elsewhere`),
    ).toBe(false);
  });
});

describe("the boundary on environment roles", () => {
  const bounded = (action: string, resource: string, context = {}): boolean =>
    allowedWithin(
      [{ Effect: "Allow", Action: "*", Resource: "*" }],
      boundary,
      action,
      resource,
      context,
    );

  it("caps even an administrator-like identity policy at the environment's services", () => {
    expect(bounded("rds-db:connect", "*")).toBe(true);
    expect(bounded("iam:UpdateAssumeRolePolicy", ANCHORS.deployRoleArn)).toBe(false);
    expect(bounded("iam:PassRole", ANCHORS.bootstrapRoleArn("cfn-exec"))).toBe(false);
    expect(bounded("cloudformation:UpdateStack", stack(ACCESS_STACK_NAME))).toBe(false);
    expect(bounded("organizations:LeaveOrganization", "*")).toBe(false);
    expect(bounded("sts:AssumeRole", ANCHORS.bootstrapRoleArn("deploy"))).toBe(false);
    expect(bounded("iam:CreateRole", environmentRole)).toBe(false);
  });

  it("lets an environment role granted administrator access change no identity the environment does not own", () => {
    expect(
      allowedWithin(execution, boundary, "iam:AttachRolePolicy", environmentRole, {
        "iam:PolicyARN": "arn:aws:iam::aws:policy/AdministratorAccess",
      }),
    ).toBe(true);
    const existingAdministrators = [
      `${iam}:role/OrganizationAccountAccessRole`,
      `${iam}:role/aws-reserved/sso.amazonaws.com/us-east-2/AWSReservedSSO_AdministratorAccess_1`,
    ];
    for (const role of existingAdministrators) {
      for (const action of [
        "iam:UpdateAssumeRolePolicy",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
      ]) {
        expect(bounded(action, role), `${action} ${role}`).toBe(false);
      }
    }
    for (const [action, resource] of [
      ["iam:CreatePolicy", `${iam}:policy/Escalator`],
      ["iam:AttachUserPolicy", `${iam}:user/someone`],
      ["iam:PutGroupPolicy", `${iam}:group/Admins`],
      ["iam:AddUserToGroup", `${iam}:group/Admins`],
    ] as const) {
      expect(bounded(action, resource), `${action} ${resource}`).toBe(false);
    }
    expect(bounded("iam:PutRolePolicy", environmentRole)).toBe(true);
    expect(
      bounded(
        "iam:AddRoleToInstanceProfile",
        `${iam}:instance-profile/${ENVIRONMENT_STACK_NAME}-Nat`,
      ),
    ).toBe(true);
    expect(
      bounded(
        "iam:CreateServiceLinkedRole",
        `${iam}:role/aws-service-role/rds.amazonaws.com/AWSServiceRoleForRDS`,
      ),
    ).toBe(true);
  });

  it("fits the managed policy size limit", () => {
    for (const statements of [execution, boundary]) {
      expect(
        JSON.stringify({ Version: "2012-10-17", Statement: statements }).replace(/\s/g, "").length,
      ).toBeLessThan(6144);
    }
  });
});

describe("a stack-owned budget", () => {
  it("alerts on actual and forecast spend over the tagged environment once configured", () => {
    const context = committedContext();
    const rollout = context[ROLLOUT_CONTEXT_KEY] as Record<string, unknown>;
    const owned = defineStacks(
      committedApp({
        [ROLLOUT_CONTEXT_KEY]: {
          ...rollout,
          budget: {
            ownership: "stack",
            name: "parallax-ci-tagged",
            limitUsd: 50,
            recipients: ["owner@example.com"],
          },
        },
      }),
    ).access;
    const subscribers = [{ SubscriptionType: "EMAIL", Address: "owner@example.com" }];
    const notification = (type: string) => ({
      Notification: {
        NotificationType: type,
        ComparisonOperator: "GREATER_THAN",
        Threshold: 100,
        ThresholdType: "PERCENTAGE",
      },
      Subscribers: subscribers,
    });
    Template.fromStack(owned).hasResourceProperties("AWS::Budgets::Budget", {
      Budget: {
        BudgetName: "parallax-ci-tagged",
        BudgetType: "COST",
        TimeUnit: "MONTHLY",
        BudgetLimit: { Amount: 50, Unit: "USD" },
        CostFilters: { TagKeyValue: ["user:parallax:environment$ci"] },
      },
      NotificationsWithSubscribers: [notification("ACTUAL"), notification("FORECASTED")],
    });
  });
});
