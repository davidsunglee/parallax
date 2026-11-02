import { spawnSync } from "node:child_process";

/** One command a rollout tool runs. */
export interface Invocation {
  readonly program: string;
  readonly args: readonly string[];
  readonly cwd?: string;
}

/** What a captured command exited with and printed. */
export interface Completed {
  readonly status: number;
  readonly stdout: string;
  readonly stderr: string;
}

/**
 * How the rollout tools reach the outside world: every AWS, GitHub, git, and
 * CDK command goes through one of these, so tests substitute scripted results
 * and no test can reach an account or a repository's settings.
 */
export interface Shell {
  /** Run *invocation* to completion and return what it printed. */
  capture(invocation: Invocation): Completed;
  /**
   * Run *invocation* attached to this process's terminal, so a human can
   * answer its prompts and a secret can be piped to it without passing
   * through this process. Returns its exit status.
   */
  attach(invocation: Invocation): number;
}

export const systemShell: Shell = {
  capture: ({ program, args, cwd }) => {
    const result = spawnSync(program, args, { cwd, encoding: "utf8" });
    return { status: result.status ?? 1, stdout: result.stdout, stderr: result.stderr };
  },
  attach: ({ program, args, cwd }) =>
    spawnSync(program, args, { cwd, stdio: "inherit" }).status ?? 1,
};

/** A command a tool needed refused, or answered with something unreadable. */
export class CommandError extends Error {
  override readonly name = "CommandError";
}

/** An AWS command by its service and operation, a GitHub call by its method and path. */
function described({ program, args }: Invocation): string {
  return [program, ...args.slice(0, program === "gh" ? 4 : 2)].join(" ");
}

function failure(invocation: Invocation, completed: Completed): CommandError {
  return new CommandError(
    `${described(invocation)} failed: ${completed.stderr.trim().split("\n", 1).join("")}`,
  );
}

/** The JSON *invocation* prints, or `undefined` when it fails saying what *absent* matches. */
export function readJson(shell: Shell, invocation: Invocation, absent?: RegExp): unknown {
  const completed = shell.capture(invocation);
  if (completed.status !== 0) {
    if (absent?.test(completed.stderr) === true) return undefined;
    throw failure(invocation, completed);
  }
  try {
    return JSON.parse(completed.stdout) as unknown;
  } catch {
    throw new CommandError(`${described(invocation)} printed no JSON`);
  }
}

/** Run *invocation*, which must succeed; what it prints is not needed. */
export function succeeded(shell: Shell, invocation: Invocation): void {
  const completed = shell.capture(invocation);
  if (completed.status !== 0) throw failure(invocation, completed);
}

/** The line *invocation* prints, trimmed. */
export function readLine(shell: Shell, invocation: Invocation): string {
  const completed = shell.capture(invocation);
  if (completed.status !== 0) throw failure(invocation, completed);
  return completed.stdout.trim();
}
