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

/** How the bootstrap's file assets are encrypted: its `FileAssetsBucketKmsKeyId` parameter, and the key it created when that is empty. */
export interface BootstrapKey {
  readonly keyId: string;
  readonly keyArn: string;
}

/** What the trust path relies on the narrowed bootstrap's roles holding once CloudFormation resolves them. */
export interface BootstrapPermissions {
  /** The deploy role's inline policies, by name, and its managed policy ARNs. */
  readonly deployInline: Readonly<Record<string, unknown>>;
  readonly deployManaged: readonly string[];
  /** The file-publishing role's inline policies, by name. */
  readonly filePublishingInline: Readonly<Record<string, unknown>>;
  /** Who may assume the execution role. */
  readonly executionTrust: unknown;
}

interface Resolution {
  readonly names: Readonly<Record<string, string>>;
  readonly conditions: Readonly<Record<string, boolean>>;
}

function lookup<T>(table: Readonly<Record<string, T>>, name: string): T {
  const value = table[name];
  if (value === undefined) throw new BootstrapTemplateError(`the template refers to ${name}`);
  return value;
}

/** The value of the intrinsic `{ [name]: argument }`, as far as the narrowing resolves one. */
function intrinsic(name: string, argument: unknown, resolution: Resolution): unknown {
  if (name === "Fn::Sub" && typeof argument === "string") {
    return argument.replace(/\$\{([^}]+)\}/g, (_, key: string) => lookup(resolution.names, key));
  }
  if (name === "Fn::If") {
    const [condition, whenTrue, whenFalse] = list(argument, "an Fn::If");
    const holds = lookup(resolution.conditions, String(condition));
    return resolved(holds ? whenTrue : whenFalse, resolution);
  }
  throw new BootstrapTemplateError(`the template uses ${name} where the narrowing expects none`);
}

/** *value* with each `Fn::Sub` and `Fn::If` resolved; any other intrinsic means the reviewed shape changed. */
function resolved(value: unknown, resolution: Resolution): unknown {
  if (Array.isArray(value)) return value.map((item) => resolved(item, resolution));
  if (typeof value !== "object" || value === null) return value;
  const entries = Object.entries(value);
  const [key, argument] = entries[0] ?? [""];
  if (key === "Ref" || key.startsWith("Fn::")) return intrinsic(key, argument, resolution);
  return Object.fromEntries(entries.map(([name, item]) => [name, resolved(item, resolution)]));
}

/**
 * The permissions *template*, narrowed, gives the roles the deploy role
 * reaches, resolved as CloudFormation resolves them for *anchors* and *key*.
 *
 * Throws {@link BootstrapTemplateError} when the template no longer has the
 * reviewed shape.
 */
export function bootstrapPermissions(
  template: unknown,
  anchors: TrustAnchors,
  key: BootstrapKey,
): BootstrapPermissions {
  const resources = object(
    narrowedBootstrapTemplate(template, anchors)["Resources"],
    "the template's resources",
  );
  const pseudo = {
    "AWS::Partition": "aws",
    "AWS::Region": anchors.region,
    "AWS::AccountId": anchors.account,
    Qualifier: anchors.qualifier,
  };
  const version = resource(resources, "CdkBootstrapVersion", "AWS::SSM::Parameter")["Name"];
  const resolution: Resolution = {
    names: {
      ...pseudo,
      CdkBootstrapVersion: String(resolved(version, { names: pseudo, conditions: {} })),
      "CloudFormationExecutionRole.Arn": anchors.bootstrapRoleArn("cfn-exec"),
      "StagingBucket.Arn": anchors.stagingBucketArn,
      FileAssetsBucketKmsKeyId: key.keyId,
      "FileAssetsBucketEncryptionKey.Arn": key.keyArn,
    },
    conditions: { CreateNewKey: key.keyId === "" },
  };
  const inline = (policies: readonly unknown[]): Record<string, unknown> =>
    Object.fromEntries(
      policies.map((policy) => {
        const { PolicyName: name, PolicyDocument: document } = object(policy, "a policy");
        return [String(resolved(name, resolution)), resolved(document, resolution)];
      }),
    );
  const deploy = resource(resources, "DeploymentActionRole", "AWS::IAM::Role");
  const publishing = resource(resources, "FilePublishingRoleDefaultPolicy", "AWS::IAM::Policy");
  const execution = resource(resources, "CloudFormationExecutionRole", "AWS::IAM::Role");
  return {
    deployInline: inline(list(deploy["Policies"], "DeploymentActionRole's policies")),
    deployManaged: list(resolved(deploy["ManagedPolicyArns"], resolution), "managed policies").map(
      String,
    ),
    filePublishingInline: inline([publishing]),
    executionTrust: resolved(execution["AssumeRolePolicyDocument"], resolution),
  };
}
