/**
 * Transaction / write-sequence / locking **compile lane** over the transaction +
 * optimistic-locking corpus, Docker-free.
 *
 * Drives the adapter's `runCompile` — the same path the CLI exercises — over the
 * twenty-one `slice-mvp-1` harness-lane transaction-family cases, asserting the
 * emitted SQL + binds equal the golden BY TEXT. The six shapes this slice exercises
 * for the first time:
 *
 *  - **read-lock** (`m-read-lock-001`, `read` shape): the single emission is
 *    the plain `eq` read with the dialect lock suffix `for share of t0` appended;
 *  - **write sequence** (`m-batch-write-001`/`m-unit-work-003`/`m-batch-write-002`
 *    batched non-temporal writes on the non-versioned `Wallet`; `m-opt-lock-002`
 *    locking-mode versioned update): one emission per generated DML statement — a
 *    multi-row `INSERT`, a uniform `pk in (…)` update, one keyed `UPDATE` per
 *    distinct key, or the ungated version-advancing `UPDATE` — each keyed by its
 *    `/writeSequence/<step>` pointer;
 *  - **scenario** (`m-unit-work-001`, read-your-own-writes; `m-unit-work-002`,
 *    rollback/abort; `m-opt-lock-001`, no-op-update-no-DML): a scenario is NOT
 *    compiled to SQL, but the adapter surfaces the
 *    per-step golden so the gate classifies it in-claim, `roundTrips` the declared
 *    case total;
 *  - **conflict** (`m-opt-lock-005`/`-006`/`-007`, optimistic locking;
 *    `m-temporal-read-009`–`-012`, optimistic × temporal close): one emission per
 *    attempt's generated versioned `UPDATE` / gated milestone close, keyed by its
 *    case pointer;
 *  - **error** (`m-read-lock-006`, read-lock-blocks-writer): NOT compiled to SQL —
 *    its golden lives per round in `concurrency.rounds`, surfaced as one emission per
 *    node so the gate classifies it in-claim (the two-connection behavior is run-lane
 *    only);
 *  - **concurrencySuccess** (`m-read-lock-007`, read-lock-shared-compatible;
 *    `m-read-lock-008`, projection-omits-lock-admits-writer): like `error`, NOT
 *    compiled to SQL — the per-round `concurrency.rounds` golden is surfaced as one
 *    emission per node (the two-connection "no error + expectRows on the held
 *    session" proof is run-lane only).
 *
 * The Docker-gated Postgres full m-case-format profile (`@parallax/typescript`'s
 * `slice-run.test.ts`) proves the SQL leaves the right rows / table state /
 * affected-row counts.
 */
import { describe, expect, it } from "vitest";
import {
  type DialectStatement,
  dialectStatements,
  goldenEntries,
  type StatementEntry,
} from "../src/case-format.js";
import { isConflict } from "../src/conflict.js";
import { discoverCasePaths, loadCase } from "../src/discover.js";
import { runCompile, TYPESCRIPT_ADAPTER } from "../src/index.js";
import { isScenario } from "../src/scenario.js";
import { isWriteSequence } from "../src/write-sequence.js";

/**
 * The transaction-family module tags this lane compiles: any `slice-mvp-1` case
 * carrying one of these on the harness lane. The optimistic × temporal-close cases
 * (`m-temporal-read-009`–`-012`) file under `m-temporal-read` but carry `m-opt-lock`
 * as a secondary tag, so tag membership (not the primary module) is the selector.
 */
const TXN_MODULES: ReadonlySet<string> = new Set([
  "m-read-lock",
  "m-batch-write",
  "m-unit-work",
  "m-opt-lock",
]);

/**
 * The in-scope transaction/locking MVP cases the HARNESS compiles (the four Phase-7
 * shapes + the harness-lane auto-retry `m-opt-lock-009`). `api-conformance`-lane
 * cases (the read-lock matrix `m-read-lock-002`–`-005`, the boundary retry cases)
 * are excluded — they have no harness-compiled golden (the API Conformance Suite
 * satisfies them), so `runCompile` routes them to a suite-satisfied `unsupported`.
 */
function txnCases(): readonly { id: string; path: string }[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(m-[a-z0-9-]+-\d{3})-.*$/, "$1"), path }))
    .map(({ id, path }) => ({ id, path, loaded: loadCase(path) }))
    .filter(({ loaded }) => loaded.tags.some((tag) => TXN_MODULES.has(tag)))
    .filter(({ loaded }) => loaded.tags.includes("slice-mvp-1"))
    .filter(({ loaded }) => loaded.lane !== "api-conformance")
    .map(({ id, path }) => ({ id, path }));
}

