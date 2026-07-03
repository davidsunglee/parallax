#!/usr/bin/env node
/**
 * Render the developer guide (`docs/guide/*.md`) FROM the API Conformance Suite
 * test snippets (Phase 10c), so the shown examples are the TESTED code — prose and
 * tests stay in lockstep. The script extracts each suite family's per-case `it(...)` blocks
 * (title + the `px.*` / `tx.*` snippet inside) and emits one guide page per family,
 * with a short curated intro.
 *
 * Run: `node languages/typescript/scripts/render-guide.mjs`
 * Check (CI, no write): `node languages/typescript/scripts/render-guide.mjs --check`
 *
 * The extraction is deliberately simple: it reads the family test file, finds each
 * `it("<title>", ...)` / `it.each(...)("<title>", ...)`, and captures the lines a
 * developer would write (the `px` / `tx` / DSL calls), skipping harness plumbing
 * (`provisionCase`, `assert*`, `expect`). It does NOT execute the tests — the tests
 * themselves are the executable proof; this just mirrors their snippets into prose.
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const TS_ROOT = resolve(HERE, "..");
const SUITE_DIR = resolve(TS_ROOT, "packages/typescript/test/api-conformance");
const GUIDE_DIR = resolve(TS_ROOT, "docs/guide");

/** The families, in reading order, with a title + intro for each guide page. */
const FAMILIES = [
  {
    file: "reads.api-conformance.test.ts",
    slug: "01-reads",
    title: "Reading data",
    tableDriven: true,
    exec: "const rows = await px.entity(entity).find(predicate).toArray();",
    intro:
      "Every read is a typed `find` over an entity finder. A predicate is built from the " +
      "generated entity symbols (`Order.id.eq(42)`), which serialize to the same canonical " +
      "operation the engine compiles — so the query you write is the query that runs. A `find` " +
      "returns a lazy `ParallaxList` of **managed objects**: `id` is a `bigint`, `price` a " +
      "`ParallaxDecimal`, a timestamp a `Temporal.Instant`. Each predicate below is a real, " +
      "tested case.",
  },
  {
    file: "deep-fetch.api-conformance.test.ts",
    slug: "02-deep-fetch",
    title: "Deep fetch (eager relationships)",
    tableDriven: true,
    exec: "const { rows, roundTrips } = await px.entity(entity).findGraph(base, options);",
    intro:
      "`find(..., { includes })` eager-loads relationships in **one bulk query per level** " +
      "(`1 + L` round trips, never N+1). Each parent is decorated with its children under the " +
      "relationship's name; the children are managed objects too. Each `find` below is a real, " +
      "tested case (shown as the operation it builds).",
  },
  {
    file: "temporal.api-conformance.test.ts",
    slug: "03-temporal-reads",
    title: "Temporal reads",
    tableDriven: true,
    exec: "const rows = await px.entity(entity).find(base, options).toArray();",
    intro:
      "Temporal reads pin one or both axes with `{ asOf }`, a `range`, or full `history`. An " +
      "omitted axis defaults to *now* (the current row); the business axis is applied outside " +
      "the processing axis. You never write the interval predicates — the engine injects them. " +
      "Each `find` below is a real, tested case.",
  },
  {
    file: "transactions.api-conformance.test.ts",
    slug: "04-transactions",
    title: "Transactions and writes",
    tableDriven: false,
    intro:
      "All writes run inside `px.transaction(async tx => …)`. `create` / `update` / `delete` " +
      "buffer and flush set-based at commit (FK-safe). Audit-only entities chain milestones: " +
      "`create` opens `[now, ∞)`, `update` closes the current row and chains a new one, " +
      "`terminate` closes only — the prior values survive as the audit trail.",
  },
  {
    file: "locking.api-conformance.test.ts",
    slug: "05-locking",
    title: "Locking",
    tableDriven: false,
    intro:
      "The correctness strategy is a per-unit-of-work mode: `px.transaction(body, { concurrency })`. " +
      "In the default `locking` mode, in-transaction reads take a shared row lock **automatically** " +
      "— you write no locking SQL — and a versioned `update` advances the version with no gate. In " +
      "`optimistic` mode reads take no lock and a versioned `update` gates on the version the unit " +
      "of work observed. Version values are **framework-owned**: you read the object, then `update` " +
      "— never passing a raw version. A stale gate throws `ParallaxOptimisticLockError`, which you " +
      "catch and retry after re-reading the fresh row; a no-op `update` (no changed attribute) " +
      "issues no DML.\n\n" +
      "The boundary also offers **bounded automatic retry**: `px.transaction(body, { retries, " +
      "retryOptimisticConflicts })`. On a retriable failure it rolls back, discards the unit of " +
      "work's observed state, and re-executes the body against fresh state — up to `retries` " +
      "re-executions (default 10; `0` disables). Transient database failures (deadlock / " +
      "serialization) are retried automatically; an optimistic-lock conflict is retried only with " +
      "`retryOptimisticConflicts: true`, in which case the re-executed body re-reads the fresh " +
      "version and succeeds with **no caller retry code**. The loop-mechanics cases live in " +
      "`boundary.api-conformance.test.ts`.",
  },
];

