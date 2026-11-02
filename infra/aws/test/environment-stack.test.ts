import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Template } from "aws-cdk-lib/assertions";
import { Ajv2020 } from "ajv/dist/2020.js";
import { beforeAll, describe, expect, it } from "vitest";
import { ConfigurationError } from "../src/configuration.ts";
import { ROLE_BOOTSTRAP_ID } from "../src/constructs/aurora-cluster.ts";
import { NAT_IMAGE_PARAMETER, type EnvironmentStack } from "../src/environment-stack.ts";
import { defineStacks } from "../src/stacks.ts";
import { CONTROL_DATABASE, ROLE_BOOTSTRAP_SQL } from "../src/role-bootstrap.ts";
import { TEST_ENVIRONMENT_PARAMETER } from "../src/test-environment.ts";
import { ENVIRONMENT_STACK_NAME, ENVIRONMENT_TAGS, RUNNER_PROJECT_NAME } from "../src/trust.ts";
import { allowed } from "./policy-evaluation.ts";
import { ANCHORS } from "./rollout-world.ts";
import { committedApp, flatten, PACKAGE_ROOT } from "./committed-app.ts";

interface Resource {
  readonly Type: string;
  readonly Properties: Readonly<Record<string, unknown>>;
  readonly DependsOn?: readonly string[];
  readonly DeletionPolicy?: string;
  readonly UpdateReplacePolicy?: string;
}

let stack: EnvironmentStack;
let template: Template;
let all: Readonly<Record<string, Resource>>;

function resources(type: string): [string, Resource][] {
  return Object.entries(template.findResources(type) as Record<string, Resource>);
}

function only(type: string): [string, Resource] {
  const [found, ...others] = resources(type);
  if (found === undefined || others.length > 0) {
    throw new Error(`expected exactly one ${type}`);
  }
  return found;
}

function runnerGroup(): string {
  const [, project] = only("AWS::CodeBuild::Project");
  const vpc = project.Properties["VpcConfig"] as { SecurityGroupIds: [{ "Fn::GetAtt": [string] }] };
  return vpc.SecurityGroupIds[0]["Fn::GetAtt"][0];
}

function ref(id: string): { Ref: string } {
  return { Ref: id };
}

beforeAll(() => {
  stack = defineStacks(committedApp()).environment;
  template = Template.fromStack(stack);
  all = template.toJSON()["Resources"] as Record<string, Resource>;
});

describe("the environment stack", () => {
  it("deploys to the configured account and Region and refuses deletion", () => {
    expect(stack.stackName).toBe(ENVIRONMENT_STACK_NAME);
    expect(stack.account).toBe("407034905514");
    expect(stack.region).toBe("us-east-2");
    expect(stack.terminationProtection).toBe(true);
  });

  it("refuses a context that holds no deployable configuration", () => {
    expect(() => defineStacks(committedApp({ "parallax:environment": undefined }))).toThrow(
      ConfigurationError,
    );
  });

  it("tags every taggable resource for cost allocation", () => {
    const tagged = Object.values(all).filter((resource) => "Tags" in resource.Properties);
    expect(tagged.length).toBeGreaterThan(20);
    for (const resource of tagged) {
      const tags = resource.Properties["Tags"];
      const pairs = Array.isArray(tags)
        ? Object.fromEntries(
            (tags as { Key: string; Value: string }[]).map(({ Key, Value }) => [Key, Value]),
          )
        : tags;
      expect(pairs, resource.Type).toMatchObject(ENVIRONMENT_TAGS);
    }
  });
});

