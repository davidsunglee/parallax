import type { GetSecretValueCommand } from "@aws-sdk/client-secrets-manager";
import { describe, expect, it } from "vitest";
import {
  DEADLINE_MARGIN_MS,
  handler,
  platformDependencies,
  roleBootstrapHandler,
  type ConnectionOptions,
  type Login,
  type RoleBootstrapEvent,
  type RoleBootstrapProperties,
  type Session,
  type SqlClient,
} from "../src/role-bootstrap-handler/index.mts";
import { CONVERGED_ROLE_FACTS } from "../src/role-bootstrap.ts";

const PROPERTIES: RoleBootstrapProperties = {
  Id: "parallax-ci-role-bootstrap",
  Host: "parallax-ci.cluster-abc.us-east-2.rds.amazonaws.com",
  Port: "5432",
  User: "parallax_admin",
  Database: "parallax_ci_control",
  SecretArn: "arn:aws:secretsmanager:us-east-2:111122223333:secret:master",
  Sql: "DO $bootstrap$ BEGIN END $bootstrap$",
  FactsSql: "SELECT facts",
  ExpectedFacts: JSON.stringify(CONVERGED_ROLE_FACTS),
  Revision: "0123456789abcdef0123456789abcdef01234567",
};

const TOKEN = "signed-token";
const PASSWORD = "master-password";

const event = (
  RequestType: RoleBootstrapEvent["RequestType"],
  PhysicalResourceId?: string,
): RoleBootstrapEvent => ({
  RequestType,
  ResourceProperties: PROPERTIES,
  ...(PhysicalResourceId === undefined ? {} : { PhysicalResourceId }),
});

/** An error carrying *code*, as postgres.js reports a server refusal or a socket failure. */
function failure(code: string, message = `${code} raised`): Error {
  return Object.assign(new Error(message), { code });
}

type Rows = readonly (readonly unknown[])[];
const facts = (value: unknown): Rows => [[JSON.stringify(value)]];
const done: Rows = [];

/**
 * A scripted cluster and clock: each sign-in answers with the next outcome (a
 * session or an error), each statement on a session with the next rows, and
 * each wait advances the clock.
 */
function world(
  signIns: readonly (Error | "session")[],
  replies: readonly Rows[],
  remaining = 300_000,
) {
  const outcomes = [...signIns];
  const answers = [...replies];
  const logins: Login[] = [];
  const statements: string[] = [];
  const waits: number[] = [];
  const ended: number[] = [];
  let clock = 0;
  const session: Session = {
    query: (sql) => {
      statements.push(sql);
      const rows = answers.shift();
      return rows === undefined
        ? Promise.reject(new Error("unscripted statement"))
        : Promise.resolve(rows);
    },
    end: () => {
      ended.push(clock);
      return Promise.resolve();
    },
  };
  const run = roleBootstrapHandler({
    connect: (login) => {
      logins.push(login);
      const outcome = outcomes.shift();
      if (outcome === undefined) return Promise.reject(new Error("unscripted sign-in"));
      return outcome === "session" ? Promise.resolve(session) : Promise.reject(outcome);
    },
    token: (host, port, user) => `${TOKEN}:${host}:${String(port)}:${user}`,
    password: (secretArn) =>
      secretArn === PROPERTIES.SecretArn
        ? Promise.resolve(PASSWORD)
        : Promise.reject(new Error("wrong secret")),
    sleep: (milliseconds) => {
      waits.push(milliseconds);
      clock += milliseconds;
      return Promise.resolve();
    },
    now: () => clock,
  });
  const invoke = (request: RoleBootstrapEvent) =>
    run(request, { getRemainingTimeInMillis: () => remaining });
  return { invoke, logins, statements, waits, ended };
}

const login = (password: string): Login => ({
  host: PROPERTIES.Host,
  port: 5432,
  database: PROPERTIES.Database,
  user: PROPERTIES.User,
  password,
});
const BY_TOKEN = login(`${TOKEN}:${PROPERTIES.Host}:5432:${PROPERTIES.User}`);
const BY_PASSWORD = login(PASSWORD);