/** Extract the developer-facing snippet lines from an `it` body. */
function extractSnippet(body) {
  const lines = body.split("\n");
  const kept = [];
  for (const raw of lines) {
    const line = raw.trim();
    // Keep the lines a developer would write: px / tx / find / create / update /
    // terminate / transaction. Skip harness plumbing + assertions.
    if (
      /(^|\b)(await\s+)?(f\.)?px[.\s]/.test(line) ||
      /\btx\.entity\(/.test(line) ||
      /\.(create|update|terminate|delete|find|single|toArray|transaction)\(/.test(line)
    ) {
      if (
        /provisionCase|assert[A-Z]|expect\(|applyPrecondition|withClock|dockerAvailable/.test(line)
      ) {
        continue;
      }
      kept.push(dedent(raw));
    }
  }
  return kept.join("\n");
}

/** Strip the common leading indentation from a captured line (to ~4 spaces). */
function dedent(raw) {
  return raw.replace(/^\s{0,8}/, "");
}

/**
 * Parse a TABLE-DRIVEN family (reads / deep-fetch / temporal): the `px` execution
 * is shared in one `it.each`, and each case's DSL lives in the `CASES` array as a
 * `predicate: () => …` or `build: () => …` closure. Extract each entry's stem +
 * the exact DSL expression, and pair it with the family's shared execution line.
 */
function parseTableFamily(source, family) {
  const entries = [];
  // Split the CASES array into per-entry blocks keyed by their `stem` / literal.
  const stemRe = /(?:stem:\s*)?"(\d{4}-[a-z0-9-]+)"/g;
  const stems = [];
  let m;
  while ((m = stemRe.exec(source)) !== null) {
    stems.push({ stem: m[1], index: m.index });
  }
  for (let i = 0; i < stems.length; i += 1) {
    const start = stems[i].index;
    const end = i + 1 < stems.length ? stems[i + 1].index : source.length;
    const block = source.slice(start, end);
    const dsl = extractDsl(block);
    if (dsl) {
      entries.push({ title: stems[i].stem, snippet: `${dsl}\n${family.exec}` });
    }
  }
  return entries;
}

/**
 * Extract the DSL expression from a case entry, handling both authoring forms:
 *  - the object form (`{ stem, entity, build: () => <expr> }` — deep-fetch/temporal), and
 *  - the helper form (`p("stem", "Entity", () => <expr>)` / `f("stem", "Entity", base,
 *    options)` — reads). The captured expression is the developer's DSL, verbatim.
 */
function extractDsl(block) {
  // Object form: an explicit `predicate:`/`build:`/`operation:` arrow.
  const keyed = /(?:predicate|build|operation):\s*\(\)\s*=>\s*([\s\S]*?)(?:,\n\s*\}|\},)/.exec(block);
  if (keyed) {
    return dedentBlock(keyed[1].trim().replace(/\.toOperation\(\)$/, ""));
  }
  // Helper `p(...)` form; the block starts at the stem and may run into the next
  // entry, so capture up to the entry-closing `),` at the start of a line.
  const trimmed = block.trim();
  const pForm = /^"[^"]+",\s*"[^"]+",\s*\(\)\s*=>\s*([\s\S]*?)\)\s*,\s*(?:\n|$)/.exec(trimmed);
  if (pForm) {
    return dedentBlock(pForm[1].trim());
  }
  // Helper `f(...)` form: `"stem", "Entity", base, { ...options }),`.
  const fForm = /^"[^"]+",\s*"[^"]+",\s*(\w+),\s*(\{[\s\S]*?\})\s*\)\s*,\s*(?:\n|$)/.exec(trimmed);
  if (fForm) {
    return `find(${fForm[1]}(), ${dedentBlock(fForm[2].trim())})`;
  }
  return undefined;
}