describe("the private network", () => {
  it("places public and private subnets in exactly the configured zones", () => {
    const subnets = resources("AWS::EC2::Subnet").map(([, subnet]) => subnet.Properties);
    expect(subnets).toHaveLength(4);
    expect(new Set(subnets.map((subnet) => subnet["AvailabilityZone"]))).toEqual(
      new Set(["us-east-2a", "us-east-2b"]),
    );
    const privateSubnets = subnets.filter((subnet) => subnet["MapPublicIpOnLaunch"] === false);
    expect(privateSubnets).toHaveLength(2);
  });

  it("routes every private subnet's internet traffic through the one NAT instance", () => {
    expect(resources("AWS::EC2::NatGateway")).toHaveLength(0);
    const [nat] = only("AWS::EC2::Instance");
    const defaults = resources("AWS::EC2::Route").map(([, route]) => route.Properties);
    expect(defaults.every((route) => route["DestinationCidrBlock"] === "0.0.0.0/0")).toBe(true);
    const viaNat = defaults.filter((route) => "InstanceId" in route);
    const viaGateway = defaults.filter((route) => "GatewayId" in route);
    expect(viaNat).toHaveLength(2);
    expect(viaGateway).toHaveLength(2);
    for (const route of viaNat) expect(route["InstanceId"]).toEqual(ref(nat));
    const [gateway] = only("AWS::EC2::InternetGateway");
    for (const route of viaGateway) expect(route["GatewayId"]).toEqual(ref(gateway));
  });

  it("forwards traffic from an image the deploy names, without SSH or IMDSv1", () => {
    const [, nat] = only("AWS::EC2::Instance");
    expect(nat.Properties).toMatchObject({
      InstanceType: "t4g.nano",
      SourceDestCheck: false,
      ImageId: ref(NAT_IMAGE_PARAMETER),
    });
    expect(nat.Properties).not.toHaveProperty("KeyName");
    const [launchTemplate] = only("AWS::EC2::LaunchTemplate");
    expect(nat.Properties["LaunchTemplate"]).toMatchObject({
      Version: { "Fn::GetAtt": [launchTemplate, "LatestVersionNumber"] },
    });
    template.hasResourceProperties("AWS::EC2::LaunchTemplate", {
      LaunchTemplateData: { MetadataOptions: { HttpTokens: "required" } },
    });
    const parameter = (template.toJSON()["Parameters"] as Record<string, Record<string, unknown>>)[
      NAT_IMAGE_PARAMETER
    ];
    expect(parameter).toMatchObject({ Type: "AWS::EC2::Image::Id" });
    expect(parameter).not.toHaveProperty("Default");
  });

  it("admits traffic to the NAT instance from the private subnets only", () => {
    const [, nat] = only("AWS::EC2::Instance");
    const [natGroup] = nat.Properties["SecurityGroupIds"] as [{ "Fn::GetAtt": [string, string] }];
    const group = all[natGroup["Fn::GetAtt"][0]];
    const privateCidrs = resources("AWS::EC2::Subnet")
      .map(([, subnet]) => subnet.Properties)
      .filter((subnet) => subnet["MapPublicIpOnLaunch"] === false)
      .map((subnet) => subnet["CidrBlock"]);
    const ingress = group?.Properties["SecurityGroupIngress"] as { CidrIp: string }[];
    expect(new Set(ingress.map((rule) => rule.CidrIp))).toEqual(new Set(privateCidrs));
    const separateRules = resources("AWS::EC2::SecurityGroupIngress").map(
      ([, rule]) => rule.Properties,
    );
    expect(
      separateRules.some((rule) =>
        JSON.stringify(rule["GroupId"]).includes(natGroup["Fn::GetAtt"][0]),
      ),
    ).toBe(false);
  });

  it("recovers the NAT instance when its system status check fails", () => {
    const [nat] = only("AWS::EC2::Instance");
    template.hasResourceProperties("AWS::CloudWatch::Alarm", {
      Namespace: "AWS/EC2",
      MetricName: "StatusCheckFailed_System",
      Dimensions: [{ Name: "InstanceId", Value: ref(nat) }],
      ComparisonOperator: "GreaterThanOrEqualToThreshold",
      Threshold: 1,
      AlarmActions: ["arn:aws:automate:us-east-2:ec2:recover"],
    });
  });

  it("keeps S3 traffic off the NAT instance through a gateway endpoint", () => {
    const [, endpoint] = only("AWS::EC2::VPCEndpoint");
    expect(endpoint.Properties["VpcEndpointType"]).toBe("Gateway");
    expect(JSON.stringify(endpoint.Properties["ServiceName"])).toContain(".s3");
    const routeTables = endpoint.Properties["RouteTableIds"] as { Ref: string }[];
    const privateTables = resources("AWS::EC2::SubnetRouteTableAssociation")
      .map(([, association]) => association.Properties)
      .filter((association) => {
        const subnet = all[(association["SubnetId"] as { Ref: string }).Ref];
        return subnet?.Properties["MapPublicIpOnLaunch"] === false;
      })
      .map((association) => association["RouteTableId"]);
    expect(routeTables).toEqual(expect.arrayContaining(privateTables));
  });
});

