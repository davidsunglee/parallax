import { createHash } from "node:crypto";
import { Aspects, Duration, Stack, Validations } from "aws-cdk-lib";
import { Alarm, ComparisonOperator, Metric, TreatMissingData } from "aws-cdk-lib/aws-cloudwatch";
import { Ec2Action, Ec2InstanceAction } from "aws-cdk-lib/aws-cloudwatch-actions";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Construct } from "constructs";

export const VPC_CIDR = "10.80.0.0/16";

/**
 * What the NAT instance runs on first boot to forward the private subnets'
 * traffic. CDK's default fails on a 512 MB instance, whose memory dnf exhausts
 * before iptables is installed, and relies on `route`, which Amazon Linux 2023
 * does not ship; this one installs through a temporary swap file and finds the
 * outbound interface with `ip`.
 */
export const NAT_SETUP_COMMANDS = [
  "set -euo pipefail",
  "fallocate -l 1G /nat-setup.swap",
  "chmod 600 /nat-setup.swap",
  "mkswap /nat-setup.swap",
  "swapon /nat-setup.swap",
  "dnf install -y iptables-services",
  "swapoff /nat-setup.swap",
  "rm -f /nat-setup.swap",
  "systemctl enable --now iptables",
  'echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/90-nat-forwarding.conf',
  "sysctl -p /etc/sysctl.d/90-nat-forwarding.conf",
  "outbound=$(ip -o -4 route show default | awk '{print $5}')",
  'test -n "$outbound"',
  'iptables -t nat -A POSTROUTING -o "$outbound" -j MASQUERADE',
  "iptables -F FORWARD",
  "iptables-save > /etc/sysconfig/iptables",
] as const;

export interface PrivateNetworkProps {
  readonly availabilityZones: readonly string[];
  readonly natInstanceType: ec2.InstanceType;
  readonly natImage: ec2.IMachineImage;
}

/**
 * A VPC whose workloads live in private subnets and reach the internet through
 * one NAT instance, with S3 traffic kept off it by a gateway endpoint.
 */
export class PrivateNetwork extends Construct {
  readonly vpc: ec2.IVpc;
  readonly nat: ec2.NatInstanceProviderV2;

  constructor(scope: Construct, id: string, props: PrivateNetworkProps) {
    super(scope, id);
    const userData = ec2.UserData.forLinux();
    userData.addCommands(...NAT_SETUP_COMMANDS);
    this.nat = ec2.NatProvider.instanceV2({
      instanceType: props.natInstanceType,
      machineImage: props.natImage,
      defaultAllowedTraffic: ec2.NatTrafficDirection.OUTBOUND_ONLY,
      userData,
    });
    this.vpc = new ec2.Vpc(this, "Vpc", {
      ipAddresses: ec2.IpAddresses.cidr(VPC_CIDR),
      availabilityZones: [...props.availabilityZones],
      natGateways: 1,
      natGatewayProvider: this.nat,
      restrictDefaultSecurityGroup: true,
      subnetConfiguration: [
        { name: "public", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "private", subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS, cidrMask: 20 },
      ],
      gatewayEndpoints: {
        S3: { service: ec2.GatewayVpcEndpointAwsService.S3 },
      },
    }) as ec2.IVpc; // jsii's `T | undefined` class members versus the interface's optional ones
    Validations.of(this.vpc).acknowledge({
      id: "CloudFormation-Validate::W3010",
      reason: "The zones are committed configuration so that synthesis never looks them up.",
    });
    for (const subnet of this.vpc.privateSubnets) {
      this.nat.securityGroup.addIngressRule(
        ec2.Peer.ipv4(subnet.ipv4CidrBlock),
        ec2.Port.allTraffic(),
        "Traffic the NAT instance forwards for a private subnet",
      );
    }
    // User data runs only on an instance's first boot, so a change to it must
    // replace the instance: its digest joins the logical ID.
    const setup = createHash("sha256").update(userData.render()).digest("hex").slice(0, 16);
    this.nat.gatewayInstances.forEach((instance, index) => {
      instance.instance.overrideLogicalId(
        `${Stack.of(this).getLogicalId(instance.instance)}${setup}`,
      );
      this.recoveryAlarm(instance, index);
    });
    Aspects.of(this).add(new ec2.InstanceRequireImdsv2Aspect());
  }

  /** Recovers the instance onto healthy hardware when AWS's own system check fails. */
  private recoveryAlarm(instance: ec2.Instance, index: number): void {
    const alarm = new Alarm(this, `NatRecovery${String(index)}`, {
      alarmDescription: "Recover the NAT instance when its system status check fails",
      metric: new Metric({
        namespace: "AWS/EC2",
        metricName: "StatusCheckFailed_System",
        dimensionsMap: { InstanceId: instance.instanceId },
        statistic: "Maximum",
        period: Duration.minutes(1),
      }),
      threshold: 1,
      evaluationPeriods: 2,
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: TreatMissingData.MISSING,
    });
    alarm.addAlarmAction(new Ec2Action(Ec2InstanceAction.RECOVER));
  }
}
