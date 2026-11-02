import { describe, expect, it } from "vitest";
import { ACCESS_STACK_NAME, BOOTSTRAP_STACK_NAME, ENVIRONMENT_STACK_NAME } from "../src/trust.ts";
import {
  BOOTSTRAP_VARIANT,
  BootstrapTemplateError,
  narrowedBootstrapTemplate,
  pinnedBootstrapTemplate,
} from "../tools/bootstrap-template.ts";
import { allowed } from "./policy-evaluation.ts";
import { ANCHORS } from "./rollout-world.ts";

type Template = Record<string, Record<string, Record<string, unknown>>>;

const pinned = pinnedBootstrapTemplate() as Template;
const narrowed = narrowedBootstrapTemplate(pinned, ANCHORS) as Template;

function properties(template: Template, name: string): Record<string, unknown> {
  return template["Resources"]?.[name]?.["Properties"] as Record<string, unknown>;
}

function deployStatements(template: Template): Record<string, unknown>[] {
  const [policy] = properties(template, "DeploymentActionRole")["Policies"] as {
    PolicyDocument: { Statement: Record<string, unknown>[] };
  }[];
  return policy?.PolicyDocument.Statement ?? [];
}

describe("the pinned bootstrap template", () => {
  it("trusts the whole account and administers through its default execution role", () => {
    const trust = properties(pinned, "DeploymentActionRole")["AssumeRolePolicyDocument"] as {
      Statement: { Principal?: { AWS?: unknown } }[];
    };
    expect(trust.Statement[0]?.Principal?.AWS).toEqual({ Ref: "AWS::AccountId" });
    expect(
      JSON.stringify(properties(pinned, "CloudFormationExecutionRole")["ManagedPolicyArns"]),
    ).toContain("AdministratorAccess");
    expect(
      allowed(
        deployStatements(pinned),
        "cloudformation:UpdateStack",
        ANCHORS.stackArn(ACCESS_STACK_NAME),
      ),
    ).toBe(true);
  });
});

describe("the narrowed bootstrap template", () => {
  it("declares its own variant, so a default bootstrap cannot replace it unnoticed", () => {
    expect(narrowed["Parameters"]?.["BootstrapVariant"]?.["Default"]).toBe(BOOTSTRAP_VARIANT);
  });

  it("lets only the deploy role assume any bootstrap role", () => {
    for (const role of [
      "DeploymentActionRole",
      "FilePublishingRole",
      "ImagePublishingRole",
      "LookupRole",
    ]) {
      expect(properties(narrowed, role)["AssumeRolePolicyDocument"]).toEqual({
        Version: "2012-10-17",
        Statement: [
          {
            Effect: "Allow",
            Principal: { AWS: ANCHORS.deployRoleArn },
            Action: ["sts:AssumeRole", "sts:TagSession"],
            Condition: { Null: { "sts:ExternalId": "true" } },
          },
        ],
      });
    }
  });

  it("lets the bootstrap deploy role change the environment stack alone, and never delete it", () => {
    const statements = deployStatements(narrowed);
    const environment = ANCHORS.stackArn(ENVIRONMENT_STACK_NAME).replace("*", "abc");
    for (const action of [
      "CreateChangeSet",
      "ExecuteChangeSet",
      "UpdateStack",
      "UpdateTerminationProtection",
    ]) {
      expect(allowed(statements, `cloudformation:${action}`, environment)).toBe(true);
    }
    for (const stack of [ACCESS_STACK_NAME, BOOTSTRAP_STACK_NAME, "SomeOtherStack"]) {
      const arn = ANCHORS.stackArn(stack).replace("*", "abc");
      for (const action of [
        "CreateChangeSet",
        "ExecuteChangeSet",
        "UpdateStack",
        "DeleteStack",
        "CreateStackRefactor",
      ]) {
        expect(allowed(statements, `cloudformation:${action}`, arn), `${action} on ${stack}`).toBe(
          false,
        );
      }
    }
    expect(allowed(statements, "cloudformation:DeleteStack", environment)).toBe(false);
    expect(allowed(statements, "s3:PutObject", "arn:aws:s3:::someone-elses-bucket/key")).toBe(
      false,
    );
    expect(allowed(statements, "sts:GetCallerIdentity", "*")).toBe(true);
    expect(statements.map((statement) => statement["Sid"])).toEqual([
      "DeployEnvironmentStack",
      undefined,
      "CliStagingBucket",
      "ReadVersion",
      "ReadIdentity",
      "LeaveTrustStacksAlone",
    ]);
  });

  it("passes only the execution role, which always holds the supplied policy and boundary", () => {
    const passing = deployStatements(narrowed).find(
      (statement) => statement["Action"] === "iam:PassRole",
    );
    expect(passing?.["Resource"]).toEqual({ "Fn::Sub": "${CloudFormationExecutionRole.Arn}" });
    const execution = properties(narrowed, "CloudFormationExecutionRole");
    expect(execution["ManagedPolicyArns"]).toEqual({ Ref: "CloudFormationExecutionPolicies" });
    expect(execution["PermissionsBoundary"]).toEqual({
      "Fn::Sub": "arn:${AWS::Partition}:iam::${AWS::AccountId}:policy/${InputPermissionsBoundary}",
    });
  });

  it("leaves the pinned template itself and everything else unchanged", () => {
    const strip = (template: Template): Template => {
      const copy = structuredClone(template);
      delete copy["Parameters"]?.["BootstrapVariant"];
      for (const role of [
        "DeploymentActionRole",
        "FilePublishingRole",
        "ImagePublishingRole",
        "LookupRole",
        "CloudFormationExecutionRole",
      ]) {
        delete copy["Resources"]?.[role];
      }
      return copy;
    };
    expect(strip(narrowed)).toEqual(strip(pinned));
    expect(JSON.stringify(pinned)).toContain("AdministratorAccess");
  });

  it("refuses a template whose shape changed, so a CLI upgrade needs a new review", () => {
    const changed = (mutate: (template: Template) => void): unknown => {
      const copy = structuredClone(pinned);
      mutate(copy);
      return copy;
    };
    const cases: [unknown, string][] = [
      [null, "expected the template to be an object"],
      [changed((template) => delete template["Parameters"]), "the template's parameters"],
      [
        changed((template) => delete template["Parameters"]?.["BootstrapVariant"]),
        "the BootstrapVariant parameter",
      ],
      [
        changed((template) => delete template["Resources"]?.["LookupRole"]),
        "expected resource LookupRole",
      ],
      [
        changed((template) => {
          const resources = template["Resources"] as Record<string, unknown>;
          resources["LookupRole"] = { Type: "AWS::IAM::User" };
        }),
        "LookupRole to be a AWS::IAM::Role",
      ],
      [
        changed((template) => (properties(template, "DeploymentActionRole")["Policies"] = {})),
        "to be a list",
      ],
      [
        changed((template) => {
          deployStatements(template).push({
            Sid: "Added",
            Effect: "Allow",
            Action: "*",
            Resource: "*",
          });
        }),
        "statements changed to [DeployPermissions",
      ],
      [
        changed(
          (template) =>
            delete properties(template, "CloudFormationExecutionRole")["PermissionsBoundary"],
        ),
        "PermissionsBoundary",
      ],
    ];
    for (const [template, message] of cases) {
      expect(() => narrowedBootstrapTemplate(template, ANCHORS)).toThrow(BootstrapTemplateError);
      expect(() => narrowedBootstrapTemplate(template, ANCHORS)).toThrow(message);
    }
  });
});