describe("the role-bootstrap handler", () => {
  it("signs in with an IAM token, runs the statement, and reads the converged facts back", async () => {
    for (const request of [event("Create"), event("Update", PROPERTIES.Id)]) {
      const { invoke, logins, statements, waits, ended } = world(
        ["session"],
        [done, facts(CONVERGED_ROLE_FACTS)],
      );
      await expect(invoke(request)).resolves.toEqual({
        PhysicalResourceId: PROPERTIES.Id,
        Data: { Facts: JSON.stringify(CONVERGED_ROLE_FACTS), Revision: PROPERTIES.Revision },
      });
      expect(logins).toEqual([BY_TOKEN]);
      expect(statements).toEqual([PROPERTIES.Sql, PROPERTIES.FactsSql]);
      expect(waits).toEqual([]);
      expect(ended).toHaveLength(1);
    }
  });

  it("falls back to the master password only when the token is refused, as on the first run", async () => {
    for (const refusal of ["28P01", "28000"]) {
      const { invoke, logins } = world(
        [failure(refusal), "session"],
        [done, facts(CONVERGED_ROLE_FACTS)],
      );
      await expect(invoke(event("Create"))).resolves.toMatchObject({
        PhysicalResourceId: PROPERTIES.Id,
      });
      expect(logins).toEqual([BY_TOKEN, BY_PASSWORD]);
    }
  });

  it("fails, naming both refusals, when the master user refuses the token and the password", async () => {
    const byToken = failure("28000", "PAM authentication failed");
    const byPassword = failure("28P01", "password authentication failed");
    const { invoke } = world([byToken, byPassword], []);
    const refused = invoke(event("Create"));
    await expect(refused).rejects.toThrow(
      "the master user refused both its IAM token and its password",
    );
    await expect(refused).rejects.toMatchObject({ errors: [byToken, byPassword] });
  });

  it("fails at once on a sign-in failure that is neither a refusal nor an unreachable cluster", async () => {
    const { invoke, logins, waits } = world([failure("3D000", "database does not exist")], []);
    await expect(invoke(event("Create"))).rejects.toThrow("database does not exist");
    expect(logins).toEqual([BY_TOKEN]);
    expect(waits).toEqual([]);
    const { invoke: second } = world(
      [failure("28P01"), failure("53300", "too many connections")],
      [],
    );
    await expect(second(event("Create"))).rejects.toThrow("too many connections");
  });

  it("waits out an unreachable or resuming cluster with growing delays, then converges", async () => {
    const { invoke, logins, waits } = world(
      [
        failure("ECONNREFUSED"),
        failure("CONNECT_TIMEOUT"),
        failure("57P03"),
        failure("ETIMEDOUT"),
        failure("ECONNRESET"),
        failure("EHOSTUNREACH"),
        "session",
      ],
      [done, facts(CONVERGED_ROLE_FACTS)],
    );
    await expect(invoke(event("Create"))).resolves.toMatchObject({
      PhysicalResourceId: PROPERTIES.Id,
    });
    expect(waits).toEqual([2_000, 4_000, 8_000, 16_000, 20_000, 20_000]);
    expect(logins).toEqual(Array<Login>(7).fill(BY_TOKEN));
  });

  it("waits out an unreachable cluster after the token is refused, too", async () => {
    const { invoke, logins } = world(
      [failure("28P01"), failure("ECONNRESET"), "session"],
      [done, facts(CONVERGED_ROLE_FACTS)],
    );
    await expect(invoke(event("Create"))).resolves.toMatchObject({
      PhysicalResourceId: PROPERTIES.Id,
    });
    expect(logins).toEqual([BY_TOKEN, BY_PASSWORD, BY_TOKEN]);
  });

  it("fails, rather than outlasting its invocation, when the cluster does not answer in time", async () => {
    const { invoke, waits } = world(
      Array<Error>(20).fill(failure("CONNECT_TIMEOUT")),
      [],
      DEADLINE_MARGIN_MS + 2_000 + 4_000 + 3_000,
    );
    await expect(invoke(event("Create"))).rejects.toThrow(
      "the cluster did not answer in time (CONNECT_TIMEOUT)",
    );
    expect(waits).toEqual([2_000, 4_000]);
  });

  it("fails when the facts read back are not the converged ones, ending the session either way", async () => {
    const drifted = { ...CONVERGED_ROLE_FACTS, controlOwner: "parallax_admin" };
    const { invoke, ended } = world(["session"], [done, facts(drifted)]);
    await expect(invoke(event("Create"))).rejects.toThrow(
      `the roles did not converge: ${JSON.stringify(drifted)}`,
    );
    expect(ended).toHaveLength(1);
    for (const answer of [done, [[1]]]) {
      const { invoke: empty } = world(["session"], [done, answer]);
      await expect(empty(event("Create"))).rejects.toThrow("the facts query returned no JSON text");
    }
    const { invoke: refused, ended: closed } = world(["session"], []);
    await expect(refused(event("Create"))).rejects.toThrow("unscripted statement");
    expect(closed).toHaveLength(1);
  });

  it("does nothing on delete, keeping what earlier runs converged", async () => {
    const { invoke, logins } = world([], []);
    await expect(invoke(event("Delete", "parallax-ci-role-bootstrap"))).resolves.toEqual({
      PhysicalResourceId: "parallax-ci-role-bootstrap",
    });
    await expect(invoke(event("Delete"))).resolves.toEqual({ PhysicalResourceId: PROPERTIES.Id });
    expect(logins).toEqual([]);
  });

  it("is exported for the runtime", async () => {
    await expect(
      handler(event("Delete", PROPERTIES.Id), { getRemainingTimeInMillis: () => 0 }),
    ).resolves.toEqual({ PhysicalResourceId: PROPERTIES.Id });
  });
});

