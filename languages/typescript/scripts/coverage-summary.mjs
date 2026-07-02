import { readFileSync } from "node:fs";

const path = process.argv[2] ?? "coverage/typescript/coverage-summary.json";
const summary = JSON.parse(readFileSync(path, "utf8"));
const total = summary.total;

const metrics = ["lines", "statements", "branches", "functions"];

console.log("## TypeScript Line Coverage");
console.log("");
console.log("| Metric | Covered | Total | Percent |");
console.log("| --- | ---: | ---: | ---: |");
for (const metric of metrics) {
  const entry = total[metric];
  console.log(`| ${label(metric)} | ${entry.covered} | ${entry.total} | ${entry.pct}% |`);
}
console.log("");
console.log("Artifacts include the full V8 coverage output and `lcov.info`.");

function label(metric) {
  return metric[0].toUpperCase() + metric.slice(1);
}
