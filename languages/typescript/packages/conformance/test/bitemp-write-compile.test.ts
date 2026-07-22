/**
 * Full-bitemporal write **compile lane** over TypeScript's `slice-mvp-1` claim,
 * Docker-free (COR-26).
 *
 * Drives the adapter's `runCompile` over its nine claimed `m-bitemp-write` cases and asserts
 * the emitted SQL + binds equal the golden BY TEXT — the DB-free proof that the
 * TypeScript rectangle-split write generation is correct without a database read-back:
 *
 *  - **windowed rectangle split** (`updateUntil` `-001`, `terminateUntil` `-002`,
 *    `insertUntil` `-003`): inactivate + head / (middle) / tail chained milestones
 *    bounded to `[validFrom, until)`;
 *  - **plain (unbounded) write** (`insert` `-009`, `update` `-006`, `terminate` `-007`):
 *    a single fully-current INSERT (insert), or inactivate + head + new-tail (update) /
 *    head only (terminate), the residual window running to the open row's `thru_z`;
 *  - **optimistic-gated** (`-004` / `-005` conflict close, `-008` end-to-end split):
 *    the inactivating close targets the observed rectangle with `… and from_z = ? and
 *    in_z = ?`, the two trailing binds drawn from the currently-open row.
 *
 * The head/tail milestones carry the currently-open row's UNCHANGED columns (acct_num,
 * the old value) — not present in the mutating step's own ① — so this exercises the
 * in-memory replay reconstruction (`buildWriteSequencePlan`). The Docker-gated run lane
 * (`@parallax/typescript`'s `slice-run.test.ts`) additionally proves the DML leaves the
 * right `tableState` / `affectedRows`.
 */
import { postgresDialect } from "@parallax/dialect";
import { describe, expect, it } from "vitest";
import {
  type CaseDocument,
  type DialectStatement,
  dialectStatements,
  goldenEntries,
} from "../src/case-format.js";
import { discoverCasePaths, type LoadedCase, loadCase } from "../src/discover.js";
import { runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";
import { buildWriteSequencePlan } from "../src/write-sequence.js";

/** The nine full-bitemporal write cases claimed by TypeScript's MVP slice. */
function bitempWriteCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({
      id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"),
      path,
      loaded: loadCase(path),
    }))
    .filter(
      ({ id, loaded }) => id.startsWith("m-bitemp-write-") && loaded.tags.includes("slice-mvp-1"),
    )
    .map(({ id, path }) => ({ id, path }))
    .sort((left, right) => left.id.localeCompare(right.id));
}

const CASES = bitempWriteCases();

/** The ordered golden Postgres statements (`{sql, binds}`) a case declares. */
function golden(loaded: ReturnType<typeof loadCase>): readonly DialectStatement[] {
  return dialectStatements(goldenEntries(loaded.raw), "postgres");
}

describe("m-bitemp-write compile lane — emitted === golden over the MVP's nine cases", () => {
  it("discovers exactly the nine MVP-tagged m-bitemp-write cases", () => {
    expect(CASES.map(({ id }) => id)).toEqual([
      "m-bitemp-write-001",
      "m-bitemp-write-002",
      "m-bitemp-write-003",
      "m-bitemp-write-004",
      "m-bitemp-write-005",
      "m-bitemp-write-006",
      "m-bitemp-write-007",
      "m-bitemp-write-008",
      "m-bitemp-write-009",
    ]);
  });

  it.each(CASES)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }
    const expected = golden(loaded);
    expect(envelope.emissions.map((emission) => emission.sql)).toEqual(
      expected.map((statement) => statement.sql),
    );
    expect(envelope.emissions.map((emission) => emission.binds)).toEqual(
      expected.map((statement) => statement.binds),
    );
    // A rectangle split's `roundTrips` is its emitted statement count.
    expect(envelope.roundTrips).toBe(expected.length);
  });
});

