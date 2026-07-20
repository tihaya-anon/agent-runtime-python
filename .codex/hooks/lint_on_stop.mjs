import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { findRepositoryRoot, readHookInput, writeHookOutput } from "./hook-runtime.mjs";

const maxFailureOutputLength = 4000;
const maxLintOutputBuffer = 8 * 1024 * 1024;

const getBasedPyrightInvocation = (repositoryRoot) => {
  const localBasedPyright = join(repositoryRoot, ".venv", "bin", "basedpyright");
  const localWindowsBasedPyright = join(
    repositoryRoot,
    ".venv",
    "Scripts",
    "basedpyright.exe",
  );

  if (existsSync(localBasedPyright)) {
    return { command: localBasedPyright, args: [] };
  }

  if (existsSync(localWindowsBasedPyright)) {
    return { command: localWindowsBasedPyright, args: [] };
  }

  return { command: "uv", args: ["run", "--no-sync", "basedpyright"] };
};

const getFailureReason = (result) => {
  const output = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
  const detail = output.slice(-maxFailureOutputLength);

  return detail.length > 0
    ? `BasedPyright failed. Fix the reported issues before stopping.\n\n${detail}`
    : "BasedPyright failed without output. Run uv run --no-sync basedpyright and fix the reported issues before stopping.";
};

const main = async () => {
  const input = await readHookInput();

  if (input.hook_event_name !== "Stop" || input.stop_hook_active === true) {
    writeHookOutput({});
    return;
  }

  const repositoryRoot = findRepositoryRoot(
    typeof input.cwd === "string" ? input.cwd : process.cwd(),
  );
  const basedPyright = getBasedPyrightInvocation(repositoryRoot);
  const result = spawnSync(basedPyright.command, basedPyright.args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    maxBuffer: maxLintOutputBuffer,
  });

  if (result.status === 0) {
    writeHookOutput({});
    return;
  }

  writeHookOutput({
    decision: "block",
    reason:
      result.error && result.status === null
        ? `Unable to complete BasedPyright: ${result.error.message}\n\n${getFailureReason(result)}`
        : getFailureReason(result),
  });
};

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);

  writeHookOutput({
    decision: "block",
    reason: `Unable to run BasedPyright before stopping: ${message}`,
  });
});