const ENVIRONMENT = {
  AWS_REGION: "us-east-2",
  AWS_ACCESS_KEY_ID: "AKIDEXAMPLE",
  AWS_SECRET_ACCESS_KEY: "secret",
  AWS_SESSION_TOKEN: "session",
};

/** A postgres.js stand-in recording what it is opened with, run, and ended with. */
function client(probe?: Error) {
  const opened: ConnectionOptions[] = [];
  const run: string[] = [];
  const ends: number[] = [];
  const postgres = (options: ConnectionOptions): SqlClient => {
    opened.push(options);
    return {
      unsafe: (sql) => ({
        values: () => {
          run.push(sql);
          return sql === "select 1" && probe !== undefined
            ? Promise.reject(probe)
            : Promise.resolve([["value"]]);
        },
      }),
      end: ({ timeout }) => {
        ends.push(timeout);
        return Promise.resolve();
      },
    };
  };
  return { postgres, opened, run, ends };
}

const secrets = (SecretString: string | undefined) => {
  const asked: string[] = [];
  return {
    asked,
    send: (command: GetSecretValueCommand) => {
      asked.push(String(command.input.SecretId));
      return Promise.resolve(SecretString === undefined ? {} : { SecretString });
    },
  };
};

describe("the handler's runtime dependencies", () => {
  it("open one verified TLS session, signed in before it is handed over", async () => {
    const pg = client();
    const { connect } = platformDependencies({
      environment: ENVIRONMENT,
      postgres: pg.postgres,
      secrets: secrets("{}"),
    });
    const session = await connect(BY_PASSWORD);
    expect(pg.opened).toEqual([
      {
        host: PROPERTIES.Host,
        port: 5432,
        database: PROPERTIES.Database,
        username: PROPERTIES.User,
        password: PASSWORD,
        ssl: "verify-full",
        max: 1,
        connect_timeout: 10,
        prepare: false,
      },
    ]);
    await expect(session.query("select facts")).resolves.toEqual([["value"]]);
    await session.end();
    expect(pg.run).toEqual(["select 1", "select facts"]);
    expect(pg.ends).toEqual([5]);
  });

  it("close a session whose sign-in failed and report the failure", async () => {
    const refused = failure("28P01");
    const pg = client(refused);
    const { connect } = platformDependencies({
      environment: ENVIRONMENT,
      postgres: pg.postgres,
      secrets: secrets("{}"),
    });
    await expect(connect(BY_TOKEN)).rejects.toBe(refused);
    expect(pg.ends).toEqual([0]);
  });

  it("sign a token for the host with the function's own credentials", () => {
    const signed = (environment: Record<string, string>) =>
      platformDependencies({
        environment,
        postgres: client().postgres,
        secrets: secrets("{}"),
      }).token(PROPERTIES.Host, 5432, PROPERTIES.User);
    const token = signed(ENVIRONMENT);
    expect(token).toMatch(
      new RegExp(
        `^${PROPERTIES.Host}:5432/\\?Action=connect&DBUser=parallax_admin&X-Amz-Algorithm=`,
      ),
    );
    expect(token).toContain("X-Amz-Credential=AKIDEXAMPLE%2F");
    expect(token).toContain("X-Amz-Security-Token=session");
    const without = (name: string): Record<string, string> =>
      Object.fromEntries(Object.entries(ENVIRONMENT).filter(([key]) => key !== name));
    expect(signed(without("AWS_SESSION_TOKEN"))).not.toContain("X-Amz-Security-Token");
    for (const name of ["AWS_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]) {
      expect(() => signed(without(name))).toThrow(`the runtime supplies no ${name}`);
    }
  });

  it("read the master password from its secret, refusing a secret without one", async () => {
    const store = secrets(JSON.stringify({ username: "parallax_admin", password: PASSWORD }));
    const dependencies = platformDependencies({
      environment: ENVIRONMENT,
      postgres: client().postgres,
      secrets: store,
    });
    await expect(dependencies.password(PROPERTIES.SecretArn)).resolves.toBe(PASSWORD);
    expect(store.asked).toEqual([PROPERTIES.SecretArn]);
    for (const value of [undefined, "{}", JSON.stringify({ password: 7 })]) {
      const { password } = platformDependencies({
        environment: ENVIRONMENT,
        postgres: client().postgres,
        secrets: secrets(value),
      });
      await expect(password(PROPERTIES.SecretArn)).rejects.toThrow(
        "the master secret holds no password",
      );
    }
  });

  it("wait and tell time with the platform's own clock", async () => {
    const { sleep, now } = platformDependencies({
      environment: ENVIRONMENT,
      postgres: client().postgres,
      secrets: secrets("{}"),
    });
    const before = now();
    await sleep(1);
    expect(now()).toBeGreaterThanOrEqual(before);
  });
});
