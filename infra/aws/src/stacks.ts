import type { App } from "aws-cdk-lib";
import { AccessStack } from "./access-stack.ts";
import { CONFIGURATION_CONTEXT_KEY, environmentConfiguration } from "./configuration.ts";
import { EnvironmentStack } from "./environment-stack.ts";
import { ROLLOUT_CONTEXT_KEY, rolloutConfiguration } from "./rollout-configuration.ts";
import { ACCESS_STACK_NAME, ENVIRONMENT_STACK_NAME, trustAnchors } from "./trust.ts";

export interface Stacks {
  readonly access: AccessStack;
  readonly environment: EnvironmentStack;
}

/** Define both stacks on *app* from the configuration its committed context holds. */
export function defineStacks(app: App): Stacks {
  const configuration = environmentConfiguration(app.node.tryGetContext(CONFIGURATION_CONTEXT_KEY));
  const rollout = rolloutConfiguration(app.node.tryGetContext(ROLLOUT_CONTEXT_KEY), configuration);
  const anchors = trustAnchors(configuration, rollout);
  return {
    access: new AccessStack(app, ACCESS_STACK_NAME, {
      anchors,
      budget: rollout.budget.ownership === "stack" ? rollout.budget : undefined,
    }),
    environment: new EnvironmentStack(app, ENVIRONMENT_STACK_NAME, {
      configuration,
      rollout,
      anchors,
    }),
  };
}
