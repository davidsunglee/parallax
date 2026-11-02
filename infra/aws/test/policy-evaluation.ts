/**
 * A small model of IAM's identity-policy evaluation, enough to state negative
 * permissions: an explicit deny wins, otherwise some allow must match, and
 * every condition of a matching statement must hold. Actions and resources
 * match IAM's wildcards; a resource written as a CloudFormation intrinsic
 * matches nothing; conditions compare against the request *context*, where an
 * absent key fails a positive operator and satisfies a negated one.
 */

export type RequestContext = Readonly<Record<string, string>>;

interface Statement {
  readonly Effect?: unknown;
  readonly Action?: unknown;
  readonly NotAction?: unknown;
  readonly Resource?: unknown;
  readonly NotResource?: unknown;
  readonly Condition?: unknown;
}

const list = (value: unknown): unknown[] =>
  Array.isArray(value) ? (value as unknown[]) : value === undefined ? [] : [value];

function glob(pattern: string, value: string, caseless: boolean): boolean {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`, caseless ? "i" : "").test(value);
}

const anyMatch = (patterns: unknown, value: string, caseless: boolean): boolean =>
  list(patterns).some((pattern) => typeof pattern === "string" && glob(pattern, value, caseless));

function matches(statement: Statement, action: string, resource: string): boolean {
  const actionMatches =
    statement.NotAction === undefined
      ? anyMatch(statement.Action, action, true)
      : !anyMatch(statement.NotAction, action, true);
  const resourceMatches =
    statement.NotResource === undefined
      ? anyMatch(statement.Resource, resource, false)
      : !anyMatch(statement.NotResource, resource, false);
  return actionMatches && resourceMatches;
}

const OPERATORS: Readonly<
  Record<string, (expected: unknown[], actual: string | undefined) => boolean>
> = {
  StringEquals: (expected, actual) => expected.includes(actual),
  StringNotEquals: (expected, actual) => !expected.includes(actual),
  StringLike: (expected, actual) => actual !== undefined && anyMatch(expected, actual, false),
  ArnLike: (expected, actual) => actual !== undefined && anyMatch(expected, actual, false),
  Null: (expected, actual) => expected.includes(String(actual === undefined)),
};

function conditionsHold(condition: unknown, context: RequestContext): boolean {
  return Object.entries((condition ?? {}) as Record<string, Record<string, unknown>>).every(
    ([operator, keys]) => {
      const evaluate = OPERATORS[operator];
      if (evaluate === undefined) throw new Error(`the model has no ${operator} operator`);
      return Object.entries(keys).every(([key, expected]) =>
        evaluate(list(expected), context[key]),
      );
    },
  );
}

function applies(
  statement: Statement,
  action: string,
  resource: string,
  context: RequestContext,
): boolean {
  return matches(statement, action, resource) && conditionsHold(statement.Condition, context);
}

/** Whether *statements* allow *action* on *resource* in *context*. */
export function allowed(
  statements: readonly unknown[],
  action: string,
  resource: string,
  context: RequestContext = {},
): boolean {
  const applicable = (statements as Statement[]).filter((statement) =>
    applies(statement, action, resource, context),
  );
  return (
    applicable.some((statement) => statement.Effect === "Allow") &&
    !applicable.some((statement) => statement.Effect === "Deny")
  );
}

/** Whether a role holding *identity* under the permissions boundary *boundary* may do it: both must allow. */
export function allowedWithin(
  identity: readonly unknown[],
  boundary: readonly unknown[],
  action: string,
  resource: string,
  context: RequestContext = {},
): boolean {
  return (
    allowed(identity, action, resource, context) && allowed(boundary, action, resource, context)
  );
}
