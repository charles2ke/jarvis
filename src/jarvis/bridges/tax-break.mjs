// tax-break (https://github.com/charles2ke/tax-break) keeps its tax rules in a
// TypeScript engine under packages/tax-engine, and its web client lists the
// countries the app offers in client/src/countries.ts. This adapter imports
// both and hands Jarvis's requests to the engine's exported functions; every
// figure in a result comes from the project.
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { registerProjectHooks } from "./hooks.mjs";

const load = (root, file) => import(pathToFileURL(join(root, file)).href);

// JSON has no Infinity, so Jarvis writes "max" for a deduction claimed in full;
// as an unlimited claim it is held to the engine's own limit.
const unlimited = (input) =>
  JSON.parse(JSON.stringify(input), (_key, value) => (value === "max" ? Infinity : value));

function inputs(payload) {
  const list = payload?.inputs;
  if (!Array.isArray(list) || list.length === 0) throw new Error("expected a list of inputs");
  return list;
}

export default async function setup(root) {
  registerProjectHooks(root);
  const engine = await load(root, "packages/tax-engine/src/index.ts");
  return {
    async meta() {
      const { COUNTRY_OPTIONS } = await load(root, "client/src/countries.ts");
      return {
        years: engine.listAssessmentYears().map((key) => ({ key, label: engine.getConfig(key).label })),
        states: engine.listUsStates().map(({ code, name }) => ({ code, name })),
        countries: COUNTRY_OPTIONS.map(({ value, tagline }) => ({ value, tagline })),
      };
    },
    india(payload) {
      return inputs(payload).map((input) => engine.compareRegimes(unlimited(input)));
    },
    international(payload) {
      return inputs(payload).map((input) => engine.calculateInternationalTax(input));
    },
  };
}
