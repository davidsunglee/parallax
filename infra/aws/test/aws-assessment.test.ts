import { describe, expect, it } from "vitest";
import {
  ACCESS_STACK_NAME,
  BOOTSTRAP_STACK_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_STACK_NAME,
} from "../src/trust.ts";
import {
  accessStackFinding,
  bootstrapFinding,
  identityFinding,
  LATEST_NAT_IMAGE_PARAMETER,
  natImageFinding,
  offeringFinding,
  oidcProviderFinding,
  sourceConnectionFinding,
} from "../tools/aws-assessment.ts";
import { bootstrapPermissions, pinnedBootstrapTemplate } from "../tools/bootstrap-template.ts";
import {
  ABSENT_STACK,
  ACCOUNT,
  ANCHORS,
  BOOTSTRAP_PERMISSIONS,
  healthyReplies,
  IMAGE,
  json,
  world,
  type Reply,
} from "./rollout-world.ts";

const reply = (key: string): unknown => (healthyReplies()[key] as { json: unknown }).json;

const ADMINISTRATOR = "arn:aws:iam::aws:policy/AdministratorAccess";
const everything = {
  Version: "2012-10-17",
  Statement: [{ Effect: "Allow", Action: "*", Resource: "*" }],
};

const caller = (arn: string, account = ACCOUNT): Record<string, Reply> => ({
  "sts get-caller-identity": json({ Account: account, Arn: arn }),
});

describe("the identity check", () => {
  it("accepts a maintainer and refuses the deploy or a bootstrap role for setup", () => {
    expect(identityFinding(world().context, "maintainer").state).toBe("verified");
    for (const arn of [
      `arn:aws:sts::${ACCOUNT}:assumed-role/${DEPLOY_ROLE_NAME}/session`,
      `arn:aws:sts::${ACCOUNT}:assumed-role/cdk-${ANCHORS.qualifier}-deploy-role-${ACCOUNT}-us-east-2/cli`,
    ]) {
      expect(identityFinding(world(caller(arn)).context, "maintainer")).toMatchObject({
        state: "drift",
        detail: expect.stringContaining("maintainer identity") as string,
      });
    }
  });

  it("requires protected CI to run as the deploy role in the configured account", () => {
    const deployRole = `arn:aws:sts::${ACCOUNT}:assumed-role/${DEPLOY_ROLE_NAME}/infra-deploy-1-1`;
    expect(identityFinding(world(caller(deployRole)).context, "deploy").state).toBe("verified");
    expect(identityFinding(world().context, "deploy").detail).toContain(
      `runs as ${DEPLOY_ROLE_NAME}`,
    );
    expect(
      identityFinding(world(caller(deployRole, "111111111111")).context, "deploy").detail,
    ).toBe(`credentials belong to 111111111111, not ${ACCOUNT}`);
    expect(
      identityFinding(world({ "sts get-caller-identity": json({}) }).context, "deploy").state,
    ).toBe("drift");
  });
});

describe("the existing provider and connection", () => {
  it("are reused only as they were verified", () => {
    expect(oidcProviderFinding(world().context).state).toBe("verified");
    expect(
      oidcProviderFinding(
        world({ "iam get-open-id-connect-provider": json({ Url: "elsewhere.example.com" }) })
          .context,
      ).detail,
    ).toBe("the provider's issuer is elsewhere.example.com");
    expect(
      oidcProviderFinding(
        world({
          "iam get-open-id-connect-provider": json({
            Url: "token.actions.githubusercontent.com",
            ClientIDList: "sts.amazonaws.com",
          }),
        }).context,
      ).state,
    ).toBe("verified");
    expect(
      oidcProviderFinding(
        world({
          "iam get-open-id-connect-provider": json({
            Url: "token.actions.githubusercontent.com",
            ClientIDList: ["sts.amazonaws.com", "other"],
          }),
        }).context,
      ).detail,
    ).toContain("exactly the sts.amazonaws.com audience");
    expect(sourceConnectionFinding(world().context).state).toBe("verified");
    for (const [connection, detail] of [
      [{ ProviderType: "Bitbucket" }, "not a GitHub connection"],
      [{ ProviderType: "GitHub", OwnerAccountId: "1" }, "another account"],
      [{ ProviderType: "GitHub", OwnerAccountId: ACCOUNT, ConnectionStatus: "PENDING" }, "PENDING"],
    ] as const) {
      const found = sourceConnectionFinding(
        world({ "codeconnections get-connection": json({ Connection: connection }) }).context,
      );
      expect(found.detail).toContain(detail);
    }
    expect(
      sourceConnectionFinding(world({ "codeconnections get-connection": json({}) }).context).state,
    ).toBe("drift");
  });
});