describe("the Aurora cluster", () => {
  it("is a private, encrypted, IAM-authenticated Aurora PostgreSQL 18.6 cluster with the Data API", () => {
    const [, cluster] = only("AWS::RDS::DBCluster");
    expect(cluster.Properties).toMatchObject({
      Engine: "aurora-postgresql",
      EngineVersion: "18.6",
      DBClusterIdentifier: "parallax-ci",
      DatabaseName: CONTROL_DATABASE,
      Port: 5432,
      EnableIAMDatabaseAuthentication: true,
      EnableHttpEndpoint: true,
      StorageEncrypted: true,
      StorageType: "aurora",
    });
    const [subnetGroup] = only("AWS::RDS::DBSubnetGroup");
    const subnetIds = (all[subnetGroup]?.Properties["SubnetIds"] ?? []) as { Ref: string }[];
    expect(subnetIds).toHaveLength(2);
    for (const { Ref } of subnetIds) {
      expect(all[Ref]?.Properties["MapPublicIpOnLaunch"]).toBe(false);
    }
  });

  it("scales from zero to an explicit ceiling and pauses when idle", () => {
    template.hasResourceProperties("AWS::RDS::DBCluster", {
      ServerlessV2ScalingConfiguration: {
        MinCapacity: 0,
        MaxCapacity: 2,
        SecondsUntilAutoPause: 300,
      },
    });
  });

  it("has one serverless writer and one serverless reader that scales with it", () => {
    const [cluster] = only("AWS::RDS::DBCluster");
    const instances = resources("AWS::RDS::DBInstance").map(([, instance]) => instance.Properties);
    expect(instances).toHaveLength(2);
    expect(instances).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ DBInstanceIdentifier: "parallax-ci-writer", PromotionTier: 0 }),
        expect.objectContaining({ DBInstanceIdentifier: "parallax-ci-reader", PromotionTier: 1 }),
      ]),
    );
    for (const instance of instances) {
      expect(instance).toMatchObject({
        DBClusterIdentifier: ref(cluster),
        DBInstanceClass: "db.serverless",
        PubliclyAccessible: false,
        AutoMinorVersionUpgrade: false,
      });
    }
  });

  it("keeps a snapshot on removal, refuses deletion, and declines extended support", () => {
    const [, cluster] = only("AWS::RDS::DBCluster");
    expect(cluster.DeletionPolicy).toBe("Snapshot");
    expect(cluster.UpdateReplacePolicy).toBe("Snapshot");
    expect(cluster.Properties).toMatchObject({
      DeletionProtection: true,
      BackupRetentionPeriod: 1,
      CopyTagsToSnapshot: true,
      EngineLifecycleSupport: "open-source-rds-extended-support-disabled",
    });
  });

  it("requires TLS on every connection", () => {
    template.hasResourceProperties("AWS::RDS::DBClusterParameterGroup", {
      Parameters: { "rds.force_ssl": "1" },
    });
  });

  it("admits connections on the cluster's port from the runner's security group alone", () => {
    const [, cluster] = only("AWS::RDS::DBCluster");
    const [group] = cluster.Properties["VpcSecurityGroupIds"] as [{ "Fn::GetAtt": [string] }];
    const clusterGroup = group["Fn::GetAtt"][0];
    expect(all[clusterGroup]?.Properties).not.toHaveProperty("SecurityGroupIngress");
    const ingress = resources("AWS::EC2::SecurityGroupIngress").map(([, rule]) => rule.Properties);
    expect(ingress).toEqual([
      expect.objectContaining({
        GroupId: { "Fn::GetAtt": [clusterGroup, "GroupId"] },
        IpProtocol: "tcp",
        FromPort: { "Fn::GetAtt": [only("AWS::RDS::DBCluster")[0], "Endpoint.Port"] },
        ToPort: { "Fn::GetAtt": [only("AWS::RDS::DBCluster")[0], "Endpoint.Port"] },
        SourceSecurityGroupId: { "Fn::GetAtt": [runnerGroup(), "GroupId"] },
      }),
    ]);
  });
});

