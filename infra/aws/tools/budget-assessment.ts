import type { ManualBudget, StackBudget } from "../src/rollout-configuration.ts";
import { ACCESS_STACK_NAME } from "../src/trust.ts";
import { CHECK, type Finding, type Sources } from "./findings.ts";

/** What one existing budget is, as far as the guardrail is concerned. */
export interface BudgetFacts {
  readonly name: string;
  /** A monthly cost budget in US dollars: the shape a spending guardrail has. */
  readonly guardrailShape: boolean;
  readonly limitUsd: number;
  /** The email recipients of its actual-spend and forecast-spend alerts. */
  readonly actual: readonly string[];
  readonly forecast: readonly string[];
}

interface BudgetJson {
  readonly BudgetName?: string;
  readonly BudgetType?: string;
  readonly TimeUnit?: string;
  readonly BudgetLimit?: { Amount?: string; Unit?: string };
}

interface NotificationJson {
  readonly NotificationType?: string;
}

function recipients(
  read: Sources,
  account: string,
  name: string,
  notification: NotificationJson,
): string[] {
  const { Subscribers: subscribers = [] } = read.aws([
    "budgets",
    "describe-subscribers-for-notification",
    "--account-id",
    account,
    "--budget-name",
    name,
    "--notification",
    JSON.stringify(notification),
  ]) as { Subscribers?: readonly { SubscriptionType?: string; Address?: string }[] };
  return subscribers
    .filter((subscriber) => subscriber.SubscriptionType === "EMAIL")
    .map((subscriber) => String(subscriber.Address));
}

function facts(read: Sources, account: string, budget: BudgetJson): BudgetFacts {
  const name = String(budget.BudgetName);
  const { Notifications: notifications = [] } = read.aws([
    "budgets",
    "describe-notifications-for-budget",
    "--account-id",
    account,
    "--budget-name",
    name,
  ]) as { Notifications?: readonly NotificationJson[] };
  const alerted = (type: string): string[] =>
    notifications
      .filter((notification) => notification.NotificationType === type)
      .flatMap((notification) => recipients(read, account, name, notification));
  return {
    name,
    guardrailShape:
      budget.BudgetType === "COST" &&
      budget.TimeUnit === "MONTHLY" &&
      budget.BudgetLimit?.Unit === "USD",
    limitUsd: Number(budget.BudgetLimit?.Amount),
    actual: alerted("ACTUAL"),
    forecast: alerted("FORECASTED"),
  };
}

/** Every budget in *account*, and the names of those the access stack owns. */
export function readBudgets(
  read: Sources,
  account: string,
): { budgets: BudgetFacts[]; owned: Set<string> } {
  const { Budgets: budgets = [] } = read.aws([
    "budgets",
    "describe-budgets",
    "--account-id",
    account,
  ]) as {
    Budgets?: readonly BudgetJson[];
  };
  const resources = read.aws(
    ["cloudformation", "describe-stack-resources", "--stack-name", ACCESS_STACK_NAME],
    /does not exist/,
  ) as
    | { StackResources?: readonly { ResourceType?: string; PhysicalResourceId?: string }[] }
    | undefined;
  const owned = (resources?.StackResources ?? [])
    .filter((resource) => resource.ResourceType === "AWS::Budgets::Budget")
    .map((resource) => String(resource.PhysicalResourceId));
  return { budgets: budgets.map((budget) => facts(read, account, budget)), owned: new Set(owned) };
}

const alerting = (budget: BudgetFacts): boolean =>
  budget.actual.length > 0 && budget.forecast.length > 0;

const names = (budgets: readonly BudgetFacts[]): string =>
  budgets.map((budget) => budget.name).join(", ");

function finding(state: Finding["state"], detail: string): Finding {
  return { check: CHECK.budget, state, detail };
}

function recipientsToConfirm(guardrails: readonly BudgetFacts[]): Finding[] {
  return guardrails.map((budget) => ({
    check: CHECK.recipients,
    state: "confirm",
    detail: `confirm ${[...new Set([...budget.actual, ...budget.forecast])].join(", ")} completed AWS's recipient verification for ${budget.name}`,
  }));
}

