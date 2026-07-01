/**
 * The per-case result-matrix report — the first-class "is the slice green, and
 * what regressed?" artifact (design Q7 fast-feedback signal).
 *
 * The accumulator records one `{ case, command, status }` entry per case ×
 * command outcome (`ok` / `error` / `unsupported` for a raw adapter result;
 * `pass` / `fail` when a run/compile lane graded the observation against the
 * golden). {@link renderMatrixReport} folds the entries into a compact,
 * human-readable summary with per-status counts and an explicit residuals list —
 * so a reader can answer "is the slice green?" at a glance, and a regression names
 * the exact offending case IDs.
 */

/** The terminal status the adapter assigned a case for one command. */
export type MatrixStatus = "ok" | "error" | "unsupported" | "pass" | "fail";

/** One row of the matrix: a case × command outcome. */
export interface MatrixEntry {
  readonly casePath: string;
  readonly command: string;
  readonly status: MatrixStatus;
  readonly note?: string;
}

/** Accumulate per-case outcomes into an ordered matrix. */
export class CaseMatrix {
  private readonly entries: MatrixEntry[] = [];

  /** Record one outcome. */
  record(entry: MatrixEntry): void {
    this.entries.push(entry);
  }

  /** All recorded entries, in record order. */
  all(): readonly MatrixEntry[] {
    return this.entries;
  }

  /** Count of entries with the given status. */
  count(status: MatrixStatus): number {
    return this.entries.filter((e) => e.status === status).length;
  }

  /** Render the report over the accumulated entries. */
  report(): MatrixReport {
    return summarizeMatrix(this.entries);
  }
}

/** The statuses a matrix report tallies, in a fixed column order. */
const REPORT_STATUSES: readonly MatrixStatus[] = ["ok", "pass", "error", "fail", "unsupported"];

/** A residual entry — a case×command that did NOT come out green. */
export interface MatrixResidual {
  readonly casePath: string;
  readonly command: string;
  readonly status: MatrixStatus;
  readonly note?: string;
}

/** The folded matrix report: per-status counts + the non-green residuals. */
export interface MatrixReport {
  /** Total case×command entries recorded. */
  readonly total: number;
  /** Count per status, in `REPORT_STATUSES` order (zeros included). */
  readonly counts: Readonly<Record<MatrixStatus, number>>;
  /** True when every entry is green (`ok` / `pass`) — the slice is green. */
  readonly green: boolean;
  /** The non-green entries (`error` / `fail` / `unsupported`), by case ID. */
  readonly residuals: readonly MatrixResidual[];
}

/** True when a status is a green outcome (`ok` for a raw result, `pass` for a grade). */
export function isGreenStatus(status: MatrixStatus): boolean {
  return status === "ok" || status === "pass";
}

/**
 * Fold a list of matrix entries into a {@link MatrixReport}: total, per-status
 * counts, whether the slice is green (every entry `ok`/`pass`), and the residual
 * list of non-green entries (so a regression is reported with precise case IDs).
 */
export function summarizeMatrix(entries: readonly MatrixEntry[]): MatrixReport {
  const counts = Object.fromEntries(REPORT_STATUSES.map((status) => [status, 0])) as Record<
    MatrixStatus,
    number
  >;
  const residuals: MatrixResidual[] = [];
  for (const entry of entries) {
    counts[entry.status] += 1;
    if (!isGreenStatus(entry.status)) {
      residuals.push({
        casePath: entry.casePath,
        command: entry.command,
        status: entry.status,
        ...(entry.note === undefined ? {} : { note: entry.note }),
      });
    }
  }
  return { total: entries.length, counts, green: residuals.length === 0, residuals };
}

/**
 * Render a matrix report to a compact, human-readable block: a headline verdict,
 * the per-status counts, and (when not green) the residual case IDs + reasons.
 * Suitable for a CI job summary or a `--report` stdout dump.
 */
export function renderMatrixReport(report: MatrixReport): string {
  const lines: string[] = [];
  const verdict = report.green ? "GREEN" : "NOT GREEN";
  lines.push(`case-matrix: ${verdict} (${report.total} case×command outcomes)`);
  const counts = REPORT_STATUSES.filter((status) => report.counts[status] > 0)
    .map((status) => `${status}=${report.counts[status]}`)
    .join("  ");
  lines.push(`  ${counts}`);
  if (!report.green) {
    lines.push("  residuals:");
    for (const residual of report.residuals) {
      const id = caseId(residual.casePath);
      const note = residual.note ? ` — ${residual.note}` : "";
      lines.push(`    ${id} [${residual.command}] ${residual.status}${note}`);
    }
  }
  return lines.join("\n");
}

/** The four-digit case ID (`0003`) from a repo-relative case path, else the path. */
function caseId(casePath: string): string {
  const match = /(\d{4})-[^/]*\.ya?ml$/.exec(casePath);
  return match?.[1] ?? casePath;
}
