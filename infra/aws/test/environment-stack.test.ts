import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Template } from "aws-cdk-lib/assertions";
import { Ajv2020 } from "ajv/dist/2020.js";
import { beforeAll, describe, expect, it } from "vitest";
import { ConfigurationError } from "../src/configuration.ts";
import { ROLE_BOOTSTRAP_ID } from "../src/constructs/aurora-cluster.ts";
import {
  defineEnvironment,
  ENVIRONMENT_STACK_NAME,
  ENVIRONMENT_TAGS,
  NAT_IMAGE_PARAMETER,
  type EnvironmentStack,
} from "../src/environment-stack.ts";
import { CONTROL_DATABASE, ROLE_BOOTSTRAP_SQL } from "../src/role-bootstrap.ts";
import { TEST_ENVIRONMENT_PARAMETER } from "../src/test-environment.ts";
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

function ref(id: string): { Ref: string } {
  return { Ref: id };
}

beforeAll(() => {
  stack = defineEnvironment(committedApp());
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
    expect(() => defineEnvironment(committedApp({ "parallax:environment": undefined }))).toThrow(
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
    expect(resources("AWS::EC2::SecurityGroupIngress")).toHaveLength(0);
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

  it("admits no inbound traffic yet", () => {
    const [, cluster] = only("AWS::RDS::DBCluster");
    const [group] = cluster.Properties["VpcSecurityGroupIds"] as [{ "Fn::GetAtt": [string] }];
    expect(all[group["Fn::GetAtt"][0]]?.Properties).not.toHaveProperty("SecurityGroupIngress");
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
