/** The database the cluster creates at birth; the cloud suite serializes its runs on it. */
export const CONTROL_DATABASE = "parallax_ci_control";

/**
 * The IAM-authenticated login every cloud route uses, and the roles it may act
 * as. They are the conformance provisioner's own names, so the shared reset and
 * grant path applies unchanged on Aurora.
 */
export const CONFORMANCE_LOGIN = "parallax_conformance_login";
export const DEFAULT_ROLE = "parallax_conformance_default";
export const CONFORMANCE_ROLES = [
  DEFAULT_ROLE,
  "parallax_conformance_role_a",
  "parallax_conformance_role_b",
] as const;

const quoted = (names: readonly string[]): string => names.map((name) => `'${name}'`).join(", ");
const roleArray = quoted(CONFORMANCE_ROLES);

/**
 * One statement converging the login and its roles, safe to run any number of
 * times.
 *
 * It runs as the cluster's master user, which is not a superuser, so it sets
 * only attributes that user may set. The control database already exists, made
 * with the cluster, because `CREATE DATABASE` cannot run inside the
 * transaction a `DO` block is; ownership moves to the login, which first lets
 * the master act as it.
 */
export const ROLE_BOOTSTRAP_SQL = `DO $bootstrap$
DECLARE
  member name;
BEGIN
  FOREACH member IN ARRAY ARRAY[${roleArray}]::name[] LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = member) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', member);
    END IF;
  END LOOP;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${CONFORMANCE_LOGIN}') THEN
    CREATE ROLE ${CONFORMANCE_LOGIN} LOGIN;
  END IF;
  ALTER ROLE ${CONFORMANCE_LOGIN} WITH LOGIN CREATEDB;
  GRANT rds_iam TO ${CONFORMANCE_LOGIN};
  FOREACH member IN ARRAY ARRAY[${roleArray}]::name[] LOOP
    EXECUTE format('GRANT %I TO ${CONFORMANCE_LOGIN}', member);
  END LOOP;
  ALTER ROLE ${CONFORMANCE_LOGIN} SET role TO ${DEFAULT_ROLE};
  GRANT ${CONFORMANCE_LOGIN} TO CURRENT_USER;
  ALTER DATABASE ${CONTROL_DATABASE} OWNER TO ${CONFORMANCE_LOGIN};
END
$bootstrap$`;

/** What a converged bootstrap leaves in the cluster, as {@link ROLE_FACTS_SQL} reports it. */
export interface RoleFacts {
  /** Which of the login and its roles exist, sorted. */
  readonly roles: readonly string[];
  readonly login: { readonly canLogin: boolean; readonly createdb: boolean } | null;
  /** The roles the login is a member of, sorted. */
  readonly memberships: readonly string[];
  /** The login's settings in every database. */
  readonly settings: readonly string[] | null;
  readonly controlOwner: string | null;
}

/** One query returning, as a single JSON text value, the {@link RoleFacts} the cluster holds now. */
export const ROLE_FACTS_SQL = `SELECT json_build_object(
  'roles', (SELECT coalesce(json_agg(rolname ORDER BY rolname), '[]') FROM pg_roles
    WHERE rolname IN (${quoted([CONFORMANCE_LOGIN, ...CONFORMANCE_ROLES])})),
  'login', (SELECT json_build_object('canLogin', rolcanlogin, 'createdb', rolcreatedb)
    FROM pg_roles WHERE rolname = '${CONFORMANCE_LOGIN}'),
  'memberships', (SELECT coalesce(json_agg(DISTINCT granted.rolname ORDER BY granted.rolname), '[]')
    FROM pg_auth_members AS membership
    JOIN pg_roles AS granted ON granted.oid = membership.roleid
    JOIN pg_roles AS member ON member.oid = membership.member
    WHERE member.rolname = '${CONFORMANCE_LOGIN}'),
  'settings', (SELECT to_json(setting.setconfig) FROM pg_db_role_setting AS setting
    JOIN pg_roles AS member ON member.oid = setting.setrole
    WHERE member.rolname = '${CONFORMANCE_LOGIN}' AND setting.setdatabase = 0),
  'controlOwner', (SELECT pg_get_userbyid(datdba) FROM pg_database
    WHERE datname = '${CONTROL_DATABASE}')
)::text`;

/** The facts {@link ROLE_BOOTSTRAP_SQL} converges every run to. */
export const CONVERGED_ROLE_FACTS: RoleFacts = {
  roles: [CONFORMANCE_LOGIN, ...CONFORMANCE_ROLES].sort(),
  login: { canLogin: true, createdb: true },
  memberships: [...CONFORMANCE_ROLES, "rds_iam"].sort(),
  settings: [`role=${DEFAULT_ROLE}`],
  controlOwner: CONFORMANCE_LOGIN,
};
