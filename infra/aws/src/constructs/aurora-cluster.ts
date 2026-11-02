import { Duration, RemovalPolicy, Validations } from "aws-cdk-lib";
import type * as ec2 from "aws-cdk-lib/aws-ec2";
import { PolicyStatement } from "aws-cdk-lib/aws-iam";
import type { ISecret } from "aws-cdk-lib/aws-secretsmanager";
import * as rds from "aws-cdk-lib/aws-rds";
import {
  AwsCustomResource,
  AwsCustomResourcePolicy,
  PhysicalResourceId,
  type AwsSdkCall,
} from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";
import type { AuroraCapacity } from "../configuration.ts";
import { CONTROL_DATABASE, ROLE_BOOTSTRAP_SQL } from "../role-bootstrap.ts";

export const CLUSTER_IDENTIFIER = "parallax-ci";
export const POSTGRES_PORT = 5432;
export const ENGINE_VERSION = rds.AuroraPostgresEngineVersion.VER_18_6;

/** The physical ID every bootstrap run reports, so a changed statement updates rather than replaces it. */
export const ROLE_BOOTSTRAP_ID = "parallax-ci-role-bootstrap";

export interface ClusterMember {
  readonly identifier: string;
  readonly role: "writer" | "reader";
  /** The member's construct ID within the cluster. */
  readonly id: string;
}

const WRITER: ClusterMember = {
  identifier: `${CLUSTER_IDENTIFIER}-writer`,
  role: "writer",
  id: "Writer",
};
const READERS: readonly ClusterMember[] = [
  { identifier: `${CLUSTER_IDENTIFIER}-reader`, role: "reader", id: "Reader" },
];

/** Every instance of the cluster, its writer first. */
export const CLUSTER_MEMBERS: readonly ClusterMember[] = [WRITER, ...READERS];

export interface AuroraClusterProps {
  readonly vpc: ec2.IVpc;
  readonly capacity: AuroraCapacity;
}

function serverlessInstance(member: ClusterMember): rds.IClusterInstance {
  return rds.ClusterInstance.serverlessV2(member.id, {
    instanceIdentifier: member.identifier,
    publiclyAccessible: false,
    autoMinorVersionUpgrade: false,
    // A reader in the writer's tier pauses and resumes with it.
    ...(member.role === "reader" ? { scaleWithWriter: true } : {}),
  });
}

/**
 * A private, pinned Aurora PostgreSQL Serverless v2 cluster with one writer and
 * one reader, IAM authentication, and the conformance roles bootstrapped
 * through the Data API.
 */
export class AuroraCluster extends Construct {
  readonly cluster: rds.DatabaseCluster;
  readonly masterSecret: ISecret;
  readonly bootstrap: AwsCustomResource;

  constructor(scope: Construct, id: string, props: AuroraClusterProps) {
    super(scope, id);
    const engine = rds.DatabaseClusterEngine.auroraPostgres({ version: ENGINE_VERSION });
    // jsii declares a class's optional members as `T | undefined` properties, which
    // exactOptionalPropertyTypes tells apart from the interface's optional ones.
    this.masterSecret = new rds.DatabaseSecret(this, "MasterSecret", {
      username: "parallax_admin",
    }) as ISecret;
    this.cluster = new rds.DatabaseCluster(this, "Cluster", {
      engine,
      clusterIdentifier: CLUSTER_IDENTIFIER,
      writer: serverlessInstance(WRITER),
      readers: READERS.map(serverlessInstance),
      serverlessV2MinCapacity: props.capacity.minCapacity,
      serverlessV2MaxCapacity: props.capacity.maxCapacity,
      serverlessV2AutoPauseDuration: Duration.seconds(props.capacity.autoPauseSeconds),
      vpc: props.vpc,
      vpcSubnets: { subnets: props.vpc.privateSubnets },
      port: POSTGRES_PORT,
      defaultDatabaseName: CONTROL_DATABASE,
      credentials: rds.Credentials.fromSecret(this.masterSecret),
      iamAuthentication: true,
      enableDataApi: true,
      storageEncrypted: true,
      storageType: rds.DBClusterStorageType.AURORA,
      parameterGroup: new rds.ParameterGroup(this, "Parameters", {
        engine,
        parameters: { "rds.force_ssl": "1" },
      }),
      engineLifecycleSupport: rds.EngineLifecycleSupport.OPEN_SOURCE_RDS_EXTENDED_SUPPORT_DISABLED,
      backup: { retention: Duration.days(1) },
      copyTagsToSnapshot: true,
      deletionProtection: true,
      removalPolicy: RemovalPolicy.SNAPSHOT,
    });
    Validations.of(this.cluster).acknowledge({
      id: "CloudFormation-Validate::E9006",
      reason:
        "The synth-time CloudFormation schema lists Aurora PostgreSQL versions only through 18.4, " +
        "behind the 18.6 release this library pins and the deploy-time offering check verifies.",
    });
    this.bootstrap = this.roleBootstrap();
  }

  /** The instance endpoint address of *member*, resolved at deploy time. */
  memberHost(member: ClusterMember): string {
    const instance = this.cluster.node.findChild(member.id).node.defaultChild as rds.CfnDBInstance;
    return instance.attrEndpointAddress;
  }

  private roleBootstrap(): AwsCustomResource {
    const secretArn = this.masterSecret.secretArn;
    const call: AwsSdkCall = {
      service: "rds-data",
      action: "ExecuteStatement",
      parameters: {
        resourceArn: this.cluster.clusterArn,
        secretArn,
        database: CONTROL_DATABASE,
        sql: ROLE_BOOTSTRAP_SQL,
      },
      physicalResourceId: PhysicalResourceId.of(ROLE_BOOTSTRAP_ID),
    };
    // No delete call: removing the resource must never drop what earlier runs converged.
    const bootstrap = new AwsCustomResource(this, "RoleBootstrap", {
      onCreate: call,
      onUpdate: call,
      installLatestAwsSdk: false,
      timeout: Duration.minutes(5),
      policy: AwsCustomResourcePolicy.fromStatements([
        new PolicyStatement({
          actions: ["rds-data:ExecuteStatement"],
          resources: [this.cluster.clusterArn],
        }),
        new PolicyStatement({
          actions: ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
          resources: [secretArn],
        }),
      ]),
    });
    // The Data API answers only once the cluster, its instances, and the secret it
    // authenticates with all exist, which references alone do not order.
    bootstrap.node.addDependency(this.cluster, this.masterSecret);
    return bootstrap;
  }
}
