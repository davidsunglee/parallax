import type { EnvironmentConfiguration } from "../src/configuration.ts";
import { ACCESS_OUTPUTS } from "../src/access-stack.ts";
import { deployRoleConditions } from "../src/access-policies.ts";
import { ENGINE_VERSION } from "../src/constructs/aurora-cluster.ts";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  BOUNDARY_POLICY_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_STACK_NAME,
  GITHUB_OIDC_AUDIENCE,
  GITHUB_OIDC_ISSUER,
  type BootstrapRole,
  type TrustAnchors,
} from "../src/trust.ts";
import { BOOTSTRAP_VARIANT } from "./bootstrap-template.ts";
import { CHECK, judged, type Expectation, type Finding, type Sources } from "./findings.ts";

export interface AwsContext {
  readonly read: Sources;
  readonly anchors: TrustAnchors;
  readonly configuration: EnvironmentConfiguration;
}

/** Who a check expects to be running: a maintainer setting up, or protected CI deploying. */
export type Operator = "maintainer" | "deploy";

const STACK_ABSENT = /does not exist/;
const COMPLETE = new Set(["CREATE_COMPLETE", "UPDATE_COMPLETE"]);
const SERVERLESS_CLASS = "db.serverless";
/** The public parameter naming the newest Amazon Linux 2023 arm64 image. */
export const LATEST_NAT_IMAGE_PARAMETER =
  "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64";

const asList = (value: unknown): unknown[] =>
  Array.isArray(value) ? (value as unknown[]) : value === undefined ? [] : [value];

const sameSet = (left: readonly unknown[], right: readonly unknown[]): boolean =>
  JSON.stringify([...left].map(String).sort()) === JSON.stringify([...right].map(String).sort());

export function identityFinding(context: AwsContext, operator: Operator): Finding {
  const identity = context.read.aws(["sts", "get-caller-identity"]) as {
    Account?: string;
    Arn?: string;
  };
  const { account, qualifier } = context.anchors;
  const arn = identity.Arn ?? "";
  const asDeployRole = arn.startsWith(`arn:aws:sts::${account}:assumed-role/${DEPLOY_ROLE_NAME}/`);
  const asBootstrapRole = arn.includes(`:assumed-role/cdk-${qualifier}-`);
  const expectations: Expectation[] =
    operator === "deploy"
      ? [[asDeployRole, `protected CI runs as ${DEPLOY_ROLE_NAME}, not ${arn}`]]
      : [
          [
            !asDeployRole && !asBootstrapRole,
            "setup runs under a maintainer identity, never the deploy or bootstrap roles",
          ],
        ];
  return judged(
    CHECK.identity,
    [
      [
        identity.Account === account,
        `credentials belong to ${String(identity.Account)}, not ${account}`,
      ],
      ...expectations,
    ],
    `account ${account} as ${arn}`,
  );
}

export function oidcProviderFinding(context: AwsContext): Finding {
  const provider = context.read.aws([
    "iam",
    "get-open-id-connect-provider",
    "--open-id-connect-provider-arn",
    context.anchors.oidcProviderArn,
  ]) as { Url?: string; ClientIDList?: unknown };
  return judged(
    CHECK.provider,
    [
      [provider.Url === GITHUB_OIDC_ISSUER, `the provider's issuer is ${String(provider.Url)}`],
      [
        sameSet(asList(provider.ClientIDList), [GITHUB_OIDC_AUDIENCE]),
        `the provider must admit exactly the ${GITHUB_OIDC_AUDIENCE} audience`,
      ],
    ],
    `existing GitHub provider ${context.anchors.oidcProviderArn}`,
  );
}

