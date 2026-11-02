import { setTimeout as sleep } from "node:timers/promises";
import { isDeepStrictEqual } from "node:util";
import { GetSecretValueCommand, SecretsManagerClient } from "@aws-sdk/client-secrets-manager";
import postgres from "postgres";
import { iamToken } from "./iam-token.mts";

/** What the custom resource hands the handler, as CloudFormation passes it: every value a string. */
export interface RoleBootstrapProperties {
  /** The physical ID every run reports, so an update never replaces the resource. */
  readonly Id: string;
  /** The cluster's writer endpoint, which the handler reaches from inside the VPC. */
  readonly Host: string;
  readonly Port: string;
  /** The master user, which runs the statement. */
  readonly User: string;
  readonly Database: string;
  /** The master user's secret, whose password only the first run can still use. */
  readonly SecretArn: string;
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

/** Where and as whom one session signs in. */
export interface Login {
  readonly host: string;
  readonly port: number;
  readonly database: string;
  readonly user: string;
  readonly password: string;
}

/** One signed-in database session. */
export interface Session {
  /** Every row *sql* returns, each as its column values. */
  query(sql: string): Promise<readonly (readonly unknown[])[]>;
  end(): Promise<void>;
}

export interface Dependencies {
  /** A session signed in as *login*, or the database's refusal of it. */
  readonly connect: (login: Login) => Promise<Session>;
  readonly token: (host: string, port: number, user: string) => string;
  readonly password: (secretArn: string) => Promise<string>;
  readonly sleep: (milliseconds: number) => Promise<unknown>;
  readonly now: () => number;
}

/** Time kept back from the invocation's own timeout, so a failure is reported rather than cut off. */
export const DEADLINE_MARGIN_MS = 15_000;
const FIRST_DELAY_MS = 2_000;
const LONGEST_DELAY_MS = 20_000;

/** The database's refusals of a login's credentials: a wrong password, and an IAM-only login offered one. */
const REFUSED = new Set(["28P01", "28000"]);

/**
 * What a cluster answers while it cannot take a session yet: refusing or timing
 * out the connection, or starting up as a paused Serverless v2 cluster resumes.
 */
const UNREACHABLE = new Set([
  "57P03",
  "CONNECT_TIMEOUT",
  "ECONNREFUSED",
  "ECONNRESET",
  "EHOSTUNREACH",
  "ETIMEDOUT",
]);

const codeOf = (error: unknown): string | undefined =>
  typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code
    : undefined;

const isIn = (codes: ReadonlySet<string>, error: unknown): boolean =>
  codes.has(codeOf(error) ?? "");

/**
 * Sign in as the master user: by IAM token, the only way left once the first
 * run has made it a member of `rds_iam` through the login it grants itself, and
 * by its password otherwise, which only that first run can still use.
 */
async function signedIn(
  dependencies: Dependencies,
  properties: RoleBootstrapProperties,
): Promise<Session> {
  const login = {
    host: properties.Host,
    port: Number(properties.Port),
    database: properties.Database,
    user: properties.User,
  };
  try {
    return await dependencies.connect({
      ...login,
      password: dependencies.token(login.host, login.port, login.user),
    });
  } catch (byToken) {
    if (!isIn(REFUSED, byToken)) throw byToken;
    try {
      return await dependencies.connect({
        ...login,
        password: await dependencies.password(properties.SecretArn),
      });
    } catch (byPassword) {
      if (!isIn(REFUSED, byPassword)) throw byPassword;
      throw new AggregateError(
        [byToken, byPassword],
        "the master user refused both its IAM token and its password",
        { cause: byPassword },
      );
    }
  }
}

/**
 * Sign in, waiting out an unreachable or resuming cluster with doubling delays
 * until *deadline*; any other failure ends the run at once.
 */
async function reached(
  dependencies: Dependencies,
  properties: RoleBootstrapProperties,
  deadline: number,
): Promise<Session> {
  for (let delay = FIRST_DELAY_MS; ; delay = Math.min(delay * 2, LONGEST_DELAY_MS)) {
    try {
      return await signedIn(dependencies, properties);
    } catch (error) {
      if (!isIn(UNREACHABLE, error)) throw error;
      if (dependencies.now() + delay > deadline) {
        throw new Error(`the cluster did not answer in time (${String(codeOf(error))})`, {
          cause: error,
        });
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
  const session = await reached(dependencies, properties, deadline);
  try {
    await session.query(properties.Sql);
    const text = (await session.query(properties.FactsSql))[0]?.[0];
    if (typeof text !== "string") throw new Error("the facts query returned no JSON text");
    const facts: unknown = JSON.parse(text);
    if (!isDeepStrictEqual(facts, JSON.parse(properties.ExpectedFacts))) {
      throw new Error(`the roles did not converge: ${text}`);
    }
    return JSON.stringify(facts);
  } finally {
    await session.end();
  }
}

/**
 * The role-bootstrap handler: on create and on update it runs the bootstrap
 * statement as the master user, reads the converged facts back, and fails
 * unless they are the expected ones; on delete it does nothing, so removing the
 * resource never undoes what earlier runs converged.
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

/** The connection options the handler opens its one session with. */
export interface ConnectionOptions {
  readonly host: string;
  readonly port: number;
  readonly database: string;
  readonly username: string;
  readonly password: string;
  /** Certificate and hostname verification, against the runtime's Amazon CA bundle. */
  readonly ssl: "verify-full";
  readonly max: 1;
  readonly connect_timeout: number;
  readonly prepare: false;
}

/** The part of a postgres.js client the handler uses. */
export interface SqlClient {
  unsafe(sql: string): { values(): PromiseLike<readonly (readonly unknown[])[]> };
  end(options: { timeout: number }): Promise<void>;
}

/** What the Lambda runtime supplies the handler. */
export interface Platform {
  readonly environment: Readonly<Record<string, string | undefined>>;
  readonly postgres: (options: ConnectionOptions) => SqlClient;
  readonly secrets: { send(command: GetSecretValueCommand): Promise<{ SecretString?: string }> };
}

const CONNECT_TIMEOUT_SECONDS = 10;

function required(environment: Platform["environment"], name: string): string {
  const value = environment[name];
  if (value === undefined) throw new Error(`the runtime supplies no ${name}`);
  return value;
}

/** The handler's dependencies, as the Lambda runtime provides them. */
export function platformDependencies(platform: Platform): Dependencies {
  const { environment } = platform;
  return {
    connect: async (login) => {
      const sql = platform.postgres({
        host: login.host,
        port: login.port,
        database: login.database,
        username: login.user,
        password: login.password,
        ssl: "verify-full",
        max: 1,
        connect_timeout: CONNECT_TIMEOUT_SECONDS,
        prepare: false,
      });
      try {
        await sql.unsafe("select 1").values();
      } catch (error) {
        await sql.end({ timeout: 0 });
        throw error;
      }
      return {
        query: async (text) => await sql.unsafe(text).values(),
        end: () => sql.end({ timeout: 5 }),
      };
    },
    token: (host, port, user) => {
      const sessionToken = environment["AWS_SESSION_TOKEN"];
      return iamToken({
        host,
        port,
        user,
        region: required(environment, "AWS_REGION"),
        credentials: {
          accessKeyId: required(environment, "AWS_ACCESS_KEY_ID"),
          secretAccessKey: required(environment, "AWS_SECRET_ACCESS_KEY"),
          ...(sessionToken === undefined ? {} : { sessionToken }),
        },
        now: new Date(),
      });
    },
    password: async (secretArn) => {
      const { SecretString } = await platform.secrets.send(
        new GetSecretValueCommand({ SecretId: secretArn }),
      );
      const password = (JSON.parse(SecretString ?? "{}") as { password?: unknown }).password;
      if (typeof password !== "string") throw new Error("the master secret holds no password");
      return password;
    },
    sleep,
    now: Date.now,
  };
}

export const handler = roleBootstrapHandler(
  platformDependencies({
    environment: process.env,
    postgres,
    secrets: new SecretsManagerClient({}),
  }),
);
