/**
 * The full-slice **compile lane + honesty gate** (Docker-free).
 *
 * This is the Phase-8 "is the whole slice green?" sweep, at the adapter's
 * contract boundary (the runner's `runCompile`, the same path the CLI drives):
 *
 *  - **Full compile sweep.** `test.each` over every harness-lane `slice-mvp-1`
 *    tagged case (111): each compiles to an `ok` envelope, and for a `read`-shaped
 *    case (whose golden is a single string) the emitted SQL + binds equal the
 *    golden by construction. Write / scenario / conflict goldens are multi-string
 *    / per-step and graded structurally in the run lane; here they must compile
 *    `ok` (never `unsupported`, never `error`).
 *  - **Honesty — in-claim never `unsupported`.** No tagged (in-claim) case may
 *    return `unsupported`; doing so is itself a conformance failure (the six-
 *    condition gate must route every in-claim case to a real attempt).
 *  - **Honesty — out-of-claim ⇒ `unsupported` + the right diagnostic.** Four
 *    representatives exercise each gate branch: a non-Postgres dialect
 *    (`unsupported-dialect`), an unclaimed module tag (`unsupported-case-tag`), an
 *    excluded shape (`unsupported-shape`), and an untagged in-claim-module read
 *    (`missing-include-tag`).
 *  - **Case-matrix report.** The sweep folds every outcome into the first-class
 *    matrix report and asserts it is GREEN with zero residuals — the "what
 *    regressed?" artifact a reader consults at a glance.
 *
 * The DB-backed grade (rows / graph / tableState / affectedRows) is the run-lane
 * sweep (`typescript/test/slice-run.test.ts`), which lives in the composition root
 * because the concrete Testcontainers provider does.
 */

import type { Envelope } from "@parallax/core";
import { expect, describe as group, it } from "vitest";
import { dialectStatements, goldenEntries } from "../src/case-format.js";
import {
  CaseMatrix,
  discoverCasePaths,
  type LoadedCase,
  loadCase,
  type MatrixStatus,
  renderMatrixReport,
  runCompile,
  TYPESCRIPT_ADAPTER,
} from "../src/index.js";

/**
 * The matrix status a compile outcome contributes. A `rejected` case is graded
 * GREEN when it returns an `error` envelope whose diagnostic names the case's
 * `then.rejectedRule` (the pre-SQL refusal is its expected result — m-value-object
 * resolved Q7); every other in-claim case is green iff it compiled `ok`.
 */
function compileMatrixStatus(envelope: Envelope, loaded: LoadedCase): MatrixStatus {
  if (loaded.shape === "rejected") {
    const ok =
      envelope.status === "error" &&
      envelope.diagnostics[0]?.code === loaded.raw.then?.rejectedRule;
    return ok ? "pass" : "fail";
  }
  return envelope.status as MatrixStatus;
}

/**
 * The full `slice-mvp-1` tagged slice the HARNESS executes, in discovery order.
 * `api-conformance`-lane cases (boundary retry cases + the read-lock matrix reads)
 * are excluded: they have no harness-executable golden — their observable is proven
 * by the API Conformance Suite — so this sweep covers the 111 harness-lane cases
 * (101 pre-Phase-4 cases + the harness-lane auto-retry case `m-opt-lock-009` + the
 * two Phase-5 versioned set-based materialize scenarios `m-opt-lock-003`/`-004` + the
 * four Phase-6 optimistic × temporal close cases `m-temporal-read-009`–`-012` + the
 * COR-12 behavioral read-lock cases `m-read-lock-006` (blocks-writer),
 * `m-read-lock-007` (shared-compatible), and `m-read-lock-008`
 * (projection-omits-lock-admits-writer)).
 */