describe("the Aurora offering check", () => {
  it("needs the pinned release, the capacity range, and IAM-capable serverless options in every zone", () => {
    expect(offeringFinding(world().context).state).toBe("verified");
    const cases: [Record<string, Reply>, string][] = [
      [{ "rds describe-db-engine-versions": json({}) }, "is not offered"],
      [
        {
          "rds describe-db-engine-versions": json({
            DBEngineVersions: [
              { ServerlessV2FeaturesSupport: { MinCapacity: 0.5, MaxCapacity: 256 } },
            ],
          }),
        },
        "does not span 0–2 ACU",
      ],
      [{ "rds describe-db-engine-versions": json({ DBEngineVersions: [{}] }) }, "does not span"],
      [
        {
          "rds describe-db-engine-versions": json({
            DBEngineVersions: [{ ServerlessV2FeaturesSupport: { MinCapacity: 0 } }],
          }),
        },
        "does not span",
      ],
      [{ "rds describe-orderable-db-instance-options": json({}) }, "every configured zone"],
      [
        {
          "rds describe-orderable-db-instance-options": json({
            OrderableDBInstanceOptions: [
              { StorageType: "aurora", SupportsIAMDatabaseAuthentication: true },
            ],
          }),
        },
        "every configured zone",
      ],
    ];
    for (const [replies, detail] of cases) {
      expect(offeringFinding(world(replies).context).detail).toContain(detail);
    }
  });
});

describe("the NAT image check", () => {
  it("asks for a reviewed image, suggesting the newest one only to a maintainer", () => {
    const { context, captured } = world();
    expect(natImageFinding(context, null, true)).toMatchObject({
      state: "pending",
      detail: expect.stringContaining(
        `the newest Amazon Linux 2023 arm64 image is ${IMAGE}`,
      ) as string,
    });
    expect(captured.map((invocation) => invocation.args)).toContainEqual(
      expect.arrayContaining([LATEST_NAT_IMAGE_PARAMETER]),
    );
    const quiet = world();
    expect(natImageFinding(quiet.context, null, false).detail).not.toContain("newest");
    expect(quiet.captured).toHaveLength(0);
    expect(
      natImageFinding(world({ "ssm get-parameter": json({}) }).context, null, true).detail,
    ).toContain("is undefined");
  });

  it("accepts only an available Amazon Linux 2023 arm64 image", () => {
    expect(natImageFinding(world().context, IMAGE, false).state).toBe("verified");
    for (const [image, detail] of [
      [{ State: "pending" }, "not an available image"],
      [{ State: "available", Architecture: "x86_64" }, "not an arm64 image"],
      [
        { State: "available", Architecture: "arm64", Name: "ubuntu" },
        "not an Amazon Linux 2023 image",
      ],
      [{ State: "available", Architecture: "arm64" }, "not an Amazon Linux 2023 image"],
    ] as const) {
      expect(
        natImageFinding(
          world({ "ec2 describe-images": json({ Images: [image] }) }).context,
          IMAGE,
          false,
        ).detail,
      ).toContain(detail);
    }
    expect(
      natImageFinding(world({ "ec2 describe-images": json({}) }).context, IMAGE, false).state,
    ).toBe("drift");
  });
});

const accessStack = `cloudformation describe-stacks --stack-name ${ACCESS_STACK_NAME}`;
const bootstrapStack = `cloudformation describe-stacks --stack-name ${BOOTSTRAP_STACK_NAME}`;
const deployRoleKey = `iam get-role --role-name ${DEPLOY_ROLE_NAME}`;

function withStack(
  key: string,
  change: (stack: Record<string, unknown>) => Record<string, unknown>,
): Record<string, Reply> {
  const [stack] = (reply(key) as { Stacks: Record<string, unknown>[] }).Stacks;
  return { [key]: json({ Stacks: [change(stack ?? {})] }) };
}

