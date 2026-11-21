// Run one action of a connected project for Jarvis (see src/jarvis/projects.py).
//
// Reads {"project", "root", "action", "payload"} as JSON on stdin, loads the
// project's adapter from this folder, and writes one line of JSON to stdout:
// {"ok": true, "result": ...} or {"ok": false, "error": {"kind", "message"}}.
// Anything the project itself prints goes to stderr, so it cannot corrupt the
// reply.
//
// JARVIS_PROJECTS_FETCH_FIXTURES is for tests only: it names a JSON file of
// {"<URL prefix>": {"status": 200, "body": <JSON>}} and replaces fetch() so no
// request leaves the machine; a URL without a fixture fails.
import { readFileSync } from "node:fs";
import { NodeTooOld } from "./hooks.mjs";

const ADAPTERS = {
  "tax-break": "./tax-break.mjs",
  "Portfolio-Watcher": "./portfolio-watcher.mjs",
  OpenTrading: "./opentrading.mjs",
  "5-Mins": "./five-mins.mjs",
  workout: "./workout.mjs",
};

const writeStdout = process.stdout.write.bind(process.stdout);
for (const method of ["log", "info", "debug", "warn", "error", "trace", "dir", "table"]) {
  console[method] = (...args) => process.stderr.write(`${args.map(String).join(" ")}\n`);
}

function finish(body, code) {
  writeStdout(`${JSON.stringify(body)}\n`, () => process.exit(code));
}

function useFetchFixtures(path) {
  const fixtures = Object.entries(JSON.parse(readFileSync(path, "utf8"))).sort(
    ([a], [b]) => b.length - a.length,
  );
  globalThis.fetch = async (input) => {
    const url = String(input instanceof Request ? input.url : input);
    const match = fixtures.find(([prefix]) => url.startsWith(prefix));
    if (!match) throw new TypeError(`no fetch fixture for ${url}`);
    const { status = 200, body = null } = match[1];
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
}

async function main() {
  let request;
  try {
    request = JSON.parse(readFileSync(0, "utf8"));
  } catch (error) {
    return finish({ ok: false, error: { kind: "bad-request", message: `unreadable request: ${error.message}` } }, 2);
  }
  const { project, root, action, payload } = request ?? {};
  if (!Object.hasOwn(ADAPTERS, project) || typeof root !== "string" || typeof action !== "string") {
    return finish({ ok: false, error: { kind: "bad-request", message: "unknown project or malformed request" } }, 2);
  }
  if (process.env.JARVIS_PROJECTS_FETCH_FIXTURES) useFetchFixtures(process.env.JARVIS_PROJECTS_FETCH_FIXTURES);
  try {
    const { default: setup } = await import(ADAPTERS[project]);
    const actions = await setup(root);
    if (action === "ping") return finish({ ok: true, result: { node: process.version } }, 0);
    if (!Object.hasOwn(actions, action)) {
      return finish({ ok: false, error: { kind: "bad-request", message: `${project} has no action ${action}` } }, 2);
    }
    const result = await actions[action](payload ?? {});
    return finish({ ok: true, result: result ?? null }, 0);
  } catch (error) {
    const kind = error instanceof NodeTooOld ? "node-too-old" : "failed";
    process.stderr.write(`${error?.stack ?? error}\n`);
    return finish({ ok: false, error: { kind, message: String(error?.message ?? error) } }, 1);
  }
}

await main();
