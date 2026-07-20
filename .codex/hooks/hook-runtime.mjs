import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export const readHookInput = async () => {
  const chunks = [];

  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
};

export const findRepositoryRoot = (cwd) => {
  let currentDirectory = resolve(cwd);

  while (true) {
    if (existsSync(join(currentDirectory, ".git"))) {
      return currentDirectory;
    }

    const parentDirectory = dirname(currentDirectory);

    if (parentDirectory === currentDirectory) {
      throw new Error(`Unable to find repository root from: ${cwd}`);
    }

    currentDirectory = parentDirectory;
  }
};

export const writeHookOutput = (output) => {
  process.stdout.write(JSON.stringify(output));
};