function manualOwnership(budgets: readonly BudgetFacts[], owned: ReadonlySet<string>): Finding[] {
  const stackOwned = budgets.filter((budget) => owned.has(budget.name));
  if (stackOwned.length > 0) {
    return [
      finding(
        "drift",
        `${ACCESS_STACK_NAME} owns ${names(stackOwned)} although the configured guardrail is manual`,
      ),
    ];
  }
  const guardrails = budgets.filter((budget) => budget.guardrailShape);
  const [guardrail, ...others] = guardrails;
  if (guardrail === undefined) {
    return [
      finding(
        "drift",
        "no monthly cost budget guards the account; the manual guardrail must stay active",
      ),
    ];
  }
  if (others.length > 0) {
    return [
      finding(
        "drift",
        `several monthly cost budgets (${names(guardrails)}); one guardrail must be unambiguous`,
      ),
    ];
  }
  if (!alerting(guardrail)) {
    return [finding("drift", `${guardrail.name} lacks an actual or a forecast email alert`)];
  }
  return [
    finding(
      "verified",
      `manual guardrail ${guardrail.name}: $${String(guardrail.limitUsd)} monthly, actual and forecast alerts`,
    ),
    ...recipientsToConfirm([guardrail]),
  ];
}

function matchesConfiguration(budget: BudgetFacts, configured: StackBudget): boolean {
  const recipients = JSON.stringify([...configured.recipients].sort());
  return (
    budget.guardrailShape &&
    budget.limitUsd === configured.limitUsd &&
    JSON.stringify([...budget.actual].sort()) === recipients &&
    JSON.stringify([...budget.forecast].sort()) === recipients
  );
}

/**
 * The approved transition from the manual guardrail to a stack-owned budget:
 * the access stack creates the new budget beside the manual one, so spending
 * stays guarded throughout, and a human retires the manual budget only after
 * the new one's recipients are active. CloudFormation cannot adopt an existing
 * budget, so one of the configured name outside the stack is drift, never
 * something to import or delete.
 */
function stackOwnership(
  budgets: readonly BudgetFacts[],
  owned: ReadonlySet<string>,
  configured: StackBudget,
): Finding[] {
  const named = budgets.find((budget) => budget.name === configured.name);
  const manual = budgets.filter(
    (budget) => budget.guardrailShape && !owned.has(budget.name) && budget !== named,
  );
  if (named !== undefined && !owned.has(named.name)) {
    return [
      finding(
        "drift",
        `a budget named ${named.name} exists outside ${ACCESS_STACK_NAME}; it is never imported`,
      ),
    ];
  }
  if (named === undefined) {
    const meanwhile =
      manual.length > 0
        ? `${names(manual)} stay active until it is verified`
        : "no budget guards the account meanwhile";
    return [
      finding("pending", `apply access-stack to create ${configured.name}; ${meanwhile}`),
      ...recipientsToConfirm(manual),
    ];
  }
  if (!matchesConfiguration(named, configured)) {
    return [
      finding("drift", `${named.name} no longer matches its configured limit and recipients`),
    ];
  }
  const confirm = recipientsToConfirm([named]);
  if (manual.length > 0) {
    return [
      finding(
        "pending",
        `once ${named.name}'s recipients are active, a maintainer retires ${names(manual)}; that deletion is separately authorized`,
      ),
      ...confirm,
    ];
  }
  return [finding("verified", `${ACCESS_STACK_NAME} owns ${named.name}`), ...confirm];
}

/** Whether the spending guardrail is in force, as the configured ownership requires. */
export function budgetFindings(
  configured: ManualBudget | StackBudget,
  budgets: readonly BudgetFacts[],
  owned: ReadonlySet<string>,
): Finding[] {
  return configured.ownership === "manual"
    ? manualOwnership(budgets, owned)
    : stackOwnership(budgets, owned, configured);
}