describe("the role bootstrap", () => {
  function sdkCall(property: "Create" | "Update"): Record<string, unknown> {
    const [, bootstrap] = only("Custom::AWS");
    return JSON.parse(flatten(bootstrap.Properties[property]).text) as Record<string, unknown>;
  }

  it("runs the authored statement on the control database on create and on update alike", () => {
    const create = sdkCall("Create");
    expect(create).toMatchObject({
      service: "rds-data",
      action: "ExecuteStatement",
      parameters: { database: CONTROL_DATABASE, sql: ROLE_BOOTSTRAP_SQL },
      physicalResourceId: { id: ROLE_BOOTSTRAP_ID },
    });
    expect(sdkCall("Update")).toEqual(create);
  });

  it("does nothing on delete, and an update keeps its physical ID so it never replaces", () => {
    const [, bootstrap] = only("Custom::AWS");
    expect(bootstrap.Properties).not.toHaveProperty("Delete");
    expect(sdkCall("Update")["physicalResourceId"]).toEqual({ id: ROLE_BOOTSTRAP_ID });
  });

  it("targets this cluster with its own master secret", () => {
    const [cluster] = only("AWS::RDS::DBCluster");
    const [secret] = only("AWS::SecretsManager::Secret");
    const [, bootstrap] = only("Custom::AWS");
    const { text, intrinsics } = flatten(bootstrap.Properties["Create"]);
    const parameters = (JSON.parse(text) as { parameters: Record<string, string> }).parameters;
    expect(intrinsics.get(parameters["secretArn"] ?? "")).toEqual(ref(secret));
    const clusterArn = parameters["resourceArn"] ?? "";
    expect(clusterArn.startsWith("arn:aws:rds:us-east-2:407034905514:cluster:")).toBe(true);
    expect(intrinsics.get(clusterArn.slice(clusterArn.lastIndexOf(":") + 1))).toEqual(ref(cluster));
  });

  it("waits for the cluster, both instances, and the secret", () => {
    const [bootstrapId, bootstrap] = only("Custom::AWS");
    const expected = [
      only("AWS::RDS::DBCluster")[0],
      ...resources("AWS::RDS::DBInstance").map(([id]) => id),
      only("AWS::SecretsManager::Secret")[0],
      only("AWS::SecretsManager::SecretTargetAttachment")[0],
    ];
    expect(bootstrap.DependsOn, bootstrapId).toEqual(expect.arrayContaining(expected));
  });

  it("is the only principal granted the master secret, and only to execute on this cluster", () => {
    const [cluster] = only("AWS::RDS::DBCluster");
    const [secret] = only("AWS::SecretsManager::Secret");
    const policies = resources("AWS::IAM::Policy").filter(([, policy]) =>
      JSON.stringify(policy.Properties).includes(`"Ref":"${secret}"`),
    );
    expect(policies).toHaveLength(1);
    const [[, policy] = ["", undefined]] = policies;
    expect(policy?.Properties["PolicyDocument"]).toEqual({
      Version: "2012-10-17",
      Statement: [
        {
          Action: "rds-data:ExecuteStatement",
          Effect: "Allow",
          Resource: {
            "Fn::Join": ["", ["arn:aws:rds:us-east-2:407034905514:cluster:", ref(cluster)]],
          },
        },
        {
          Action: ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"],
          Effect: "Allow",
          Resource: ref(secret),
        },
      ],
    });
    for (const [, role] of resources("AWS::IAM::Role")) {
      expect(JSON.stringify(role.Properties)).not.toContain(`"Ref":"${secret}"`);
    }
  });
});

