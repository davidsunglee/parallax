import type { Capabilities, CaseShape, Command, ModuleTag } from "@parallax/core";
import type { LoadedCase } from "./discover.js";
import { type GateDiagnosticCode, inClaim } from "./gate.js";

export interface CommandSliceCoverage {
  readonly command: Command;
  readonly dialect: string;
  readonly claimedCases: number;
  readonly outOfClaim: Readonly<Record<GateDiagnosticCode, number>>;
}

export interface ConformanceSliceCoverageReport {
  readonly sliceTag: string | null;
  readonly dialect: string;
  readonly totalCorpusCases: number;
  readonly claimedCases: number;
  readonly claimedCaseIds: readonly string[];
  readonly byShape: Readonly<Partial<Record<CaseShape, number>>>;
  readonly byModule: Readonly<Record<string, number>>;
  readonly byCommand: readonly CommandSliceCoverage[];
}

export interface ConformanceSliceCoverageOptions {
  readonly dialect?: string;
  readonly commands?: readonly Command[];
}

const DEFAULT_CASE_COMMANDS: readonly Command[] = ["compile", "run"];

const GATE_CODES: readonly GateDiagnosticCode[] = [
  "unsupported-command",
  "unsupported-dialect",
  "unsupported-shape",
  "unsupported-case-tag",
  "missing-include-tag",
  "excluded-case-tag",
];

export function buildConformanceSliceCoverageReport(
  cases: readonly LoadedCase[],
  capabilities: Capabilities,
  options: ConformanceSliceCoverageOptions = {},
): ConformanceSliceCoverageReport {
  const dialect = options.dialect ?? capabilities.dialects[0] ?? "unknown";
  const commands = options.commands ?? caseCommands(capabilities.commands);
  const primaryCommand = commands[0] ?? "compile";
  const claimed = cases.filter((c) => inClaim(c, primaryCommand, dialect, capabilities).inClaim);

  return {
    sliceTag: capabilities.caseTags?.include?.[0] ?? null,
    dialect,
    totalCorpusCases: cases.length,
    claimedCases: claimed.length,
    claimedCaseIds: claimed.map((c) => caseId(c.casePath)),
    byShape: countBy(claimed, (c) => c.shape),
    byModule: countModules(claimed),
    byCommand: commands.map((command) =>
      buildCommandCoverage(cases, capabilities, command, dialect),
    ),
  };
}

export function renderConformanceSliceCoverageMarkdown(
  report: ConformanceSliceCoverageReport,
): string {
  const lines: string[] = [];
  lines.push("## TypeScript Conformance Slice Coverage");
  lines.push("");
  lines.push(`- Slice: ${report.sliceTag ? `\`${report.sliceTag}\`` : "none"}`);
  lines.push(`- Dialect: \`${report.dialect}\``);
  lines.push(`- Claimed cases: **${report.claimedCases} / ${report.totalCorpusCases}**`);
  lines.push("");
  lines.push("| Command | Claimed cases | Out of claim |");
  lines.push("| --- | ---: | ---: |");
  for (const command of report.byCommand) {
    const outOfClaim = Object.values(command.outOfClaim).reduce((sum, count) => sum + count, 0);
    lines.push(`| \`${command.command}\` | ${command.claimedCases} | ${outOfClaim} |`);
  }
  lines.push("");
  lines.push("| Shape | Claimed cases |");
  lines.push("| --- | ---: |");
  for (const [shape, count] of sortedEntries(report.byShape)) {
    lines.push(`| \`${shape}\` | ${count} |`);
  }
  lines.push("");
  lines.push("| Module tag | Claimed cases |");
  lines.push("| --- | ---: |");
  for (const [module, count] of sortedEntries(report.byModule)) {
    lines.push(`| \`${module}\` | ${count} |`);
  }
  lines.push("");
  lines.push(`<details><summary>Claimed case ids</summary>`);
  lines.push("");
  lines.push(report.claimedCaseIds.map((id) => `\`${id}\``).join(", "));
  lines.push("");
  lines.push("</details>");
  return lines.join("\n");
}

function buildCommandCoverage(
  cases: readonly LoadedCase[],
  capabilities: Capabilities,
  command: Command,
  dialect: string,
): CommandSliceCoverage {
  const outOfClaim = Object.fromEntries(GATE_CODES.map((code) => [code, 0])) as Record<
    GateDiagnosticCode,
    number
  >;
  let claimedCases = 0;
  for (const c of cases) {
    const gate = inClaim(c, command, dialect, capabilities);
    if (gate.inClaim) {
      claimedCases += 1;
    } else {
      outOfClaim[gate.code] += 1;
    }
  }
  return { command, dialect, claimedCases, outOfClaim };
}

function caseCommands(commands: readonly Command[]): readonly Command[] {
  const claimed = commands.filter((command) => DEFAULT_CASE_COMMANDS.includes(command));
  return claimed.length > 0 ? claimed : DEFAULT_CASE_COMMANDS;
}

function countBy<T, K extends string>(
  items: readonly T[],
  keyOf: (item: T) => K,
): Partial<Record<K, number>> {
  const counts: Partial<Record<K, number>> = {};
  for (const item of items) {
    const key = keyOf(item);
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function countModules(cases: readonly LoadedCase[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const c of cases) {
    for (const tag of c.tags) {
      if (isModuleTag(tag)) {
        counts[tag] = (counts[tag] ?? 0) + 1;
      }
    }
  }
  return counts;
}

function isModuleTag(tag: string): tag is ModuleTag {
  return /^m-[a-z0-9]+(-[a-z0-9]+)*$/.test(tag);
}

function sortedEntries<T extends Record<string, number> | Partial<Record<string, number>>>(
  counts: T,
): readonly (readonly [string, number])[] {
  return Object.entries(counts)
    .filter((entry): entry is [string, number] => entry[1] !== undefined)
    .sort(([a], [b]) => a.localeCompare(b, "en", { numeric: true }));
}

function caseId(casePath: string): string {
  return /(\d{4})-[^/]*\.ya?ml$/.exec(casePath)?.[1] ?? casePath;
}