// A synthetic MULTI-STEP same-pk sequence — not in the corpus, so it does not move any
// slice count — pins the in-memory replay's open-row EVOLUTION: after a split closes the
// original and chains head / middle / tail, a SECOND split on the same pk must reconstruct
// from the covering NEW open row (its value / from_z / in_z / thru_z), never the stale
// original. Before the open-row set was advanced this reconstructed the wrong head value
// and gate binds; this fixes the emission to the covering rectangle.
describe("m-bitemp-write compile lane — multi-step same-pk replay evolves open rows", () => {
  const T1 = "2024-01-01T00:00:00+00:00";
  const T215 = "2024-02-15T00:00:00+00:00";
  const T3 = "2024-03-01T00:00:00+00:00";
  const T4 = "2024-04-01T00:00:00+00:00";
  const T5 = "2024-05-01T00:00:00+00:00";
  const T6 = "2024-06-01T00:00:00+00:00";
  const T7 = "2024-07-01T00:00:00+00:00";
  const T8 = "2024-08-01T00:00:00+00:00";
  const T9 = "2024-09-01T00:00:00+00:00";
  const INF = "infinity";
  const INSERT_SQL =
    "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) values (?, ?, ?, ?, ?, ?, ?)";
  const GATED_CLOSE_SQL =
    "update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ? and in_z = ?";

  // The position descriptor, reused for an in-memory (non-corpus) write sequence.
  const positionDescriptor = loadCase(
    "core/compatibility/cases/m-bitemp-write-008-update-until-optimistic-gated.yaml",
  ).descriptor;

  /** A synthetic bitemporal write-sequence case over the position model. */
  function syntheticSequence(
    writeSequence: readonly Record<string, unknown>[],
    tags: readonly string[],
  ): LoadedCase {
    return {
      casePath: "synthetic/bitemp-multi-step.yaml",
      raw: {
        model: "models/position.yaml",
        shape: "writeSequence",
        tags,
        when: { writeSequence },
      } as unknown as CaseDocument,
      shape: "writeSequence",
      tags,
      lane: "harness",
      descriptor: positionDescriptor,
      fixtures: {},
    };
  }

  it("a second updateUntil on the same pk splits the covering NEW rectangle, gated", () => {
    // step 1 insert : value 100, business [T1, ∞)
    // step 2 updateUntil : value 200 over [T3, T9) at T215 (splits the original — -008)
    //                      → open head [T1,T3)=100, middle [T3,T9)=200, tail [T9,∞)=100
    // step 3 updateUntil : value 300 over [T4, T5) at T6 — its validFrom T4 lands in
    //                      the MIDDLE rectangle [T3, T9)=200, so the close gates on that
    //                      row's (from_z=T3, in_z=T215) and the head/tail carry its OLD
    //                      value 200 and its thru_z T9 — none of which the stale original
    //                      (100, T1, T1, ∞) would produce.
    const plan = buildWriteSequencePlan(
      syntheticSequence(
        [
          {
            mutation: "insert",
            entity: "Position",
            statements: 1,
            rows: [{ id: 1, acctNum: "A", value: 100 }],
            at: T1,
            validFrom: T1,
          },
          {
            mutation: "updateUntil",
            entity: "Position",
            statements: 4,
            rows: [{ id: 1, value: 200 }],
            at: T215,
            validFrom: T3,
            until: T9,
          },
          {
            mutation: "updateUntil",
            entity: "Position",
            statements: 4,
            rows: [{ id: 1, value: 300 }],
            at: T6,
            validFrom: T4,
            until: T5,
          },
        ],
        ["m-bitemp-write", "m-opt-lock", "write-sequence"],
      ),
      postgresDialect,
    );

    expect(
      plan.statements.map((statement) => ({ sql: statement.sql, binds: statement.binds })),
    ).toEqual([
      // step 1: open the original rectangle
      { sql: INSERT_SQL, binds: [1, "A", 100, T1, INF, T1, INF] },
      // step 2: gated close of the original + head / middle / tail (identical to -008)
      { sql: GATED_CLOSE_SQL, binds: [T215, 1, INF, T1, T1] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T1, T3, T215, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 200, T3, T9, T215, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T9, INF, T215, INF] },
      // step 3: gate + head/tail are drawn from the MIDDLE rectangle (200, T3, T215, T9),
      // NOT the original (100, T1, T1, ∞) — the open-row evolution under test.
      { sql: GATED_CLOSE_SQL, binds: [T6, 1, INF, T3, T215] },
      { sql: INSERT_SQL, binds: [1, "A", 200, T3, T4, T6, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 300, T4, T5, T6, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 200, T5, T9, T6, INF] },
    ]);
  });

  // The updateUntil replay above leaves head + middle + tail all open, so its later
  // same-pk split has a covering NEW rectangle for any instant. A `terminateUntil`
  // evolves the open-row set DIFFERENTLY: it removes the terminated window entirely,
  // leaving a GAP between the surviving head and tail (no middle successor). This pins
  // that the terminate path ALSO advances `openRows` — a later same-pk split covering
  // the surviving TAIL must reconstruct head/tail/gate binds from that tail's state
  // (value / from_z / in_z / thru_z), never the stale original the terminate closed.
  it("a later split after a terminateUntil reconstructs from the surviving tail, gated", () => {
    // step 1 insert        : value 100, business [T1, ∞)
    // step 2 terminateUntil : end the value over [T3, T7) at T215 (splits the original) —
    //                         → open head [T1,T3)=100, tail [T7,∞)=100; the window
    //                           [T3,T7) is TERMINATED (no open row — the gap).
    // step 3 updateUntil    : value 300 over [T8, T9) at T6 — its validFrom T8 lands in
    //                         the surviving TAIL [T7, ∞), so the close gates on that tail's
    //                         (from_z=T7, in_z=T215) and the head/tail carry its thru_z ∞ —
    //                         none of which the stale original (100, T1, T1, ∞) would give.
    const plan = buildWriteSequencePlan(
      syntheticSequence(
        [
          {
            mutation: "insert",
            entity: "Position",
            statements: 1,
            rows: [{ id: 1, acctNum: "A", value: 100 }],
            at: T1,
            validFrom: T1,
          },
          {
            mutation: "terminateUntil",
            entity: "Position",
            statements: 3,
            rows: [{ id: 1 }],
            at: T215,
            validFrom: T3,
            until: T7,
          },
          {
            mutation: "updateUntil",
            entity: "Position",
            statements: 4,
            rows: [{ id: 1, value: 300 }],
            at: T6,
            validFrom: T8,
            until: T9,
          },
        ],
        ["m-bitemp-write", "m-opt-lock", "write-sequence"],
      ),
      postgresDialect,
    );

    expect(
      plan.statements.map((statement) => ({ sql: statement.sql, binds: statement.binds })),
    ).toEqual([
      // step 1: open the original rectangle
      { sql: INSERT_SQL, binds: [1, "A", 100, T1, INF, T1, INF] },
      // step 2: gated close of the original + head / tail (no middle — the window is ended)
      { sql: GATED_CLOSE_SQL, binds: [T215, 1, INF, T1, T1] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T1, T3, T215, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T7, INF, T215, INF] },
      // step 3: gate + head/tail are drawn from the surviving TAIL (100, T7, T215, ∞),
      // NOT the original (100, T1, T1, ∞) — the terminate-path open-row evolution under test.
      { sql: GATED_CLOSE_SQL, binds: [T6, 1, INF, T7, T215] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T7, T8, T6, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 300, T8, T9, T6, INF] },
      { sql: INSERT_SQL, binds: [1, "A", 100, T9, INF, T6, INF] },
    ]);
  });
});