export function sourceConnectionFinding(context: AwsContext): Finding {
  const { Connection: connection = {} } = context.read.aws([
    "codeconnections",
    "get-connection",
    "--connection-arn",
    context.anchors.sourceConnectionArn,
  ]) as {
    Connection?: { ConnectionStatus?: string; ProviderType?: string; OwnerAccountId?: string };
  };
  return judged(
    CHECK.connection,
    [
      [connection.ProviderType === "GitHub", "the connection is not a GitHub connection"],
      [
        connection.OwnerAccountId === context.anchors.account,
        "the connection belongs to another account",
      ],
      [
        connection.ConnectionStatus === "AVAILABLE",
        `the connection is ${String(connection.ConnectionStatus)}, not AVAILABLE`,
      ],
    ],
    `existing connection ${context.anchors.sourceConnectionArn} is AVAILABLE`,
  );
}

interface EngineVersion {
  readonly ServerlessV2FeaturesSupport?: { MinCapacity?: number; MaxCapacity?: number };
}

interface OrderableOption {
  readonly StorageType?: string;
  readonly SupportsIAMDatabaseAuthentication?: boolean;
  readonly AvailabilityZones?: readonly { Name?: string }[];
}

/** Whether Aurora still offers the pinned release as Serverless v2, with IAM authentication, in the configured zones. */
export function offeringFinding(context: AwsContext): Finding {
  const version = ENGINE_VERSION.auroraPostgresFullVersion;
  const engine = ["--engine", "aurora-postgresql", "--engine-version", version];
  const { DBEngineVersions: versions = [] } = context.read.aws([
    "rds",
    "describe-db-engine-versions",
    ...engine,
  ]) as { DBEngineVersions?: readonly EngineVersion[] };
  const { OrderableDBInstanceOptions: options = [] } = context.read.aws([
    "rds",
    "describe-orderable-db-instance-options",
    ...engine,
    "--db-instance-class",
    SERVERLESS_CLASS,
  ]) as { OrderableDBInstanceOptions?: readonly OrderableOption[] };
  const capacity = versions[0]?.ServerlessV2FeaturesSupport ?? {};
  const { minCapacity, maxCapacity } = context.configuration.aurora;
  const offered = options.filter(
    (option) =>
      option.StorageType === "aurora" && option.SupportsIAMDatabaseAuthentication === true,
  );
  const zones = new Set(
    offered.flatMap((option) => (option.AvailabilityZones ?? []).map((zone) => zone.Name)),
  );
  return judged(
    CHECK.offering,
    [
      [versions.length === 1, `Aurora PostgreSQL ${version} is not offered`],
      [
        (capacity.MinCapacity ?? Infinity) <= minCapacity &&
          (capacity.MaxCapacity ?? -Infinity) >= maxCapacity,
        `Serverless v2 on ${version} does not span ${String(minCapacity)}–${String(maxCapacity)} ACU`,
      ],
      [
        context.configuration.availabilityZones.every((zone) => zones.has(zone)),
        `${SERVERLESS_CLASS} with IAM authentication is not offered in every configured zone`,
      ],
    ],
    `Aurora PostgreSQL ${version} Serverless v2 with IAM authentication in ${context.configuration.availabilityZones.join(", ")}`,
  );
}

function newestImage(context: AwsContext): string {
  const { Parameter: parameter } = context.read.aws([
    "ssm",
    "get-parameter",
    "--name",
    LATEST_NAT_IMAGE_PARAMETER,
  ]) as { Parameter?: { Value?: string } };
  return `; the newest Amazon Linux 2023 arm64 image is ${String(parameter?.Value)}`;
}

/** Whether the reviewed NAT image is chosen and is an available Amazon Linux 2023 arm64 image. */
export function natImageFinding(
  context: AwsContext,
  image: string | null,
  suggest: boolean,
): Finding {
  if (image === null) {
    return {
      check: CHECK.natImage,
      state: "pending",
      detail: `commit a reviewed natInstanceImage in infra/aws/deploy-inputs.json${suggest ? newestImage(context) : ""}`,
    };
  }
  const { Images: [found] = [] } = context.read.aws([
    "ec2",
    "describe-images",
    "--image-ids",
    image,
  ]) as {
    Images?: readonly { Architecture?: string; Name?: string; State?: string }[];
  };
  return judged(
    CHECK.natImage,
    [
      [found?.State === "available", `${image} is not an available image`],
      [found?.Architecture === "arm64", `${image} is not an arm64 image`],
      [
        found?.Name?.startsWith("al2023-ami-") === true,
        `${image} is not an Amazon Linux 2023 image`,
      ],
    ],
    `NAT image ${image} (${String(found?.Name)})`,
  );
}

