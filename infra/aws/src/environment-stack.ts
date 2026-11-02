import { CfnParameter, Stack, Tags, type App, type StackProps } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import type { Construct } from "constructs";
import {
  CONFIGURATION_CONTEXT_KEY,
  environmentConfiguration,
  type EnvironmentConfiguration,
} from "./configuration.ts";
import { AuroraCluster } from "./constructs/aurora-cluster.ts";
import { PrivateNetwork } from "./constructs/private-network.ts";
import { testEnvironment, TestEnvironmentParameter } from "./test-environment.ts";

export const ENVIRONMENT_STACK_NAME = "ParallaxCiEnvironmentStack";

/** The deploy input naming the NAT instance's image. */
export const NAT_IMAGE_PARAMETER = "NatInstanceImage";

/** Cost-allocation tags every resource in the environment carries. */
export const ENVIRONMENT_TAGS: Readonly<Record<string, string>> = {
  "parallax:project": "parallax",
  "parallax:environment": "ci",
};

export interface EnvironmentStackProps extends StackProps {
  readonly configuration: EnvironmentConfiguration;
}

/** Everything the cloud suite runs against: the private network, the cluster, and the published record. */
export class EnvironmentStack extends Stack {
  readonly network: PrivateNetwork;
  readonly aurora: AuroraCluster;
  readonly testEnvironment: TestEnvironmentParameter;
  private readonly zones: readonly string[];

  constructor(scope: Construct, id: string, props: EnvironmentStackProps) {
    const { configuration } = props;
    super(scope, id, {
      ...props,
      env: { account: configuration.account, region: configuration.region },
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
    this.aurora = new AuroraCluster(this, "Aurora", {
      vpc: this.network.vpc,
      capacity: configuration.aurora,
    });
    this.testEnvironment = new TestEnvironmentParameter(this, "TestEnvironment", {
      record: testEnvironment(this.aurora, configuration.region),
      after: [this.aurora.bootstrap],
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

/** Define the environment on *app* from the configuration its committed context holds. */
export function defineEnvironment(app: App): EnvironmentStack {
  const configuration = environmentConfiguration(app.node.tryGetContext(CONFIGURATION_CONTEXT_KEY));
  return new EnvironmentStack(app, ENVIRONMENT_STACK_NAME, { configuration });
}
