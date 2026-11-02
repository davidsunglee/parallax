import { describe, expect, it } from "vitest";
import { iamToken, type TokenRequest } from "../src/role-bootstrap-handler/iam-token.mts";

const HOST = "parallax-ci.cluster-abc123.us-east-2.rds.amazonaws.com";
const REQUEST: TokenRequest = {
  host: HOST,
  port: 5432,
  user: "parallax_admin",
  region: "us-east-2",
  credentials: {
    accessKeyId: "AKIDEXAMPLE",
    secretAccessKey: "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
  },
  now: new Date("2026-11-02T21:30:00Z"),
};

// Signatures computed for the same requests by @smithy/signature-v4, the signer
// @aws-sdk/rds-signer presigns with.
const SIGNATURE = "b5a25562fe4fd77fb73cfa732be63278c2e018dc14fae5acb87d36dfccbda5e3";
const SIGNATURE_WITH_SESSION = "85ed49d8db5e5ad5460d8560692c95c6727aeaf5a50e6f04dbe7dd41ebca7b04";

describe("an RDS IAM authentication token", () => {
  it("is AWS's presigned connect request for the user, without its scheme", () => {
    expect(iamToken(REQUEST)).toBe(
      `${HOST}:5432/?Action=connect&DBUser=parallax_admin&X-Amz-Algorithm=AWS4-HMAC-SHA256` +
        "&X-Amz-Credential=AKIDEXAMPLE%2F20261102%2Fus-east-2%2Frds-db%2Faws4_request" +
        "&X-Amz-Date=20261102T213000Z&X-Amz-Expires=900&X-Amz-SignedHeaders=host" +
        `&X-Amz-Signature=${SIGNATURE}`,
    );
  });

  it("signs a session token, encoded as SigV4 requires", () => {
    const token = iamToken({
      ...REQUEST,
      credentials: { ...REQUEST.credentials, sessionToken: "FQoGZXIvYXdzEXAMPLE/+token=" },
    });
    expect(token).toContain("&X-Amz-Security-Token=FQoGZXIvYXdzEXAMPLE%2F%2Btoken%3D&");
    expect(token.endsWith(`&X-Amz-Signature=${SIGNATURE_WITH_SESSION}`)).toBe(true);
  });

  it("encodes the characters encodeURIComponent leaves alone", () => {
    expect(iamToken({ ...REQUEST, user: "o'brien(x)*!" })).toContain(
      "DBUser=o%27brien%28x%29%2A%21&",
    );
  });
});