interface StackDescription {
  readonly StackStatus?: string;
  readonly EnableTerminationProtection?: boolean;
  readonly Outputs?: readonly { OutputKey?: string; OutputValue?: string }[];
  readonly Parameters?: readonly { ParameterKey?: string; ParameterValue?: string }[];
}

function describedStack(context: AwsContext, name: string): StackDescription | undefined {
  const described = context.read.aws(
    ["cloudformation", "describe-stacks", "--stack-name", name],
    STACK_ABSENT,
  ) as { Stacks?: readonly StackDescription[] } | undefined;
  return described?.Stacks?.[0];
}

function settled(stack: StackDescription, name: string): Expectation[] {
  return [
    [COMPLETE.has(stack.StackStatus ?? ""), `${name} is ${String(stack.StackStatus)}`],
    [stack.EnableTerminationProtection === true, `${name} lacks termination protection`],
  ];
}

interface PolicyStatementJson {
  readonly Effect?: string;
  readonly Principal?: unknown;
  readonly Action?: unknown;
  readonly Resource?: unknown;
  readonly Condition?: unknown;
}

function statements(document: unknown): PolicyStatementJson[] {
  return asList(
    (document as { Statement?: unknown } | undefined)?.Statement,
  ) as PolicyStatementJson[];
}

function roleTrust(context: AwsContext, name: string): PolicyStatementJson[] {
  const { Role: role } = context.read.aws(["iam", "get-role", "--role-name", name]) as {
    Role?: { AssumeRolePolicyDocument?: unknown };
  };
  return statements(role?.AssumeRolePolicyDocument);
}

/** Whether the deploy role admits exactly the one protected environment through the existing provider. */
function deployRoleTrusted(context: AwsContext): boolean {
  const trust = roleTrust(context, DEPLOY_ROLE_NAME);
  const [statement] = trust;
  return (
    trust.length === 1 &&
    statement?.Effect === "Allow" &&
    JSON.stringify(statement.Principal) ===
      JSON.stringify({ Federated: context.anchors.oidcProviderArn }) &&
    sameSet(asList(statement.Action), ["sts:AssumeRoleWithWebIdentity"]) &&
    JSON.stringify(statement.Condition) === JSON.stringify(deployRoleConditions(context.anchors))
  );
}

export function accessStackFinding(context: AwsContext): Finding {
  const stack = describedStack(context, ACCESS_STACK_NAME);
  if (stack === undefined) {
    return {
      check: CHECK.accessStack,
      state: "pending",
      detail: `deploy ${ACCESS_STACK_NAME}: apply access-stack`,
    };
  }
  const outputs = new Map(
    (stack.Outputs ?? []).map((output) => [output.OutputKey, output.OutputValue]),
  );
  const { anchors } = context;
  return judged(
    CHECK.accessStack,
    [
      ...settled(stack, ACCESS_STACK_NAME),
      [
        outputs.get(ACCESS_OUTPUTS.deployRoleArn) === anchors.deployRoleArn,
        "the deploy role is not the pinned one",
      ],
      [
        outputs.get(ACCESS_OUTPUTS.executionPolicyArn) === anchors.executionPolicyArn &&
          outputs.get(ACCESS_OUTPUTS.boundaryPolicyArn) === anchors.boundaryPolicyArn,
        "the execution policy or boundary is not the pinned one",
      ],
      [deployRoleTrusted(context), `${DEPLOY_ROLE_NAME} trusts more than ${anchors.deploySubject}`],
    ],
    `${DEPLOY_ROLE_NAME} trusts only ${anchors.deploySubject}`,
  );
}

const BOOTSTRAP_ROLES: readonly BootstrapRole[] = [
  "deploy",
  "file-publishing",
  "image-publishing",
  "lookup",
];

