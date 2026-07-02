/**
 * Developer-showcase **coverage** check (Phase 10c): no in-slice case is silently
 * absent.
 *
 * Every `slice-mvp-1` case MUST be either showcased (in a family file)
 * or listed in the skip manifest with a reason. This test discovers the whole slice
 * off the corpus and asserts that partition exactly — so adding a corpus case, or
 * dropping a showcase, fails the build until the coverage map or the skip manifest
 * is updated. It is Docker-free (pure discovery), so it runs in the fast lane too.
 */

import { discoverCasePaths, loadCase } from "@parallax/conformance";
import { expect, it } from "vitest";
import { idOf, SHOWCASED } from "./covered.js";
import { SKIP_MANIFEST, SKIPPED_IDS } from "./skip-manifest.js";

/** The four-digit ids of the whole `slice-mvp-1` slice, from the corpus. */
function sliceIds(): readonly string[] {
  return discoverCasePaths()
    .map((path) => ({ id: path.replace(/^.*\/(\d{4})-.*$/, "$1"), path }))
    .filter(({ path }) => loadCase(path).tags.includes("slice-mvp-1"))
    .map(({ id }) => id)
    .sort();
}

const SLICE = sliceIds();
const SHOWCASED_IDS = new Set(SHOWCASED.map(idOf));

it("discovers the whole slice-mvp-1 slice (99 cases)", () => {
  expect(SLICE.length).toBe(99);
});

it("every in-slice case is showcased or skipped-with-reason (no silent gaps)", () => {
  const uncovered = SLICE.filter((id) => !SHOWCASED_IDS.has(id) && !SKIPPED_IDS.has(id));
  expect(
    uncovered,
    `these in-slice cases are neither showcased nor in the skip manifest:\n  ${uncovered.join(
      ", ",
    )}`,
  ).toEqual([]);
});

it("the showcased + skipped partition covers exactly the slice (no strays)", () => {
  const partition = new Set<string>([...SHOWCASED_IDS, ...SKIPPED_IDS]);
  // Every partition id is a real in-slice case (no showcase points at a stale id).
  const strays = [...partition].filter((id) => !SLICE.includes(id)).sort();
  expect(
    strays,
    `these showcased/skipped ids are not in the slice:\n  ${strays.join(", ")}`,
  ).toEqual([]);
  // The partition sizes sum to the slice (showcased and skipped are disjoint).
  expect(SHOWCASED_IDS.size + SKIPPED_IDS.size).toBe(SLICE.length);
});

it("every skipped case carries a non-empty reason", () => {
  for (const skipped of SKIP_MANIFEST) {
    expect(skipped.reason.trim().length, `skip ${skipped.id} has no reason`).toBeGreaterThan(0);
  }
});
