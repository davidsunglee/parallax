import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as codebuild from "aws-cdk-lib/aws-codebuild";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { PolicyStatement } from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import type * as rds from "aws-cdk-lib/aws-rds";
import type * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { SOURCE_USE_ACTIONS } from "../access-policies.ts";
import type { Repository } from "../rollout-configuration.ts";

export interface RunnerProjectProps {
  readonly projectName: string;
  readonly vpc: ec2.IVpc;
  readonly repository: Repository;
  readonly sourceConnectionArn: string;
  readonly cluster: rds.DatabaseCluster;
  /** The one database login the runner may authenticate as. */
  readonly login: string;
  readonly testEnvironment: ssm.IStringParameter;
}

/**
 * An ephemeral GitHub Actions runner per queued workflow job, in the private
 * subnets. It reaches the cluster only as the IAM-authenticated login and
 * reads only the published record: it holds no master secret, no Data API,
 * and no deploy access, because an approved pull request's code runs on it.
 */
export class RunnerProject extends Construct {
  readonly project: codebuild.Project;
  readonly securityGroup: ec2.ISecurityGroup;

  constructor(scope: Construct, id: string, props: RunnerProjectProps) {
    super(scope, id);
    this.securityGroup = new ec2.SecurityGroup(this, "SecurityGroup", {
      vpc: props.vpc,
      description: "Ephemeral CI runners: outbound only",
      allowAllOutbound: true,
    });
    this.project = new codebuild.Project(this, "Project", {
      projectName: props.projectName,
      description: "Ephemeral GitHub Actions runners for the Parallax cloud suite",
      source: codebuild.Source.gitHub({
        owner: props.repository.owner,
        repo: props.repository.name,
        webhook: true,
        // The cloud verdict judges the workflow's own jobs; a second status would compete with it.
        reportBuildStatus: false,
        webhookFilters: [
          codebuild.FilterGroup.inEventOf(codebuild.EventAction.WORKFLOW_JOB_QUEUED),
        ],
      }),
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_8_0,
        computeType: codebuild.ComputeType.MEDIUM,
        privileged: false,
      },
      vpc: props.vpc,
      subnetSelection: { subnets: props.vpc.privateSubnets },
      securityGroups: [this.securityGroup],
      timeout: Duration.minutes(60),
      queuedTimeout: Duration.minutes(30),
      concurrentBuildLimit: 1,
      badge: false,
      logging: {
        cloudWatch: {
          logGroup: new logs.LogGroup(this, "Logs", {
            retention: logs.RetentionDays.ONE_MONTH,
            removalPolicy: RemovalPolicy.DESTROY,
          }),
        },
      },
    });
    // The project reads its source through the existing connection rather than
    // account-wide source credentials, which the library cannot yet express.
    (this.project.node.defaultChild as codebuild.CfnProject).addPropertyOverride("Source.Auth", {
      Type: "CODECONNECTIONS",
      Resource: props.sourceConnectionArn,
    });
    this.project.addToRolePolicy(
      new PolicyStatement({
        actions: [...SOURCE_USE_ACTIONS],
        resources: [props.sourceConnectionArn],
      }),
    );
    props.cluster.grantConnect(this.project, props.login);
    this.project.addToRolePolicy(
      new PolicyStatement({
        actions: ["ssm:GetParameter"],
        resources: [props.testEnvironment.parameterArn],
      }),
    );
    props.cluster.connections.allowDefaultPortFrom(
      this.securityGroup,
      "The cloud suite on a CI runner",
    );
  }
}