function taggedCases(): readonly { id: string; loaded: LoadedCase }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .map(({ id, path }) => ({ id, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"))
    .filter(({ loaded }) => loaded.lane !== "api-conformance")
    .map(({ id, loaded }) => ({ id, loaded }));
}

const CASES = taggedCases();

/** The Postgres golden `{sql, binds}` a `read`-shaped case pins (one statement entry). */
function readGolden(loaded: LoadedCase): { sql: string; binds: readonly unknown[] } | undefined {
  return dialectStatements(goldenEntries(loaded.raw), "postgres")[0];
}

group("full-slice compile sweep (Docker-free)", () => {
  it("discovers the harness-lane slice-mvp-1 slice (153 cases)", () => {
    // The slice is include-driven; the exact count guards against a discovery
    // regression that silently drops (or over-collects) a tagged case. This is the
    // harness-executable subset (api-conformance-lane cases are filtered out). It
    // grew by the 42 value-object cases (all harness-lane) in Phase 11.
    expect(CASES.length).toBe(153);
  });

  it.each(CASES)("$id compiles ok (in-claim ⇒ never unsupported)", ({ loaded }) => {
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);

    // A `rejected` case is refused PRE-SQL: it returns an `error` envelope whose
    // diagnostic names the violated rule (m-value-object resolved Q7), never a
    // compiled `ok`+golden. That refusal IS its green result.
    if (loaded.shape === "rejected") {
      expect(envelope.status, `${loaded.casePath}: ${JSON.stringify(envelope)}`).toBe("error");
      if (envelope.status !== "error") {
        throw new Error("expected an error (pre-SQL refusal) envelope");
      }
      expect(envelope.diagnostics[0]?.code, loaded.casePath).toBe(loaded.raw.then?.rejectedRule);
      return;
    }

    // Honesty: an in-claim (tagged) case must be attempted — `ok` or `error`,
    // NEVER `unsupported`. The whole slice is green, so it is `ok`.
    expect(envelope.status, `${loaded.casePath}: ${JSON.stringify(envelope)}`).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }

    // A single-statement read golden is compared exactly (`emitted === golden`);
    // this includes `m-core-001`'s `bytes` `encode(t0.payload, ?) payload_hex`
    // projection and the value-object nested-extraction reads.
    const golden = loaded.shape === "read" ? readGolden(loaded) : undefined;
    if (golden !== undefined && envelope.emissions.length === 1) {
      const [emission] = envelope.emissions;
      expect(emission?.sql, loaded.casePath).toBe(golden.sql);
      expect(emission?.binds, loaded.casePath).toEqual(golden.binds);
    }
  });
});

/** One representative per out-of-claim gate branch, with its expected diagnostic. */
const OUT_OF_CLAIM: readonly {
  label: string;
  casePath: string;
  dialect: string;
  code: string;
}[] = [
  {
    label: "a non-Postgres dialect",
    casePath: "core/compatibility/cases/m-op-algebra-002-eq.yaml",
    dialect: "mariadb",
    code: "unsupported-dialect",
  },
  {
    label: "an unclaimed module tag (m-detach)",
    casePath: "core/compatibility/cases/m-detach-002-update.yaml",
    dialect: "postgres",
    code: "unsupported-case-tag",
  },
  {
    label: "an excluded case shape (coherence)",
    casePath: "core/compatibility/cases/m-coherence-004-insert-refetch.yaml",
    dialect: "postgres",
    code: "unsupported-shape",
  },
  {
    label: "an untagged in-claim-module read",
    casePath: "core/compatibility/cases/m-temporal-read-018-business-as-of-now-defaulted.yaml",
    dialect: "postgres",
    code: "missing-include-tag",
  },
];

group("honesty — out-of-claim ⇒ unsupported with the first-failed-filter code", () => {
  it.each(OUT_OF_CLAIM)("$label returns unsupported ($code)", ({ casePath, dialect, code }) => {
    const envelope = runCompile(loadCase(casePath), dialect, TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("unsupported");
    if (envelope.status !== "unsupported") {
      throw new Error("expected an unsupported envelope");
    }
    expect(envelope.diagnostics[0]?.code).toBe(code);
  });
});

group("case-matrix report — the slice is green at a glance", () => {
  it("folds every compile outcome into a GREEN report with no residuals", () => {
    const matrix = new CaseMatrix();
    for (const { loaded } of CASES) {
      const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
      matrix.record({
        casePath: loaded.casePath,
        command: "compile",
        status: compileMatrixStatus(envelope, loaded),
      });
    }
    const report = matrix.report();
    // The rendered report is the human-facing artifact; surface it on failure so
    // a regression names the exact residual case IDs.
    expect(report.green, `\n${renderMatrixReport(report)}`).toBe(true);
    expect(report.total).toBe(153);
    // 143 non-rejected cases compile `ok`; the 10 value-object `rejected` cases are
    // graded `pass` (a correct pre-SQL refusal naming the rule).
    expect(report.counts.ok).toBe(143);
    expect(report.counts.pass).toBe(10);
    expect(report.residuals).toEqual([]);
  });
});