function trustsOnlyDeployRole(context: AwsContext, role: BootstrapRole): boolean {
  const trust = roleTrust(context, context.anchors.bootstrapRoleName(role));
  return (
    trust.length > 0 &&
    trust.every(
      (statement) =>
        statement.Effect !== "Allow" ||
        JSON.stringify(statement.Principal) ===
          JSON.stringify({ AWS: context.anchors.deployRoleArn }),
    )
  );
}

function executionRoleBounded(context: AwsContext): boolean {
  const name = context.anchors.bootstrapRoleName("cfn-exec");
  const { Role: role } = context.read.aws(["iam", "get-role", "--role-name", name]) as {
    Role?: { PermissionsBoundary?: { PermissionsBoundaryArn?: string } };
  };
  const { AttachedPolicies: attached = [] } = context.read.aws([
    "iam",
    "list-attached-role-policies",
    "--role-name",
    name,
  ]) as { AttachedPolicies?: readonly { PolicyArn?: string }[] };
  return (
    role?.PermissionsBoundary?.PermissionsBoundaryArn === context.anchors.boundaryPolicyArn &&
    sameSet(
      attached.map((policy) => policy.PolicyArn),
      [context.anchors.executionPolicyArn],
    )
  );
}

const STACK_MUTATION = /^cloudformation:(?!(Describe|Get|List|Validate|Detect|Estimate))/;

/** Whether every CloudFormation change the bootstrap deploy role is allowed targets only the environment stack. */
function deployRoleConfined(context: AwsContext): boolean {
  const { PolicyDocument: document } = context.read.aws([
    "iam",
    "get-role-policy",
    "--role-name",
    context.anchors.bootstrapRoleName("deploy"),
    "--policy-name",
    "default",
  ]) as { PolicyDocument?: unknown };
  return statements(document)
    .filter((statement) => statement.Effect === "Allow")
    .filter((statement) =>
      asList(statement.Action).some((action) => STACK_MUTATION.test(String(action))),
    )
    .every((statement) =>
      sameSet(asList(statement.Resource), [context.anchors.stackArn(ENVIRONMENT_STACK_NAME)]),
    );
}

export function bootstrapFinding(context: AwsContext): Finding {
  const stack = describedStack(context, BOOTSTRAP_STACK_NAME);
  if (stack === undefined) {
    return {
      check: CHECK.bootstrap,
      state: "pending",
      detail: `bootstrap ${BOOTSTRAP_STACK_NAME}: apply bootstrap`,
    };
  }
  const parameters = new Map(
    (stack.Parameters ?? []).map((entry) => [entry.ParameterKey, entry.ParameterValue]),
  );
  const { anchors } = context;
  return judged(
    CHECK.bootstrap,
    [
      ...settled(stack, BOOTSTRAP_STACK_NAME),
      [
        parameters.get("BootstrapVariant") === BOOTSTRAP_VARIANT,
        "the bootstrap is not the narrowed variant",
      ],
      [
        parameters.get("Qualifier") === anchors.qualifier,
        `the bootstrap qualifier is not ${anchors.qualifier}`,
      ],
      [
        parameters.get("CloudFormationExecutionPolicies") === anchors.executionPolicyArn &&
          parameters.get("InputPermissionsBoundary") === BOUNDARY_POLICY_NAME,
        "the bootstrap was not given the pinned execution policy and boundary",
      ],
      [
        BOOTSTRAP_ROLES.every((role) => trustsOnlyDeployRole(context, role)),
        `a bootstrap role trusts someone other than ${DEPLOY_ROLE_NAME}`,
      ],
      [
        executionRoleBounded(context),
        "the execution role holds more than the bounded policy, or lacks the boundary",
      ],
      [
        deployRoleConfined(context),
        `the bootstrap deploy role may change a stack other than ${ENVIRONMENT_STACK_NAME}`,
      ],
    ],
    `${BOOTSTRAP_STACK_NAME} trusts only ${DEPLOY_ROLE_NAME} and executes under the boundary`,
  );
}
