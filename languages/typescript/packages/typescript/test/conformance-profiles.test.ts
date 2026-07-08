import { describe, expect, it } from "vitest";
import {
  allProfileCases,
  casesForProfile,
  exclusionsForProfile,
  MARIADB_CURATED_PROFILE,
  MARIADB_CURATED_PROFILE_IDS,
  MATRIX_PROFILES,
  POSTGRES_FULL_PROFILE,
  POSTGRES_GRAPH_PROFILE,
  POSTGRES_GRAPH_PROFILE_IDS,
  POSTGRES_READ_PROFILE,
  POSTGRES_READ_PROFILE_IDS,
  POSTGRES_TEMPORAL_PROFILE,
  POSTGRES_TEMPORAL_PROFILE_IDS,
  POSTGRES_TXN_PROFILE,
  POSTGRES_TXN_PROFILE_IDS,
} from "./conformance-profiles.js";

function idsFor(profile: typeof POSTGRES_FULL_PROFILE): readonly string[] {
  return casesForProfile(profile)
    .map(({ id }) => id)
    .sort();
}

describe("m-case-format matrix profiles", () => {
  it("declares stable, unique profile names", () => {
    const names = MATRIX_PROFILES.map((profile) => profile.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it("keeps the canonical Postgres full profile at the 173 harness-lane cases", () => {
    expect(casesForProfile(POSTGRES_FULL_PROFILE)).toHaveLength(173);
  });

  it("folds the historical Postgres read run into a named profile", () => {
    expect(idsFor(POSTGRES_READ_PROFILE)).toEqual([...POSTGRES_READ_PROFILE_IDS].sort());
  });

  it("folds the historical Postgres graph run into a named profile", () => {
    expect(idsFor(POSTGRES_GRAPH_PROFILE)).toEqual([...POSTGRES_GRAPH_PROFILE_IDS].sort());
  });

  it("folds the historical Postgres transaction run into a named profile", () => {
    expect(idsFor(POSTGRES_TXN_PROFILE)).toEqual([...POSTGRES_TXN_PROFILE_IDS].sort());
  });

  it("folds the historical Postgres temporal run into a named profile", () => {
    expect(idsFor(POSTGRES_TEMPORAL_PROFILE)).toEqual([...POSTGRES_TEMPORAL_PROFILE_IDS].sort());
  });

  it("declares MariaDB as a first-class curated 36-case partial profile", () => {
    expect(idsFor(MARIADB_CURATED_PROFILE)).toEqual([...MARIADB_CURATED_PROFILE_IDS].sort());
    expect(casesForProfile(MARIADB_CURATED_PROFILE)).toHaveLength(36);
  });

  it("classifies every non-included Postgres full-profile case as an explicit MariaDB exclusion", () => {
    const all = allProfileCases();
    const postgresFull = casesForProfile(POSTGRES_FULL_PROFILE, all);
    const mariadbIncluded = new Set(
      casesForProfile(MARIADB_CURATED_PROFILE, all).map(({ id }) => id),
    );
    const exclusions = exclusionsForProfile(MARIADB_CURATED_PROFILE, all);
    const excluded = new Set(exclusions.map(({ id }) => id));

    for (const { id } of postgresFull) {
      expect(
        mariadbIncluded.has(id) || excluded.has(id),
        `${id} is neither included nor explicitly excluded from ${MARIADB_CURATED_PROFILE.name}`,
      ).toBe(true);
    }
    expect(exclusions.length).toBe(postgresFull.length - 25);
    // Two exclusion reasons now: the historical no-mariadb-golden reason, plus the
    // value-object cases (which DO carry mariadb golden but are proven by the
    // Phase-10 direct compile tests, not this run-lane profile).
    expect(new Set(exclusions.map(({ reason }) => reason))).toEqual(
      new Set([
        "no goldenSql.mariadb in this partial MariaDB profile",
        "value-object MariaDB parity is proven by the Phase-10 direct compile tests, not this run-lane profile",
      ]),
    );
  });
});
