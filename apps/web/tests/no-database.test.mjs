import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const dependencyNames = Object.keys({
  ...packageJson.dependencies,
  ...packageJson.devDependencies,
});

assert.equal(dependencyNames.includes("pg"), false);
assert.equal(dependencyNames.includes("postgres"), false);
assert.equal(dependencyNames.some((name) => name.includes("sqlalchemy")), false);

function files(dir) {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (entry === "node_modules" || entry === ".next") return [];
    if (statSync(path).isDirectory()) return files(path);
    return [path];
  });
}

const source = ["app", "lib", "package.json", "next.config.ts"].flatMap((entry) => {
  const path = join(root, entry);
  return statSync(path).isDirectory() ? files(path) : [path];
});

for (const path of source) {
  const text = readFileSync(path, "utf8");
  assert.equal(text.includes("postgres://"), false, path);
  assert.equal(text.includes("DATABASE_URL"), false, path);
}