/**
 * The EXACT in-scope harness-lane transaction MVP id set: read-lock
 * `m-read-lock-001`, batched writes `m-batch-write-001`/`m-unit-work-003`/
 * `m-batch-write-002`, read-your-own-writes `m-unit-work-001`, rollback/abort
 * `m-unit-work-002`, no-op update `m-opt-lock-001`, locking-mode versioned update
 * `m-opt-lock-002`, the optimistic-lock conflict/retry `m-opt-lock-005`/`-006`/`-007`, the
 * harness-lane auto-retry `m-opt-lock-009`, the read-lock-blocks-writer concurrency
 * case `m-read-lock-006`, the read-lock-shared-compatible `m-read-lock-007` and
 * projection-omits-lock-admits-writer `m-read-lock-008` concurrency-success cases,
 * and the optimistic × temporal close cases `m-temporal-read-009`–`-012`. Asserting
 * the exact set fails loudly on a discovery regression (the untagged pkgen / cache /
 * cascade / detached-merge / error-class cases, and the api-conformance-lane
 * read-lock / boundary cases, must NOT leak in).
 */
const EXPECTED_IDS: readonly string[] = [
  "m-read-lock-001",
  "m-batch-write-001",
  "m-unit-work-001",
  "m-unit-work-002",
  "m-opt-lock-001",
  "m-opt-lock-002",
  "m-unit-work-003",
  "m-batch-write-002",
  "m-opt-lock-005",
  "m-opt-lock-006",
  "m-opt-lock-007",
  "m-opt-lock-009",
  "m-read-lock-006",
  "m-read-lock-007",
  "m-temporal-read-009",
  "m-temporal-read-010",
  "m-temporal-read-011",
  "m-temporal-read-012",
  "m-read-lock-008",
  // The full-bitemporal optimistic cases (COR-26): the gated inactivation-close
  // conflict pair `m-bitemp-write-004`/`-005` and the end-to-end optimistic-gated
  // rectangle split `m-bitemp-write-008` (writeSequence) — all carry `m-opt-lock`.
  "m-bitemp-write-004",
  "m-bitemp-write-005",
  "m-bitemp-write-008",
  // COR-26 Phase 2 — audit-chaining breadth + unit-work RYOW (already-claimed
  // modules): the optimistic-gated audit close `m-audit-write-006` (conflict, carries
  // `m-opt-lock`), the read-your-own-writes update/delete scenarios `m-unit-work-005`/
  // `-006`, the non-cascade FK-delete ordering `m-unit-work-007` (writeSequence,
  // delete), and the insert-update combining scenario `m-unit-work-008`.
  "m-audit-write-006",
  "m-unit-work-005",
  "m-unit-work-006",
  "m-unit-work-007",
  "m-unit-work-008",
  // COR-26 Phase 3 — batch-DELETE + opt-lock edges + mixed-op flush (already-claimed
  // modules): the non-versioned DELETE collapse `m-batch-write-003` (writeSequence,
  // `delete ... where id in (…)`), the versioned per-key gated delete
  // `m-batch-write-004` (writeSequence, one `... where id = ? and version = ?` per
  // key), the conflict-aborts-UoW scenario `m-opt-lock-012`, the multi-attribute
  // versioned update `m-opt-lock-013` (conflict), and the mixed-op flush scenario
  // `m-unit-work-009`.
  "m-batch-write-003",
  "m-batch-write-004",
  "m-opt-lock-012",
  "m-opt-lock-013",
  "m-unit-work-009",
  // COR-26 Phase 5 — the promoted pk-gen cases carry `m-unit-work`, so they enter
  // this lane: the `max` allocations `m-pk-gen-001`/`-002` (insert ... select
  // coalesce(max(col), ?) + ?) and the simulated-sequence allocations
  // `m-pk-gen-004`/`-006` (update ... set next_val = next_val + ? then the reserved
  // id insert). The sequence x temporal `m-pk-gen-014` files under `m-pk-gen` +
  // `m-audit-write` (no TXN_MODULE tag), so it is graded by the run lane, not here.
  "m-pk-gen-001",
  "m-pk-gen-002",
  "m-pk-gen-004",
  "m-pk-gen-006",
  // COR-26 Phase 5 — value-object write cases cross-tagged into the transaction
  // family: the multi-row batched VO insert `m-value-object-045` (carries
  // `m-batch-write`) and the versioned VO document write under an optimistic gate
  // `m-value-object-046` (carries `m-opt-lock`).
  "m-value-object-045",
  "m-value-object-046",
  // COR-3 snapshot slice — the unit-of-work rollback breadth cases cross-tagged
  // slice-mvp-1: the aborting-callback INSERT `m-unit-work-011` and DELETE
  // `m-unit-work-012` (both scenario shape, carrying `m-unit-work`).
  "m-unit-work-011",
  "m-unit-work-012",
];

