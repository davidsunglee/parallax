import { cpSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  AssetHashType,
  CustomResource,
  DockerImage,
  Duration,
  RemovalPolicy,
  Validations,
} from "aws-cdk-lib";
import type * as ec2 from "aws-cdk-lib/aws-ec2";
import * as lambda from "aws-cdk-lib/aws-lambda";
import type { ISecret } from "aws-cdk-lib/aws-secretsmanager";
import * as rds from "aws-cdk-lib/aws-rds";
import { Provider } from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";
import type { AuroraCapacity } from "../configuration.ts";
import {
  CONTROL_DATABASE,
  CONVERGED_ROLE_FACTS,
  ROLE_BOOTSTRAP_SQL,
  ROLE_FACTS_SQL,
} from "../role-bootstrap.ts";

export const CLUSTER_IDENTIFIER = "parallax-ci";
export const POSTGRES_PORT = 5432;
export const ENGINE_VERSION = rds.AuroraPostgresEngineVersion.VER_18_6;

/** The physical ID every bootstrap run reports, so a changed statement updates rather than replaces it. */
export const ROLE_BOOTSTRAP_ID = "parallax-ci-role-bootstrap";

/** The custom resource type of the role bootstrap. */
export const ROLE_BOOTSTRAP_TYPE = "Custom::RoleBootstrap";

/** The runtime the role-bootstrap handler runs on, which also supplies its Secrets Manager client. */
export const ROLE_BOOTSTRAP_RUNTIME = lambda.Runtime.NODEJS_24_X;

/** The master user, which the role bootstrap runs as. */
export const MASTER_USER = "parallax_admin";

/** The runtime's bundle of Amazon CA certificates, which Node.js 20 and later runtimes leave unloaded. */
export const RUNTIME_CA_BUNDLE = "/var/runtime/ca-cert.pem";

/**
 * The handler's directory beside this module: its TypeScript source when the
 * app runs from source, and its compiled `index.mjs` when it runs from the
 * build, which is the only form a deployment ships.
 */
const ROLE_BOOTSTRAP_HANDLER = fileURLToPath(new URL("../role-bootstrap-handler", import.meta.url));

/** The installed postgres.js package, which the handler's asset carries beside it. */
const POSTGRES_PACKAGE = dirname(dirname(fileURLToPath(import.meta.resolve("postgres"))));

/**
 * The handler's asset: its own directory plus the parts of postgres.js the
 * runtime loads, its manifest and ES module sources, copied at synthesis rather
 * than bundled, since the driver has no dependencies of its own.
 */
function roleBootstrapCode(): lambda.Code {
  return lambda.Code.fromAsset(ROLE_BOOTSTRAP_HANDLER, {
    assetHashType: AssetHashType.OUTPUT,
    bundling: {
      // Required by the type; local bundling always succeeds, so it is never pulled.
      image: DockerImage.fromRegistry("scratch"),
      local: {
        tryBundle(outputDir) {
          cpSync(ROLE_BOOTSTRAP_HANDLER, outputDir, { recursive: true });
          for (const part of ["package.json", "src"]) {
            cpSync(
              join(POSTGRES_PACKAGE, part),
              join(outputDir, "node_modules", "postgres", part),
              {
                recursive: true,
              },
            );
          }
          return true;
        },
      },
    },
  });
}

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
  /** The revision being deployed; each new one runs the role bootstrap again. */
  readonly revision: string;
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
 * one reader, IAM authentication, and the conformance roles bootstrapped from
 * inside the VPC.
 */
export class AuroraCluster extends Construct {
  readonly cluster: rds.DatabaseCluster;
  readonly masterSecret: ISecret;
  readonly bootstrap: CustomResource;

  constructor(scope: Construct, id: string, props: AuroraClusterProps) {
    super(scope, id);
    const engine = rds.DatabaseClusterEngine.auroraPostgres({ version: ENGINE_VERSION });
    // jsii declares a class's optional members as `T | undefined` properties, which
    // exactOptionalPropertyTypes tells apart from the interface's optional ones.
    this.masterSecret = new rds.DatabaseSecret(this, "MasterSecret", {
      username: MASTER_USER,
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
      enableDataApi: false,
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
    this.bootstrap = this.roleBootstrap(props.vpc, props.revision);
  }

  /** The instance endpoint address of *member*, resolved at deploy time. */
  memberHost(member: ClusterMember): string {
    const instance = this.cluster.node.findChild(member.id).node.defaultChild as rds.CfnDBInstance;
    return instance.attrEndpointAddress;
  }

  private roleBootstrap(vpc: ec2.IVpc, revision: string): CustomResource {
    const handler = new lambda.Function(this, "RoleBootstrapHandler", {
      description: "Converges the conformance roles as the master user and reads them back",
      runtime: ROLE_BOOTSTRAP_RUNTIME,
      architecture: lambda.Architecture.ARM_64,
      code: roleBootstrapCode(),
      handler: "index.handler",
      timeout: Duration.minutes(5),
      vpc,
      vpcSubnets: { subnets: vpc.privateSubnets },
      environment: { NODE_EXTRA_CA_CERTS: RUNTIME_CA_BUNDLE },
    });
    this.cluster.connections.allowDefaultPortFrom(handler, "The role bootstrap");
    // Once the first run has made the master a member of rds_iam, an IAM token is
    // the only way it signs in; the secret serves that first run alone.
    this.cluster.grantConnect(handler, MASTER_USER);
    this.masterSecret.grantRead(handler);
    const provider = new Provider(this, "RoleBootstrapProvider", { onEventHandler: handler });
    // No delete action: removing the resource must never drop what earlier runs converged.
    const bootstrap = new CustomResource(this, "RoleBootstrap", {
      serviceToken: provider.serviceToken,
      resourceType: ROLE_BOOTSTRAP_TYPE,
      properties: {
        Id: ROLE_BOOTSTRAP_ID,
        Host: this.cluster.clusterEndpoint.hostname,
        Port: String(POSTGRES_PORT),
        User: MASTER_USER,
        Database: CONTROL_DATABASE,
        SecretArn: this.masterSecret.secretArn,
        Sql: ROLE_BOOTSTRAP_SQL,
        FactsSql: ROLE_FACTS_SQL,
        ExpectedFacts: JSON.stringify(CONVERGED_ROLE_FACTS),
        Revision: revision,
      },
    });
    // The writer accepts the handler only once the cluster, its instances, the
    // ingress admitting the handler, and the secret all exist, which references
    // alone do not order.
    bootstrap.node.addDependency(this.cluster, this.masterSecret);
    return bootstrap;
  }
}
