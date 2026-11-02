import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CONFORMANCE_LOGIN,
  CONFORMANCE_ROLES,
  CONTROL_DATABASE,
  DEFAULT_ROLE,
  ROLE_BOOTSTRAP_SQL,
} from "../src/role-bootstrap.ts";
import { PACKAGE_ROOT } from "./committed-app.ts";

const PROVISIONER = join(
  PACKAGE_ROOT,
  "../../languages/python/packages/parallax-conformance/src/parallax/conformance/provision.py",
);

describe("the role bootstrap statement", () => {
  it("is one DO block, which the Data API runs as a single statement", () => {
    expect(ROLE_BOOTSTRAP_SQL.startsWith("DO $bootstrap$\n")).toBe(true);
    expect(ROLE_BOOTSTRAP_SQL.endsWith("\n$bootstrap$")).toBe(true);
    expect(ROLE_BOOTSTRAP_SQL.match(/\$bootstrap\$/g)).toHaveLength(2);
  });

  it("creates the database nowhere, because the cluster already did", () => {
    expect(ROLE_BOOTSTRAP_SQL).not.toMatch(/CREATE\s+DATABASE/i);
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      `ALTER DATABASE ${CONTROL_DATABASE} OWNER TO ${CONFORMANCE_LOGIN};`,
    );
  });

  it("creates each role only when it is missing, so a repeated run converges", () => {
    const creations = ROLE_BOOTSTRAP_SQL.split("\n").filter((line) => line.includes("CREATE ROLE"));
    expect(creations).toHaveLength(2);
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = member)",
    );
    expect(ROLE_BOOTSTRAP_SQL).toContain(
      `IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${CONFORMANCE_LOGIN}')`,
    );
  });

  it("converges the login's attributes, IAM membership, roles, and default role", () => {
    for (const statement of [
      `ALTER ROLE ${CONFORMANCE_LOGIN} WITH LOGIN CREATEDB;`,
      `GRANT rds_iam TO ${CONFORMANCE_LOGIN};`,
      `EXECUTE format('GRANT %I TO ${CONFORMANCE_LOGIN}', member);`,
      `ALTER ROLE ${CONFORMANCE_LOGIN} SET role TO ${DEFAULT_ROLE};`,
    ]) {
      expect(ROLE_BOOTSTRAP_SQL).toContain(statement);
    }
    for (const role of CONFORMANCE_ROLES) expect(ROLE_BOOTSTRAP_SQL).toContain(`'${role}'`);
  });

  it("names exactly the roles the conformance provisioner grants", () => {
    const provisioner = readFileSync(PROVISIONER, "utf8");
    expect(provisioner).toContain(`CONFORMANCE_LOGIN: Final[str] = "${CONFORMANCE_LOGIN}"`);
    expect(provisioner).toContain(`_DEFAULT_ROLE = "${DEFAULT_ROLE}"`);
    const granted = [...provisioner.matchAll(/"role-[ab]": "([a-z_]+)"/g)].map((match) => match[1]);
    expect([DEFAULT_ROLE, ...granted]).toEqual([...CONFORMANCE_ROLES]);
  });
});