/** Normalize a multi-line captured expression to a readable, left-aligned snippet. */
function dedentBlock(text) {
  const lines = text.split("\n");
  const indents = lines
    .slice(1)
    .filter((l) => l.trim().length > 0)
    .map((l) => l.match(/^\s*/)[0].length);
  const min = indents.length > 0 ? Math.min(...indents) : 0;
  return lines
    .map((l, i) => (i === 0 ? l : l.slice(min)))
    .join("\n")
    .trimEnd();
}

/** Parse a family test file into `{ title, snippet }` entries in source order. */
function parseFamily(source) {
  const entries = [];
  // Match `it("title", ...)` / `it.each(CASES)("title", ...)`.
  const itRe = /\bit(?:\.each\([^)]*\))?\(\s*(?:"([^"]+)"|`([^`]+)`)/g;
  let match;
  const indices = [];
  while ((match = itRe.exec(source)) !== null) {
    indices.push({ title: match[1] ?? match[2] ?? "", start: match.index });
  }
  for (let i = 0; i < indices.length; i += 1) {
    const start = indices[i].start;
    const end = i + 1 < indices.length ? indices[i + 1].start : source.length;
    const body = source.slice(start, end);
    const snippet = extractSnippet(body);
    if (snippet.trim().length > 0) {
      entries.push({ title: indices[i].title, snippet });
    }
  }
  return entries;
}

/** Render one family guide page. */
function renderPage(family, entries) {
  const parts = [
    "<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->",
    "",
    `# ${family.title}`,
    "",
    family.intro,
    "",
    "Every snippet below is extracted from a test that runs it against a real Postgres " +
      "through `@parallax/db-postgres` and asserts the shown result " +
      `(\`packages/typescript/test/api-conformance/${family.file}\`).`,
    "",
  ];
  for (const entry of entries) {
    parts.push(`## ${entry.title}`, "", "```ts", entry.snippet, "```", "");
  }
  return `${parts.join("\n").trimEnd()}\n`;
}

/** Render the guide index. */
function renderIndex() {
  const rows = FAMILIES.map((f) => `- [${f.title}](./${f.slug}.md)`).join("\n");
  return [
    "<!-- AUTO-GENERATED from the API Conformance Suite tests by scripts/render-guide.mjs — DO NOT EDIT. -->",
    "",
    "# Parallax (TypeScript) — developer guide",
    "",
    "A tour of the typed developer surface, rendered from the executable API Conformance Suite: " +
      "every example is a test that runs against a real Postgres and asserts the shown result, " +
      "so the guide can never drift from the code.",
    "",
    rows,
    "",
  ].join("\n");
}

function main() {
  const check = process.argv.includes("--check");
  mkdirSync(GUIDE_DIR, { recursive: true });
  const outputs = new Map();
  outputs.set(resolve(GUIDE_DIR, "index.md"), renderIndex());
  for (const family of FAMILIES) {
    const source = readFileSync(resolve(SUITE_DIR, family.file), "utf8");
    const entries = family.tableDriven
      ? parseTableFamily(source, family)
      : parseFamily(source);
    if (entries.length === 0) {
      throw new Error(`no snippets extracted from ${family.file}`);
    }
    outputs.set(resolve(GUIDE_DIR, `${family.slug}.md`), renderPage(family, entries));
  }

  if (check) {
    let drifted = false;
    const existing = new Set(
      readdirSync(GUIDE_DIR).map((name) => resolve(GUIDE_DIR, name)),
    );
    for (const [path, contents] of outputs) {
      const current = safeRead(path);
      if (current !== contents) {
        process.stderr.write(`guide out of date: ${path}\n`);
        drifted = true;
      }
      existing.delete(path);
    }
    if (drifted) {
      process.stderr.write("run `node languages/typescript/scripts/render-guide.mjs` to regenerate\n");
      process.exit(1);
    }
    process.stdout.write("developer guide is up to date\n");
    return;
  }

  for (const [path, contents] of outputs) {
    writeFileSync(path, contents);
    process.stdout.write(`wrote ${path}\n`);
  }
}

/** Read a file or return `undefined` when it does not exist. */
function safeRead(path) {
  try {
    return readFileSync(path, "utf8");
  } catch {
    return undefined;
  }
}

main();