describe("the published TestEnvironment", () => {
  it("is published only after the role bootstrap succeeded", () => {
    const [bootstrap] = only("Custom::AWS");
    const [, parameter] = only("AWS::SSM::Parameter");
    expect(parameter.Properties).toMatchObject({
      Name: TEST_ENVIRONMENT_PARAMETER,
      Type: "String",
      Tier: "Standard",
    });
    expect(parameter.DependsOn).toContain(bootstrap);
  });

  it("resolves to a schema-conforming record whose hosts are the cluster's own endpoints", () => {
    const [cluster] = only("AWS::RDS::DBCluster");
    const instances = Object.fromEntries(
      resources("AWS::RDS::DBInstance").map(([id, instance]) => [
        instance.Properties["DBInstanceIdentifier"],
        id,
      ]),
    ) as Record<string, string>;
    const [, parameter] = only("AWS::SSM::Parameter");
    const { text, intrinsics } = flatten(parameter.Properties["Value"]);
    const record = JSON.parse(text) as {
      writer_host: string;
      reader_host: string;
      instances: { identifier: string; host: string }[];
    };
    const attribute = (marker: string): unknown => intrinsics.get(marker);
    expect(attribute(record.writer_host)).toEqual({ "Fn::GetAtt": [cluster, "Endpoint.Address"] });
    expect(attribute(record.reader_host)).toEqual({
      "Fn::GetAtt": [cluster, "ReadEndpoint.Address"],
    });
    for (const instance of record.instances) {
      expect(attribute(instance.host)).toEqual({
        "Fn::GetAtt": [instances[instance.identifier], "Endpoint.Address"],
      });
    }
    const deployed = JSON.parse(
      text.replace(/«\d+»/g, "parallax-ci.cluster-abc123.us-east-2.rds.amazonaws.com"),
    ) as unknown;
    const schema = JSON.parse(
      readFileSync(join(PACKAGE_ROOT, "test-environment.schema.json"), "utf8"),
    ) as object;
    const validate = new Ajv2020({ allErrors: true }).compile(schema);
    expect(validate(deployed), JSON.stringify(validate.errors)).toBe(true);
    expect(deployed).toMatchObject({
      schema: 1,
      port: 5432,
      region: "us-east-2",
      login: "parallax_conformance_login",
      cluster_id: "parallax-ci",
      ca_bundle_url: "https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem",
    });
  });
});

describe("the deployment trust", () => {
  it("deploys only through its own bootstrap's roles", () => {
    const parameters = template.toJSON()["Parameters"] as Record<string, { Default?: string }>;
    expect(parameters["BootstrapVersion"]?.Default).toBe(
      `/cdk-bootstrap/${ANCHORS.qualifier}/version`,
    );
    const synthesizer = stack.synthesizer as { cloudFormationExecutionRoleArn?: string };
    expect(JSON.stringify(stack.resolve(synthesizer.cloudFormationExecutionRoleArn))).toContain(
      `cdk-${ANCHORS.qualifier}-cfn-exec-role`,
    );
  });

  it("puts the access stack's boundary on every role it creates", () => {
    const roles = resources("AWS::IAM::Role");
    expect(roles.length).toBeGreaterThanOrEqual(4);
    for (const [id, role] of roles) {
      expect(role.Properties["PermissionsBoundary"], id).toBe(ANCHORS.boundaryPolicyArn);
    }
  });

  it("creates no identity provider, source connection, user, or managed policy of its own", () => {
    const types = new Set(Object.values(all).map((resource) => resource.Type));
    for (const type of [
      "AWS::IAM::OIDCProvider",
      "AWS::IAM::User",
      "AWS::IAM::ManagedPolicy",
      "AWS::CodeConnections::Connection",
      "AWS::CodeStarConnections::Connection",
      "AWS::CodeBuild::SourceCredential",
      "AWS::Budgets::Budget",
    ]) {
      expect(types.has(type), type).toBe(false);
    }
  });
});

