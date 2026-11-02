import { setTimeout as sleep } from "node:timers/promises";
import { isDeepStrictEqual } from "node:util";
import {
  ExecuteStatementCommand,
  RDSDataClient,
  type ExecuteStatementCommandInput,
  type ExecuteStatementCommandOutput,
} from "@aws-sdk/client-rds-data";

/** What the custom resource hands the handler, as CloudFormation passes it: every value a string. */
export interface RoleBootstrapProperties {
  /** The physical ID every run reports, so an update never replaces the resource. */
  readonly Id: string;
  readonly ResourceArn: string;
  readonly SecretArn: string;
  readonly Database: string;
  readonly Sql: string;
  /** A query returning the converged facts as one JSON text value. */
  readonly FactsSql: string;
  readonly ExpectedFacts: string;
  /** The deployed revision; a new one makes every deployment run the statement again. */
  readonly Revision: string;
}

/** The custom-resource event the provider framework invokes the handler with. */
export interface RoleBootstrapEvent {
  readonly RequestType: "Create" | "Update" | "Delete";
  readonly PhysicalResourceId?: string;
  readonly ResourceProperties: RoleBootstrapProperties;
}

export interface RoleBootstrapResponse {
  readonly PhysicalResourceId: string;
  /** The facts read back after the statement, as JSON text, and the revision that ran it. */
  readonly Data?: { readonly Facts: string; readonly Revision: string };
}

/** The part of the Lambda context the handler reads. */
export interface Invocation {
  getRemainingTimeInMillis(): number;
}

/** The part of the RDS Data API client the handler uses. */
export interface DataApi {
  send(command: ExecuteStatementCommand): Promise<ExecuteStatementCommandOutput>;
}

export interface Dependencies {
  readonly client: DataApi;
  readonly sleep: (milliseconds: number) => Promise<unknown>;
  readonly now: () => number;
}

/** Time kept back from the invocation's own timeout, so a failure is reported rather than cut off. */
export const DEADLINE_MARGIN_MS = 15_000;
const FIRST_DELAY_MS = 2_000;
const LONGEST_DELAY_MS = 20_000;

/** The one error a paused Serverless v2 cluster answers with while the request resumes it. */
const RESUMING = "DatabaseResumingException";

const resuming = (error: unknown): error is Error =>
  error instanceof Error && error.name === RESUMING;

/**
 * Run the statement *input*, waiting out a paused cluster's resumption with doubling
 * delays until *deadline*; any other failure ends the run at once.
 */
async function executed(
  dependencies: Dependencies,
  input: ExecuteStatementCommandInput,
  deadline: number,
): Promise<ExecuteStatementCommandOutput> {
  for (let delay = FIRST_DELAY_MS; ; delay = Math.min(delay * 2, LONGEST_DELAY_MS)) {
    try {
      return await dependencies.client.send(new ExecuteStatementCommand(input));
    } catch (error) {
      if (!resuming(error)) throw error;
      if (dependencies.now() + delay > deadline) {
        throw new Error(`the cluster did not resume in time: ${error.message}`, { cause: error });
      }
      await dependencies.sleep(delay);
    }
  }
}

async function converge(
  dependencies: Dependencies,
  properties: RoleBootstrapProperties,
  deadline: number,
): Promise<string> {
  const target = {
    resourceArn: properties.ResourceArn,
    secretArn: properties.SecretArn,
    database: properties.Database,
  };
  await executed(dependencies, { ...target, sql: properties.Sql }, deadline);
  const { records } = await executed(
    dependencies,
    { ...target, sql: properties.FactsSql },
    deadline,
  );
  const text = records?.[0]?.[0]?.stringValue;
  if (text === undefined) throw new Error("the facts query returned no JSON text");
  const facts: unknown = JSON.parse(text);
  if (!isDeepStrictEqual(facts, JSON.parse(properties.ExpectedFacts))) {
    throw new Error(`the roles did not converge: ${text}`);
  }
  return JSON.stringify(facts);
}

/**
 * The role-bootstrap handler: on create and on update it runs the bootstrap
 * statement, reads the converged facts back, and fails unless they are the
 * expected ones; on delete it does nothing, so removing the resource never
 * undoes what earlier runs converged.
 */
export function roleBootstrapHandler(
  dependencies: Dependencies,
): (event: RoleBootstrapEvent, invocation: Invocation) => Promise<RoleBootstrapResponse> {
  return async (event, invocation) => {
    const properties = event.ResourceProperties;
    if (event.RequestType === "Delete") {
      return { PhysicalResourceId: event.PhysicalResourceId ?? properties.Id };
    }
    const deadline =
      dependencies.now() + invocation.getRemainingTimeInMillis() - DEADLINE_MARGIN_MS;
    const facts = await converge(dependencies, properties, deadline);
    return {
      PhysicalResourceId: properties.Id,
      Data: { Facts: facts, Revision: properties.Revision },
    };
  };
}

export const handler = roleBootstrapHandler({
  client: new RDSDataClient({}),
  sleep,
  now: Date.now,
});
