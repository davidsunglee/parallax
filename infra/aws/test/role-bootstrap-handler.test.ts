import type {
  ExecuteStatementCommand,
  ExecuteStatementCommandInput,
  ExecuteStatementCommandOutput,
} from "@aws-sdk/client-rds-data";
import { describe, expect, it } from "vitest";
import {
  DEADLINE_MARGIN_MS,
  handler,
  roleBootstrapHandler,
  type RoleBootstrapEvent,
  type RoleBootstrapProperties,
} from "../src/role-bootstrap-handler/index.mts";
import { CONVERGED_ROLE_FACTS } from "../src/role-bootstrap.ts";

const PROPERTIES: RoleBootstrapProperties = {
  Id: "parallax-ci-role-bootstrap",
  ResourceArn: "arn:aws:rds:us-east-2:111122223333:cluster:parallax-ci",
  SecretArn: "arn:aws:secretsmanager:us-east-2:111122223333:secret:master",
  Database: "parallax_ci_control",
  Sql: "DO $bootstrap$ BEGIN END $bootstrap$",
  FactsSql: "SELECT facts",
  ExpectedFacts: JSON.stringify(CONVERGED_ROLE_FACTS),
  Revision: "0123456789abcdef0123456789abcdef01234567",
};

const event = (
  RequestType: RoleBootstrapEvent["RequestType"],
  PhysicalResourceId?: string,
): RoleBootstrapEvent => ({
  RequestType,
  ResourceProperties: PROPERTIES,
  ...(PhysicalResourceId === undefined ? {} : { PhysicalResourceId }),
});

/** An error shaped as the SDK raises a modeled exception: its name is the exception's. */
function failure(name: string, message = `${name} raised`): Error {
  const error = new Error(message);
  error.name = name;
  return error;
}

const facts = (value: unknown): ExecuteStatementCommandOutput => ({
  $metadata: {},
  records: [[{ stringValue: JSON.stringify(value) }]],
});
const done: ExecuteStatementCommandOutput = { $metadata: {} };

type Reply = ExecuteStatementCommandOutput | Error;

/** A scripted Data API and clock: each statement answers with the next reply, and each wait advances the clock. */
function world(replies: readonly Reply[], remaining = 300_000) {
  const queue = [...replies];
  const statements: ExecuteStatementCommandInput[] = [];
  const waits: number[] = [];
  let clock = 0;
  const run = roleBootstrapHandler({
    client: {
      send: (command: ExecuteStatementCommand) => {
        statements.push(command.input);
        const reply = queue.shift();
        if (reply === undefined) return Promise.reject(new Error("unscripted statement"));
        return reply instanceof Error ? Promise.reject(reply) : Promise.resolve(reply);
      },
    },
    sleep: (milliseconds) => {
      waits.push(milliseconds);
      clock += milliseconds;
      return Promise.resolve();
    },
    now: () => clock,
  });
  const invoke = (request: RoleBootstrapEvent) =>
    run(request, { getRemainingTimeInMillis: () => remaining });
  return { invoke, statements, waits };
}

describe("the role-bootstrap handler", () => {
  it("runs the statement, then reads the converged facts back as the resource's data", async () => {
    for (const request of [event("Create"), event("Update", PROPERTIES.Id)]) {
      const { invoke, statements, waits } = world([done, facts(CONVERGED_ROLE_FACTS)]);
      await expect(invoke(request)).resolves.toEqual({
        PhysicalResourceId: PROPERTIES.Id,
        Data: { Facts: JSON.stringify(CONVERGED_ROLE_FACTS), Revision: PROPERTIES.Revision },
      });
      expect(statements).toEqual(
        [PROPERTIES.Sql, PROPERTIES.FactsSql].map((sql) => ({
          resourceArn: PROPERTIES.ResourceArn,
          secretArn: PROPERTIES.SecretArn,
          database: PROPERTIES.Database,
          sql,
        })),
      );
      expect(waits).toEqual([]);
    }
  });

  it("waits out a paused cluster's resumption with growing delays, then converges", async () => {
    const resuming = failure("DatabaseResumingException");
    const { invoke, statements, waits } = world([
      resuming,
      resuming,
      resuming,
      resuming,
      resuming,
      done,
      facts(CONVERGED_ROLE_FACTS),
    ]);
    await expect(invoke(event("Create"))).resolves.toMatchObject({
      PhysicalResourceId: PROPERTIES.Id,
    });
    expect(waits).toEqual([2_000, 4_000, 8_000, 16_000, 20_000]);
    expect(statements.map((statement) => statement.sql)).toEqual([
      ...Array<string>(6).fill(PROPERTIES.Sql),
      PROPERTIES.FactsSql,
    ]);
  });

  it("fails, rather than outlasting its invocation, when the cluster does not resume in time", async () => {
    const resuming = failure("DatabaseResumingException", "the database is resuming");
    const { invoke, waits } = world(
      Array<Reply>(20).fill(resuming),
      DEADLINE_MARGIN_MS + 2_000 + 4_000 + 3_000,
    );
    await expect(invoke(event("Create"))).rejects.toThrow(
      "the cluster did not resume in time: the database is resuming",
    );
    expect(waits).toEqual([2_000, 4_000]);
  });

  it("fails at once on any other error", async () => {
    const { invoke, statements, waits } = world([failure("BadRequestException", "syntax error")]);
    await expect(invoke(event("Create"))).rejects.toThrow("syntax error");
    expect(statements).toHaveLength(1);
    expect(waits).toEqual([]);
  });

  it("fails when the facts read back are not the converged ones", async () => {
    const drifted = { ...CONVERGED_ROLE_FACTS, controlOwner: "parallax_admin" };
    const { invoke } = world([done, facts(drifted)]);
    await expect(invoke(event("Create"))).rejects.toThrow(
      `the roles did not converge: ${JSON.stringify(drifted)}`,
    );
    for (const answer of [done, { $metadata: {}, records: [[{ longValue: 1 }]] }]) {
      const { invoke: empty } = world([done, answer]);
      await expect(empty(event("Create"))).rejects.toThrow("the facts query returned no JSON text");
    }
  });

  it("does nothing on delete, keeping what earlier runs converged", async () => {
    const { invoke, statements } = world([]);
    await expect(invoke(event("Delete", "parallax-ci-role-bootstrap"))).resolves.toEqual({
      PhysicalResourceId: "parallax-ci-role-bootstrap",
    });
    await expect(invoke(event("Delete"))).resolves.toEqual({ PhysicalResourceId: PROPERTIES.Id });
    expect(statements).toEqual([]);
  });

  it("is exported for the runtime, reaching the Data API through the runtime's own client", async () => {
    await expect(
      handler(event("Delete", PROPERTIES.Id), { getRemainingTimeInMillis: () => 0 }),
    ).resolves.toEqual({ PhysicalResourceId: PROPERTIES.Id });
  });
});
