/**
 * The schema-first reader facade for the compatibility-case format.
 *
 * `case-format.generated.ts` is the `json-schema-to-typescript` view of
 * `core/schemas/compatibility-case.schema.json` — the single canonical description
 * of the case shape the `@parallax/conformance` loader validates each document
 * against (with Ajv, at load). This module re-exports those generated types under
 * working names and supplies the small structural accessors every shape reader
 * shares: the golden `{sql, binds}` statement entries under `then.statements` (or a
 * per-step `statements`), a naive `given.apply` entry's plain SQL, and the
 * per-statement binds. There is no positional pairing left to interpret — each
 * statement entry carries its own binds inline.
 */
import type {
  ParallaxCompatibilityCaseMCaseFormat,
  StatementEntry,
} from "./case-format.generated.js";

/** A parsed, schema-valid compatibility case document (the generated static view). */
export type CaseDocument = ParallaxCompatibilityCaseMCaseFormat;

export type { StatementEntry } from "./case-format.generated.js";

/** A statement entry resolved to one dialect: its SQL text plus its authored binds. */
export interface DialectStatement {
  readonly sql: string;
  readonly binds: readonly unknown[];
}

/** The authored binds of a statement entry (dialect-agnostic; defaults to `[]`). */
export function entryBinds(entry: StatementEntry): readonly unknown[] {
  return entry.binds ?? [];
}

/**
 * The SQL text a statement entry carries for `dialect`. A golden entry's `sql` is a
 * dialect-keyed map — this returns the dialect's text, or `undefined` when that
 * dialect is absent; a naive `given.apply` entry's `sql` is a plain string, returned
 * verbatim for every dialect.
 */
export function entrySql(entry: StatementEntry, dialect: string): string | undefined {
  return typeof entry.sql === "string" ? entry.sql : entry.sql[dialect];
}

/** The golden statement entries at `then.statements` (empty when none authored). */
export function goldenEntries(doc: CaseDocument): readonly StatementEntry[] {
  return doc.then?.statements ?? [];
}

/**
 * Resolve statement entries to their `{sql, binds}` for `dialect`, in order, skipping
 * any entry whose golden map omits the dialect (a Postgres-only case read on MariaDB).
 */
export function dialectStatements(
  entries: readonly StatementEntry[],
  dialect: string,
): readonly DialectStatement[] {
  const out: DialectStatement[] = [];
  for (const entry of entries) {
    const sql = entrySql(entry, dialect);
    if (sql !== undefined) {
      out.push({ sql, binds: entryBinds(entry) });
    }
  }
  return out;
}
