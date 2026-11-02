import { createHash, createHmac } from "node:crypto";

/** The AWS credentials a token is signed with, as a Lambda function's environment supplies them. */
export interface Credentials {
  readonly accessKeyId: string;
  readonly secretAccessKey: string;
  readonly sessionToken?: string;
}

export interface TokenRequest {
  readonly host: string;
  readonly port: number;
  readonly user: string;
  readonly region: string;
  readonly credentials: Credentials;
  readonly now: Date;
}

const SERVICE = "rds-db";
const ALGORITHM = "AWS4-HMAC-SHA256";
/** The longest an RDS IAM authentication token is accepted for. */
const EXPIRES_SECONDS = 900;

/** RFC 3986 encoding, which SigV4 requires and `encodeURIComponent` leaves partly undone. */
const encoded = (value: string): string =>
  encodeURIComponent(value).replace(
    /[!'()*]/g,
    (character) => `%${character.charCodeAt(0).toString(16).toUpperCase()}`,
  );

const sha256 = (value: string): string => createHash("sha256").update(value).digest("hex");
const hmac = (key: Buffer | string, value: string): Buffer =>
  createHmac("sha256", key).update(value).digest();

/**
 * An RDS IAM authentication token for *user* on *host*: a SigV4-presigned
 * `connect` request, written as the URL without its scheme, which the database
 * accepts as the password for the next 15 minutes.
 */
export function iamToken(request: TokenRequest): string {
  const { host, port, user, region, credentials } = request;
  const stamp = request.now.toISOString().replace(/[-:]|\.\d{3}/g, "");
  const day = stamp.slice(0, 8);
  const scope = `${day}/${region}/${SERVICE}/aws4_request`;
  const parameters: [string, string][] = [
    ["Action", "connect"],
    ["DBUser", user],
    ["X-Amz-Algorithm", ALGORITHM],
    ["X-Amz-Credential", `${credentials.accessKeyId}/${scope}`],
    ["X-Amz-Date", stamp],
    ["X-Amz-Expires", String(EXPIRES_SECONDS)],
    ["X-Amz-SignedHeaders", "host"],
  ];
  if (credentials.sessionToken !== undefined) {
    parameters.push(["X-Amz-Security-Token", credentials.sessionToken]);
  }
  const query = parameters
    .map(([name, value]) => [encoded(name), encoded(value)] as const)
    .sort(([left], [right]) => (left < right ? -1 : 1))
    .map(([name, value]) => `${name}=${value}`)
    .join("&");
  const authority = `${host}:${String(port)}`;
  const canonicalRequest = ["GET", "/", query, `host:${authority}\n`, "host", sha256("")].join(
    "\n",
  );
  const stringToSign = [ALGORITHM, stamp, scope, sha256(canonicalRequest)].join("\n");
  const key = ["aws4_request", SERVICE, region, day].reduceRight<Buffer | string>(
    (signingKey, part) => hmac(signingKey, part),
    `AWS4${credentials.secretAccessKey}`,
  );
  const signature = hmac(key, stringToSign).toString("hex");
  return `${authority}/?${query}&X-Amz-Signature=${signature}`;
}
