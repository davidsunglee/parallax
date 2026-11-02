import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  ENVIRONMENT_STACK_NAME,
  type TrustAnchors,
} from "../src/trust.ts";

/**
 * The variant the narrowed bootstrap declares. The CDK CLI refuses to replace
 * a bootstrap stack of another variant, so a later default bootstrap cannot
 * silently restore the account-wide trust this one removes.
 */
export const BOOTSTRAP_VARIANT = "Parallax CI: deploy trust narrowed to one role";

/** The roles the pinned template defines and the narrowed one trusts only the deploy role to assume. */
const ASSUMABLE_ROLES = [
  "DeploymentActionRole",
  "FilePublishingRole",
  "ImagePublishingRole",
  "LookupRole",
] as const;

/** Every statement the pinned deploy role policy holds, by Sid; the one without a Sid passes the execution role. */
const PINNED_DEPLOY_STATEMENTS = [
  "DeployPermissions",
  "PipelineCrossAccountArtifactsBucket",
  "PipelineCrossAccountArtifactsKey",
  "",
  "CliPermissions",
  "CliStagingBucket",
  "ReadVersion",
  "Refactor",
];

/** The statements kept unchanged: passing the execution role, reading staged assets, and reading the version. */
const KEPT_DEPLOY_STATEMENTS = new Set(["", "CliStagingBucket", "ReadVersion"]);

/** The template the pinned CDK CLI bootstraps with when given none. */
export function pinnedBootstrapTemplate(): unknown {
  const path = fileURLToPath(
    import.meta.resolve("aws-cdk/lib/api/bootstrap/bootstrap-template.yaml"),
  );
  return parse(readFileSync(path, "utf8"));
}

/** The pinned template no longer has the shape the narrowing was reviewed against. */
export class BootstrapTemplateError extends Error {
  override readonly name = "BootstrapTemplateError";
}

type Node = Record<string, unknown>;

function object(value: unknown, where: string): Node {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new BootstrapTemplateError(`expected ${where} to be an object`);
  }
  return value as Node;
}

function list(value: unknown, where: string): unknown[] {
  if (!Array.isArray(value)) throw new BootstrapTemplateError(`expected ${where} to be a list`);
  return value;
}

function resource(resources: Node, name: string, type: string): Node {
  const found = object(resources[name], `resource ${name}`);
  if (found["Type"] !== type) throw new BootstrapTemplateError(`expected ${name} to be a ${type}`);
  return object(found["Properties"], `${name}'s properties`);
}

function sid(statement: Node): string {
  const value = statement["Sid"];
  return typeof value === "string" ? value : "";
}

function trustOnly(roleArn: string): Node {
  return {
    Version: "2012-10-17",
    Statement: [
      {
        Effect: "Allow",
        Principal: { AWS: roleArn },
        Action: ["sts:AssumeRole", "sts:TagSession"],
        Condition: { Null: { "sts:ExternalId": "true" } },
      },
    ],
  };
}

function deployStatements(policies: unknown, anchors: TrustAnchors): unknown[] {
  const [policy] = list(policies, "DeploymentActionRole's policies").map((entry) =>
    object(entry, "a DeploymentActionRole policy"),
  );
  const document = object(policy?.["PolicyDocument"], "DeploymentActionRole's default policy");
  const statements = list(document["Statement"], "the default policy's statements").map(
    (statement) => object(statement, "a default policy statement"),
  );
  const sids = statements.map((statement) => sid(statement));
  if (JSON.stringify(sids) !== JSON.stringify(PINNED_DEPLOY_STATEMENTS)) {
    throw new BootstrapTemplateError(
      `the deploy role's statements changed to [${sids.join(", ")}]; review the narrowing`,
    );
  }
  return [
    {
      Sid: "DeployEnvironmentStack",
      Effect: "Allow",
      Action: [
        "cloudformation:CreateChangeSet",
        "cloudformation:DeleteChangeSet",
        "cloudformation:DescribeChangeSet",
        "cloudformation:ExecuteChangeSet",
        "cloudformation:CreateStack",
        "cloudformation:UpdateStack",
        "cloudformation:RollbackStack",
        "cloudformation:ContinueUpdateRollback",
        "cloudformation:UpdateTerminationProtection",
      ],
      Resource: anchors.stackArn(ENVIRONMENT_STACK_NAME),
    },
    ...statements.filter((statement) => KEPT_DEPLOY_STATEMENTS.has(sid(statement))),
    { Sid: "ReadIdentity", Effect: "Allow", Action: "sts:GetCallerIdentity", Resource: "*" },
    {
      Sid: "LeaveTrustStacksAlone",
      Effect: "Deny",
      Action: "cloudformation:*",
      Resource: [anchors.stackArn(BOOTSTRAP_STACK_NAME), anchors.stackArn(ACCESS_STACK_NAME)],
    },
  ];
}

/**
 * *template*, the pinned default bootstrap template, narrowed for the trust
 * path: only the deploy role may assume any bootstrap role; the deploy role
 * may change no stack but the environment stack, may not delete it, and loses
 * the default's cross-account and refactoring grants; and the execution role
 * always holds the supplied bounded policy and boundary, never the default's
 * administrator access. Anything else in the template is unchanged.
 *
 * Throws {@link BootstrapTemplateError} when the template no longer has the
 * reviewed shape, so a CLI upgrade that changes it needs a new review.
 */
export function narrowedBootstrapTemplate(template: unknown, anchors: TrustAnchors): Node {
  const narrowed = object(structuredClone(template), "the template");
  const parameters = object(narrowed["Parameters"], "the template's parameters");
  object(parameters["BootstrapVariant"], "the BootstrapVariant parameter")["Default"] =
    BOOTSTRAP_VARIANT;
  const resources = object(narrowed["Resources"], "the template's resources");
  for (const name of ASSUMABLE_ROLES) {
    resource(resources, name, "AWS::IAM::Role")["AssumeRolePolicyDocument"] = trustOnly(
      anchors.deployRoleArn,
    );
  }
  const deploy = resource(resources, "DeploymentActionRole", "AWS::IAM::Role");
  const [policy] = list(deploy["Policies"], "DeploymentActionRole's policies") as Node[];
  deploy["Policies"] = [
    {
      ...policy,
      PolicyDocument: {
        Version: "2012-10-17",
        Statement: deployStatements(deploy["Policies"], anchors),
      },
    },
  ];
  const execution = resource(resources, "CloudFormationExecutionRole", "AWS::IAM::Role");
  for (const property of ["ManagedPolicyArns", "PermissionsBoundary"]) {
    object(execution[property], `the execution role's ${property}`);
  }
  execution["ManagedPolicyArns"] = { Ref: "CloudFormationExecutionPolicies" };
  execution["PermissionsBoundary"] = {
    "Fn::Sub": "arn:${AWS::Partition}:iam::${AWS::AccountId}:policy/${InputPermissionsBoundary}",
  };
  return narrowed;
}
