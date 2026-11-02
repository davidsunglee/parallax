import {
  CfnOutput,
  Duration,
  LegacyStackSynthesizer,
  Stack,
  Tags,
  type IStackSynthesizer,
} from "aws-cdk-lib";
import { CfnBudget } from "aws-cdk-lib/aws-budgets";
import * as iam from "aws-cdk-lib/aws-iam";
import type { Construct } from "constructs";
import {
  boundaryPolicy,
  deployRoleConditions,
  deployRolePolicy,
  executionPolicy,
} from "./access-policies.ts";
import type { StackBudget } from "./rollout-configuration.ts";
import {
  BOUNDARY_POLICY_NAME,
  DEPLOY_ROLE_NAME,
  ENVIRONMENT_TAG,
  ENVIRONMENT_TAGS,
  EXECUTION_POLICY_NAME,
  type TrustAnchors,
} from "./trust.ts";

/** The access stack's outputs, which setup checks after it deploys. */
export const ACCESS_OUTPUTS = {
  deployRoleArn: "DeployRoleArn",
  executionPolicyArn: "ExecutionPolicyArn",
  boundaryPolicyArn: "BoundaryPolicyArn",
} as const;

export interface AccessStackProps {
  readonly anchors: TrustAnchors;
  readonly budget: StackBudget | undefined;
}

/** The cost filters a stack-owned budget watches the tagged environment through. */
export const STACK_BUDGET_FILTERS: Readonly<Record<string, readonly string[]>> = {
  TagKeyValue: [`user:${ENVIRONMENT_TAG.join("$")}`],
};

function notification(type: "ACTUAL" | "FORECASTED", recipients: readonly string[]) {
  return {
    notification: {
      notificationType: type,
      comparisonOperator: "GREATER_THAN",
      threshold: 100,
      thresholdType: "PERCENTAGE",
    },
    subscribers: recipients.map((address) => ({ subscriptionType: "EMAIL", address })),
  };
}

/**
 * The deploy trust path: the role protected CI deploys with, the bounded
 * policy its CloudFormation execution role holds, and the boundary every role
 * the environment creates carries. A maintainer deploys it with their own
 * credentials, never through the bootstrap roles or the role it defines, so
 * no CI identity can change who may deploy.
 */
export class AccessStack extends Stack {
  readonly deployRole: iam.Role;

  constructor(scope: Construct, id: string, props: AccessStackProps) {
    const { anchors } = props;
    super(scope, id, {
      env: { account: anchors.account, region: anchors.region },
      // It deploys before the bootstrap exists, so it may name no bootstrap
      // role or asset bucket: the CLI deploys it with the maintainer's own
      // credentials and passes its template inline. The cast bridges jsii's
      // `T | undefined` class members and the interface's optional ones.
      synthesizer: new LegacyStackSynthesizer() as IStackSynthesizer,
      terminationProtection: true,
      analyticsReporting: false,
    });
    const provider = iam.OpenIdConnectProvider.fromOpenIdConnectProviderArn(
      this,
      "GitHubProvider",
      anchors.oidcProviderArn,
    );
    this.deployRole = new iam.Role(this, "DeployRole", {
      roleName: DEPLOY_ROLE_NAME,
      description: "Protected CI deploys the environment stack through the bootstrap roles",
      assumedBy: new iam.WebIdentityPrincipal(
        provider.openIdConnectProviderArn,
        deployRoleConditions(anchors),
      ),
      maxSessionDuration: Duration.hours(1),
      inlinePolicies: { deploy: deployRolePolicy(anchors) },
    });
    const execution = new iam.ManagedPolicy(this, "ExecutionPolicy", {
      managedPolicyName: EXECUTION_POLICY_NAME,
      description: "What CloudFormation may do while deploying the environment stack",
      document: executionPolicy(anchors),
    });
    const boundary = new iam.ManagedPolicy(this, "Boundary", {
      managedPolicyName: BOUNDARY_POLICY_NAME,
      description: "The most the execution role and every environment role may do",
      document: boundaryPolicy(anchors),
    });
    if (props.budget !== undefined) this.budget(props.budget);
    new CfnOutput(this, ACCESS_OUTPUTS.deployRoleArn, { value: this.deployRole.roleArn });
    new CfnOutput(this, ACCESS_OUTPUTS.executionPolicyArn, { value: execution.managedPolicyArn });
    new CfnOutput(this, ACCESS_OUTPUTS.boundaryPolicyArn, { value: boundary.managedPolicyArn });
    for (const [key, value] of Object.entries(ENVIRONMENT_TAGS)) {
      Tags.of(this).add(key, value);
    }
  }

  /** A monthly cost budget over the environment's tagged resources, alerting on actual and forecast spend. */
  private budget(budget: StackBudget): void {
    new CfnBudget(this, "Budget", {
      budget: {
        budgetName: budget.name,
        budgetType: "COST",
        timeUnit: "MONTHLY",
        budgetLimit: { amount: budget.limitUsd, unit: "USD" },
        // Billing must have the tag activated for cost allocation before it filters anything.
        costFilters: STACK_BUDGET_FILTERS,
      },
      notificationsWithSubscribers: [
        notification("ACTUAL", budget.recipients),
        notification("FORECASTED", budget.recipients),
      ],
    });
  }
}