describe("the runner", () => {
  function runnerStatements(): unknown[] {
    const [roleId] = resources("AWS::IAM::Role").find(([id]) =>
      id.startsWith("RunnerProjectRole"),
    ) ?? [""];
    return resources("AWS::IAM::Policy")
      .filter(([, policy]) => JSON.stringify(policy.Properties["Roles"]).includes(roleId))
      .flatMap(
        ([, policy]) => (policy.Properties["PolicyDocument"] as { Statement: unknown[] }).Statement,
      );
  }

  it("is an ephemeral private runner queued by workflow jobs, reading source through the existing connection", () => {
    const [, project] = only("AWS::CodeBuild::Project");
    expect(project.Properties).toMatchObject({
      Name: RUNNER_PROJECT_NAME,
      Source: {
        Type: "GITHUB",
        Location: "https://github.com/davidsunglee/parallax.git",
        Auth: { Type: "CODECONNECTIONS", Resource: ANCHORS.sourceConnectionArn },
        ReportBuildStatus: false,
      },
      Triggers: {
        Webhook: true,
        FilterGroups: [[{ Type: "EVENT", Pattern: "WORKFLOW_JOB_QUEUED" }]],
      },
      Environment: { PrivilegedMode: false, Type: "LINUX_CONTAINER" },
      TimeoutInMinutes: 60,
      QueuedTimeoutInMinutes: 30,
      ConcurrentBuildLimit: 1,
    });
    const subnets = (project.Properties["VpcConfig"] as { Subnets: { Ref: string }[] }).Subnets;
    expect(subnets).toHaveLength(2);
    for (const { Ref } of subnets) expect(all[Ref]?.Properties["MapPublicIpOnLaunch"]).toBe(false);
  });

  it("connects only as the conformance login and reads only the published record", () => {
    const [cluster] = only("AWS::RDS::DBCluster");
    const statements = runnerStatements() as { Action: unknown; Resource: unknown }[];
    const connect = statements.filter((statement) =>
      JSON.stringify(statement.Action).includes("rds-db:connect"),
    );
    expect(connect).toHaveLength(1);
    const { text, intrinsics } = flatten(connect[0]?.Resource);
    expect(text).toMatch(
      /^arn:aws:rds-db:us-east-2:407034905514:dbuser:«0»\/parallax_conformance_login$/,
    );
    expect(intrinsics.get("«0»")).toEqual({ "Fn::GetAtt": [cluster, "DBClusterResourceId"] });
    const parameter = statements.filter((statement) =>
      JSON.stringify(statement.Action).includes("ssm:"),
    );
    expect(parameter.map((statement) => statement.Action)).toEqual(["ssm:GetParameter"]);
    const [parameterId] = only("AWS::SSM::Parameter");
    expect(JSON.stringify(parameter[0]?.Resource)).toContain(parameterId);
  });

  it("holds no master secret, Data API, deploy, or IAM access", () => {
    const statements = runnerStatements();
    const [secret] = only("AWS::SecretsManager::Secret");
    expect(JSON.stringify(statements)).not.toContain(secret);
    for (const [action, resource] of [
      ["secretsmanager:GetSecretValue", "*"],
      ["rds-data:ExecuteStatement", "*"],
      ["sts:AssumeRole", ANCHORS.bootstrapRoleArn("deploy")],
      ["sts:AssumeRole", ANCHORS.deployRoleArn],
      ["iam:PassRole", "*"],
      ["cloudformation:UpdateStack", "*"],
      ["ssm:PutParameter", "*"],
      ["codeconnections:DeleteConnection", ANCHORS.sourceConnectionArn],
    ]) {
      expect(allowed(statements, String(action), String(resource)), String(action)).toBe(false);
    }
    expect(
      allowed(statements, "codeconnections:GetConnectionToken", ANCHORS.sourceConnectionArn),
    ).toBe(true);
  });
});
