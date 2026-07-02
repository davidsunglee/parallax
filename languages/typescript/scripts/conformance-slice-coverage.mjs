import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import {
  buildConformanceSliceCoverageReport,
  discoverCasePaths,
  SLICE_MVP_1_CAPABILITIES,
  loadCase,
  renderConformanceSliceCoverageMarkdown,
} from "../packages/conformance/dist/index.js";

const args = parseArgs(process.argv.slice(2));
const cases = discoverCasePaths().map(loadCase);
const report = buildConformanceSliceCoverageReport(cases, SLICE_MVP_1_CAPABILITIES);
const markdown = renderConformanceSliceCoverageMarkdown(report);

if (args.json) {
  writeOutput(args.json, `${JSON.stringify(report, null, 2)}\n`);
}
if (args.markdown) {
  writeOutput(args.markdown, `${markdown}\n`);
}
if (!args.json && !args.markdown) {
  console.log(markdown);
}

function parseArgs(argv) {
  const parsed = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--json" || arg === "--markdown") {
      const value = argv[i + 1];
      if (!value) {
        throw new Error(`${arg} requires a path`);
      }
      parsed[arg.slice(2)] = value;
      i += 1;
      continue;
    }
    throw new Error(`unknown argument: ${arg}`);
  }
  return parsed;
}

function writeOutput(path, contents) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents, "utf8");
}