describe("the access stack check", () => {
  it("is pending until a maintainer deploys the stack", () => {
    expect(
      accessStackFinding(world({ [accessStack]: ABSENT_STACK(ACCESS_STACK_NAME) }).context),
    ).toMatchObject({
      state: "pending",
      detail: expect.stringContaining("apply access-stack") as string,
    });
  });

  it("verifies the stack's state, outputs, and the deploy role's exact trust", () => {
    expect(accessStackFinding(world().context).state).toBe("verified");
    const trust = (
      reply(deployRoleKey) as {
        Role: { AssumeRolePolicyDocument: { Statement: Record<string, unknown>[] } };
      }
    ).Role.AssumeRolePolicyDocument.Statement[0];
    const cases: [Record<string, Reply>, string][] = [
      [
        withStack(accessStack, (stack) => ({ ...stack, StackStatus: "UPDATE_ROLLBACK_COMPLETE" })),
        "UPDATE_ROLLBACK_COMPLETE",
      ],
      [
        withStack(accessStack, (stack) => ({ ...stack, EnableTerminationProtection: false })),
        "termination protection",
      ],
      [
        withStack(accessStack, (stack) => ({
          ...stack,
          Outputs: undefined,
          StackStatus: undefined,
        })),
        "is undefined",
      ],
      [withStack(accessStack, (stack) => ({ ...stack, Outputs: undefined })), "not the pinned one"],
      [
        withStack(accessStack, (stack) => ({
          ...stack,
          Outputs: [{ OutputKey: "DeployRoleArn", OutputValue: ANCHORS.deployRoleArn }],
        })),
        "execution policy or boundary",
      ],
      [
        {
          [deployRoleKey]: json({
            Role: {
              AssumeRolePolicyDocument: {
                Statement: [
                  {
                    ...trust,
                    Condition: {
                      StringLike: { "token.actions.githubusercontent.com:sub": "repo:*" },
                    },
                  },
                ],
              },
            },
          }),
        },
        `trusts more than ${ANCHORS.deploySubject}`,
      ],
      [
        {
          [deployRoleKey]: json({
            Role: { AssumeRolePolicyDocument: { Statement: [trust, trust] } },
          }),
        },
        "trusts more",
      ],
      [{ [deployRoleKey]: json({}) }, "trusts more"],
      [
        {
          [deployRoleKey]: json({
            Role: { AssumeRolePolicyDocument: { Statement: { ...trust, Effect: "Deny" } } },
          }),
        },
        "trusts more",
      ],
      [
        {
          [deployRoleKey]: json({
            Role: {
              AssumeRolePolicyDocument: { Statement: [{ ...trust, Principal: { AWS: "*" } }] },
            },
          }),
        },
        "trusts more",
      ],
      [
        {
          [deployRoleKey]: json({
            Role: {
              AssumeRolePolicyDocument: { Statement: [{ ...trust, Action: ["sts:AssumeRole"] }] },
            },
          }),
        },
        "trusts more",
      ],
      [
        { [`iam list-role-policies --role-name ${DEPLOY_ROLE_NAME}`]: json({}) },
        `${DEPLOY_ROLE_NAME} holds other permissions than ${ACCESS_STACK_NAME} defines`,
      ],
      [
        {
          [`iam list-attached-role-policies --role-name ${DEPLOY_ROLE_NAME}`]: json({
            AttachedPolicies: [{ PolicyArn: ADMINISTRATOR }],
          }),
        },
        "holds other permissions",
      ],
      [
        {
          [`iam get-role-policy --role-name ${DEPLOY_ROLE_NAME} --policy-name deploy`]: json({
            PolicyDocument: everything,
          }),
        },
        "holds other permissions",
      ],
      [
        {
          [`iam get-policy --policy-arn ${ANCHORS.boundaryPolicyArn}`]: json({
            Policy: { DefaultVersionId: "v3" },
          }),
          [`iam get-policy-version --policy-arn ${ANCHORS.boundaryPolicyArn} --version-id v3`]:
            json({ PolicyVersion: { Document: everything } }),
        },
        `the execution policy or boundary is not the one ${ACCESS_STACK_NAME} defines`,
      ],
      [
        {
          [`iam get-policy-version --policy-arn ${ANCHORS.executionPolicyArn} --version-id v2`]:
            json({ PolicyVersion: {} }),
        },
        "is not the one",
      ],
    ];
    for (const [replies, detail] of cases) {
      expect(accessStackFinding(world(replies).context).detail).toContain(detail);
    }
  });

  it("reads documents IAM treats alike as the same, whatever their key order or list spelling", () => {
    const trust = reply(deployRoleKey) as {
      Role: { AssumeRolePolicyDocument: { Statement: Record<string, unknown>[] } };
    };
    const [statement] = trust.Role.AssumeRolePolicyDocument.Statement;
    const reordered = {
      Condition: {
        StringEquals: {
          "token.actions.githubusercontent.com:sub": ANCHORS.deploySubject,
          "token.actions.githubusercontent.com:aud": ["sts.amazonaws.com"],
        },
      },
      Action: ["sts:AssumeRoleWithWebIdentity"],
      Principal: { Federated: [ANCHORS.oidcProviderArn] },
      Effect: statement?.["Effect"],
    };
    expect(
      accessStackFinding(
        world({
          [deployRoleKey]: json({
            Role: { AssumeRolePolicyDocument: { Statement: reordered, Version: "2012-10-17" } },
          }),
        }).context,
      ).state,
    ).toBe("verified");
  });
});

