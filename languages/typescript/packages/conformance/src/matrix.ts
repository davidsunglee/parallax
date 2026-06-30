/**
 * Per-case result-matrix accumulator (the "is the slice green, what regressed?"
 * artifact). Phase 3 ships the minimal accumulator; Phase 8 formalizes the
 * report shape and the CI surface.
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
}