const CASES = txnCases();

/** A scenario / write step as authored (its golden statement entries). */
interface StepWithStatements {
  readonly statements?: readonly StatementEntry[];
}

/**
 * The ordered golden Postgres statements (`{sql, binds}`) a case declares, per its
 * shape — read from the SAME `then.statements` / per-step `statements` entries the
 * runner emits from, in emission order. Each entry carries its own inline binds.
 */
function expectedStatements(loaded: ReturnType<typeof loadCase>): readonly DialectStatement[] {
  const raw = loaded.raw;
  if (loaded.shape === "error" || loaded.shape === "concurrencySuccess") {
    // A concurrency case (error `m-read-lock-006`, or concurrency-success
    // `m-read-lock-007`/`m-read-lock-008`) keeps its golden per round inside
    // `when.concurrency.rounds[].{A,B}.statements` — flatten in round/A/B order.
    const rounds = raw.when?.concurrency?.rounds ?? [];
    return rounds.flatMap((round) =>
      (["A", "B"] as const).flatMap((node) =>
        dialectStatements((round[node]?.statements ?? []) as readonly StatementEntry[], "postgres"),
      ),
    );
  }
  if (isScenario(loaded)) {
    // A step may list several golden statements; flatten them in authored order.
    const steps = (raw.when?.scenario ?? []) as readonly StepWithStatements[];
    return steps.flatMap((step) => dialectStatements(step.statements ?? [], "postgres"));
  }
  if (isConflict(loaded)) {
    const attempts = raw.when?.attempts;
    if (attempts) {
      return attempts.flatMap((attempt) =>
        dialectStatements(attempt.statements as readonly StatementEntry[], "postgres"),
      );
    }
    return dialectStatements(goldenEntries(raw), "postgres");
  }
  return dialectStatements(goldenEntries(raw), "postgres");
}

/** The ordered golden Postgres SQL texts a case declares, per its shape. */
function goldenStatements(loaded: ReturnType<typeof loadCase>): readonly string[] {
  return expectedStatements(loaded).map((statement) => statement.sql);
}

/** The per-statement authored binds a case declares, in emission order. */
function goldenBinds(loaded: ReturnType<typeof loadCase>): readonly (readonly unknown[])[] {
  return expectedStatements(loaded).map((statement) => statement.binds);
}

describe("txn compile lane — emitted === golden over the transaction corpus", () => {
  it("discovers exactly the in-scope transaction MVP cases", () => {
    expect(CASES.map(({ id }) => id).sort()).toEqual([...EXPECTED_IDS].sort());
  });

  it.each(CASES)("$id compiles to the golden Postgres SQL + binds", ({ path }) => {
    const loaded = loadCase(path);
    const envelope = runCompile(loaded, "postgres", TYPESCRIPT_ADAPTER);
    expect(envelope.status, JSON.stringify(envelope)).toBe("ok");
    if (envelope.status !== "ok" || envelope.command !== "compile") {
      throw new Error("expected an ok compile envelope");
    }

    expect(envelope.emissions.map((e) => e.sql)).toEqual(goldenStatements(loaded));
    expect(envelope.emissions.map((e) => e.binds)).toEqual(goldenBinds(loaded));

    // Shape-specific `roundTrips` + case-pointer conventions.
    if (isWriteSequence(loaded) || isConflict(loaded)) {
      expect(envelope.roundTrips).toBe(envelope.emissions.length);
    }
    if (isScenario(loaded)) {
      expect(envelope.roundTrips).toBe(loaded.raw.then?.roundTrips);
    }
    if (loaded.shape === "read") {
      expect(envelope.emissions).toHaveLength(1);
      expect(envelope.emissions[0]?.casePointer).toBe("/operation");
      expect(envelope.roundTrips).toBe(1);
    }
  });
});