describe("the bootstrap check", () => {
  const roleKey = (kind: Parameters<typeof ANCHORS.bootstrapRoleName>[0]): string =>
    `iam get-role --role-name ${ANCHORS.bootstrapRoleName(kind)}`;
  const role = (kind: Parameters<typeof ANCHORS.bootstrapRoleName>[0]): string =>
    ANCHORS.bootstrapRoleName(kind);
  const [publishingPolicy = ""] = Object.keys(BOOTSTRAP_PERMISSIONS.filePublishingInline);

  it("is pending until a maintainer bootstraps", () => {
    expect(
      bootstrapFinding(world({ [bootstrapStack]: ABSENT_STACK(BOOTSTRAP_STACK_NAME) }).context),
    ).toMatchObject({
      state: "pending",
      detail: expect.stringContaining("apply bootstrap") as string,
    });
  });

  it("verifies the narrowed variant, its parameters, every role's trust, and the permissions the deploy role reaches", () => {
    expect(bootstrapFinding(world().context).state).toBe("verified");
    const parameter = (key: string, value: string) =>
      withStack(bootstrapStack, (stack) => ({
        ...stack,
        Parameters: [
          ...(stack["Parameters"] as { ParameterKey: string }[]).filter(
            (entry) => entry.ParameterKey !== key,
          ),
          { ParameterKey: key, ParameterValue: value },
        ],
      }));
    const statement = { Effect: "Allow", Action: "sts:AssumeRole" };
    const execution = reply(roleKey("cfn-exec")) as { Role: Record<string, unknown> };
    const cases: [Record<string, Reply>, string][] = [
      [parameter("BootstrapVariant", "AWS CDK: Default Resources"), "not the narrowed variant"],
      [parameter("Qualifier", "hnb659fds"), "qualifier is not"],
      [parameter("CloudFormationExecutionPolicies", ADMINISTRATOR), "pinned execution policy"],
      [parameter("InputPermissionsBoundary", ""), "pinned execution policy"],
      [
        withStack(bootstrapStack, (stack) => ({ ...stack, Parameters: undefined })),
        "not the narrowed variant",
      ],
      [
        {
          [roleKey("lookup")]: json({
            Role: {
              AssumeRolePolicyDocument: {
                Statement: [{ ...statement, Principal: { AWS: ACCOUNT } }],
              },
            },
          }),
        },
        "trusts someone other than",
      ],
      [{ [roleKey("image-publishing")]: json({ Role: {} }) }, "trusts someone other than"],
      [
        { [roleKey("cfn-exec")]: json({ Role: { ...execution.Role, PermissionsBoundary: {} } }) },
        "lacks the boundary",
      ],
      [
        {
          [roleKey("cfn-exec")]: json({
            Role: {
              ...execution.Role,
              AssumeRolePolicyDocument: {
                Version: "2012-10-17",
                Statement: [
                  {
                    Effect: "Allow",
                    Principal: { Service: "cloudformation.amazonaws.com" },
                    Action: "sts:AssumeRole",
                  },
                  { ...statement, Principal: { AWS: "arn:aws:iam::111122223333:root" } },
                ],
              },
            },
          }),
        },
        "the execution role trusts more than CloudFormation",
      ],
      [
        {
          [`iam list-attached-role-policies --role-name ${role("cfn-exec")}`]: json({
            AttachedPolicies: [{ PolicyArn: ADMINISTRATOR }],
          }),
        },
        "holds more than the bounded policy",
      ],
      [
        { [`iam list-attached-role-policies --role-name ${role("cfn-exec")}`]: json({}) },
        "holds more than the bounded policy",
      ],
      [
        {
          [`iam list-role-policies --role-name ${role("cfn-exec")}`]: json({
            PolicyNames: ["escalate"],
          }),
          [`iam get-role-policy --role-name ${role("cfn-exec")} --policy-name escalate`]: json({
            PolicyDocument: everything,
          }),
        },
        "holds more than the bounded policy",
      ],
      [
        {
          [`iam get-role-policy --role-name ${role("deploy")} --policy-name default`]: json({
            PolicyDocument: everything,
          }),
        },
        `the bootstrap deploy role holds other permissions than the narrowed template's, which change ${ENVIRONMENT_STACK_NAME} alone`,
      ],
      [
        {
          [`iam get-role-policy --role-name ${role("deploy")} --policy-name default`]: json({
            PolicyDocument: {
              Statement: [
                { Effect: "Allow", Action: ["cloudformation:UpdateStack"], Resource: "*" },
              ],
            },
          }),
        },
        "the bootstrap deploy role holds other permissions",
      ],
      [
        {
          [`iam list-attached-role-policies --role-name ${role("deploy")}`]: json({
            AttachedPolicies: [{ PolicyArn: ADMINISTRATOR }],
          }),
        },
        "the bootstrap deploy role holds other permissions",
      ],
      [
        {
          [`iam get-role-policy --role-name ${role("file-publishing")} --policy-name ${publishingPolicy}`]:
            json({ PolicyDocument: everything }),
        },
        "the file-publishing role holds other permissions than the narrowed template's",
      ],
      [
        { [`iam list-role-policies --role-name ${role("file-publishing")}`]: json({}) },
        "the file-publishing role holds other permissions",
      ],
    ];
    for (const [replies, detail] of cases) {
      expect(bootstrapFinding(world(replies).context).detail).toContain(detail);
    }
  });

  it("judges the file-publishing role against the key the bootstrap created", () => {
    const keyArn = `arn:aws:kms:us-east-2:${ACCOUNT}:key/1234abcd`;
    const created = bootstrapPermissions(pinnedBootstrapTemplate(), ANCHORS, { keyId: "", keyArn });
    const keyed = (outputs: unknown) => ({
      ...withStack(bootstrapStack, (stack) => ({
        ...stack,
        Parameters: [
          ...(stack["Parameters"] as { ParameterKey: string }[]).filter(
            (entry) => entry.ParameterKey !== "FileAssetsBucketKmsKeyId",
          ),
          { ParameterKey: "FileAssetsBucketKmsKeyId", ParameterValue: "" },
        ],
        Outputs: outputs,
      })),
      [`iam get-role-policy --role-name ${role("file-publishing")} --policy-name ${publishingPolicy}`]:
        json({ PolicyDocument: created.filePublishingInline[publishingPolicy] }),
    });
    expect(
      bootstrapFinding(
        world(keyed([{ OutputKey: "FileAssetKeyArn", OutputValue: keyArn }])).context,
      ).state,
    ).toBe("verified");
    expect(bootstrapFinding(world(keyed(undefined)).context).detail).toContain(
      "the file-publishing role holds other permissions",
    );
  });

  it("ignores a refusal in a role's trust and a document's spelling", () => {
    const [deployPolicy] = Object.values(BOOTSTRAP_PERMISSIONS.deployInline) as {
      Statement: unknown[];
    }[];
    const tolerated = {
      [roleKey("image-publishing")]: json({
        Role: {
          AssumeRolePolicyDocument: {
            Statement: [
              {
                Effect: "Allow",
                Action: "sts:AssumeRole",
                Principal: { AWS: [ANCHORS.deployRoleArn] },
              },
              { Effect: "Deny", Action: "sts:AssumeRole", Principal: { AWS: "*" } },
            ],
          },
        },
      }),
      [`iam get-role-policy --role-name ${role("deploy")} --policy-name default`]: json({
        PolicyDocument: {
          ...deployPolicy,
          Statement: [...(deployPolicy?.Statement ?? [])].reverse(),
        },
      }),
    };
    expect(bootstrapFinding(world(tolerated).context).state).toBe("verified");
  });
});
