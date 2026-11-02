import {
  CfnOutput,
  CfnParameter,
  DefaultStackSynthesizer,
  PermissionsBoundary,
  Stack,
  Tags,
  type IStackSynthesizer,
} from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import type { Construct } from "constructs";
import type { EnvironmentConfiguration } from "./configuration.ts";
import { AuroraCluster } from "./constructs/aurora-cluster.ts";
import { PrivateNetwork } from "./constructs/private-network.ts";
import { RunnerProject } from "./constructs/runner-project.ts";
import { CONFORMANCE_LOGIN } from "./role-bootstrap.ts";
import type { RolloutConfiguration } from "./rollout-configuration.ts";
import { testEnvironment, TestEnvironmentParameter } from "./test-environment.ts";
import {
  BOUNDARY_POLICY_NAME,
  ENVIRONMENT_TAGS,
  RUNNER_PROJECT_NAME,
  type TrustAnchors,
} from "./trust.ts";

/** The deploy input naming the NAT instance's image. */
export const NAT_IMAGE_PARAMETER = "NatInstanceImage";

/** The deploy input naming the commit being deployed. */
export const REVISION_PARAMETER = "DeployedRevision";

/** The outputs recording what the latest role bootstrap converged, and for which revision. */
export const ROLE_BOOTSTRAP_OUTPUTS = {
  facts: "RoleBootstrapFacts",
  revision: "RoleBootstrapRevision",
} as const;

export interface EnvironmentStackProps {
  readonly configuration: EnvironmentConfiguration;
  readonly rollout: RolloutConfiguration;
  readonly anchors: TrustAnchors;
}

/**
 * Everything the cloud suite runs against: the private network, the cluster,
 * the runner, and the published record. It deploys only through its own
 * bootstrap's roles, and every role it creates carries the access stack's
 * boundary.
 */
export class EnvironmentStack extends Stack {
  readonly network: PrivateNetwork;
  readonly aurora: AuroraCluster;
  readonly testEnvironment: TestEnvironmentParameter;
  readonly runner: RunnerProject;
  private readonly zones: readonly string[];

  constructor(scope: Construct, id: string, props: EnvironmentStackProps) {
    const { configuration, rollout, anchors } = props;
    super(scope, id, {
      env: { account: configuration.account, region: configuration.region },
      // jsii's `T | undefined` class members versus the interface's optional ones
      synthesizer: new DefaultStackSynthesizer({
        qualifier: anchors.qualifier,
      }) as IStackSynthesizer,
      permissionsBoundary: PermissionsBoundary.fromName(BOUNDARY_POLICY_NAME),
      terminationProtection: true,
      analyticsReporting: false,
    });
    this.zones = configuration.availabilityZones;
    // An explicit, reviewed deploy input rather than a lookup: CloudFormation keeps
    // the previous value on every deploy that does not supply one, so the instance
    // is replaced only when a reviewed deploy names a new image.
    const natImage = new CfnParameter(this, NAT_IMAGE_PARAMETER, {
      type: "AWS::EC2::Image::Id",
      description: "The reviewed Amazon Linux 2023 arm64 image the NAT instance runs",
    });
    this.network = new PrivateNetwork(this, "Network", {
      availabilityZones: configuration.availabilityZones,
      natInstanceType: new ec2.InstanceType(configuration.natInstanceType),
      natImage: ec2.MachineImage.genericLinux({ [configuration.region]: natImage.valueAsString }),
    });
    // Supplied by every deployment rather than looked up, so synthesis stays
    // offline and a new revision always runs the role bootstrap again.
    const revision = new CfnParameter(this, REVISION_PARAMETER, {
      type: "String",
      allowedPattern: "^[0-9a-f]{40}$",
      description: "The commit this deployment deploys",
    });
    this.aurora = new AuroraCluster(this, "Aurora", {
      vpc: this.network.vpc,
      capacity: configuration.aurora,
      revision: revision.valueAsString,
    });
    new CfnOutput(this, ROLE_BOOTSTRAP_OUTPUTS.facts, {
      value: this.aurora.bootstrap.getAttString("Facts"),
    });
    new CfnOutput(this, ROLE_BOOTSTRAP_OUTPUTS.revision, {
      value: this.aurora.bootstrap.getAttString("Revision"),
    });
    this.testEnvironment = new TestEnvironmentParameter(this, "TestEnvironment", {
      record: testEnvironment(this.aurora, configuration.region),
      after: [this.aurora.bootstrap],
    });
    this.runner = new RunnerProject(this, "Runner", {
      projectName: RUNNER_PROJECT_NAME,
      vpc: this.network.vpc,
      repository: rollout.repository,
      sourceConnectionArn: anchors.sourceConnectionArn,
      cluster: this.aurora.cluster,
      login: CONFORMANCE_LOGIN,
      testEnvironment: this.testEnvironment.parameter,
    });
    for (const [key, value] of Object.entries(ENVIRONMENT_TAGS)) {
      Tags.of(this).add(key, value);
    }
  }

  /** The configured zones, so nothing in the stack has to look the account's zones up. */
  override get availabilityZones(): string[] {
    return [...this.zones];
  }
}
