// workout (https://github.com/charles2ke/workout) is a static page. Its plan,
// WORKOUT_DATA, lives in workout.js, a browser script that also builds the page
// as it loads, and the script hands the plan to its Jest tests through
// module.exports._test. This adapter reads the plan the same way: it runs the
// script, with the helpers it require()s, in a sandbox where every browser
// object is an inert stand-in, so the page set-up does nothing.
import { readFileSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import vm from "node:vm";

// Any property, call or construction gives back the same do-nothing object.
const inert = new Proxy(function () {}, {
  get: (_target, key) => {
    if (key === Symbol.toPrimitive) return () => "";
    if (key === Symbol.iterator) return function* () {};
    return key === "then" ? undefined : inert;
  },
  set: () => true,
  apply: () => inert,
  construct: () => inert,
  has: () => true,
});

// The script takes its helpers from window.WorkoutCommon and window.WorkoutLog
// when the page has loaded them, and require()s them otherwise.
const NOT_ON_WINDOW = new Set(["WorkoutCommon", "WorkoutLog", "AudioContext", "webkitAudioContext"]);
const windowStub = new Proxy(
  {},
  {
    get: (_target, key) => (typeof key === "symbol" || NOT_ON_WINDOW.has(key) ? undefined : inert),
    set: () => true,
    has: () => true,
  },
);
const storage = { getItem: () => null, setItem() {}, removeItem() {}, clear() {}, key: () => null, length: 0 };
const silent = { log() {}, info() {}, warn() {}, error() {}, debug() {} };

function loadScript(root, name) {
  const top = resolve(root);
  const sandbox = vm.createContext({
    window: windowStub,
    document: inert,
    navigator: inert,
    location: inert,
    history: inert,
    localStorage: storage,
    sessionStorage: storage,
    matchMedia: () => inert,
    setTimeout: () => 0,
    clearTimeout() {},
    setInterval: () => 0,
    clearInterval() {},
    requestAnimationFrame: () => 0,
    console: silent,
  });
  const cache = new Map();
  const load = (file) => {
    if (!file.startsWith(top + sep)) throw new Error(`workout tried to load ${file}, outside the project`);
    if (cache.has(file)) return cache.get(file).exports;
    const module = { exports: {} };
    cache.set(file, module);
    const wrapper = vm.runInContext(`(function (module, exports, require) {${readFileSync(file, "utf8")}\n})`, sandbox, {
      filename: file,
    });
    wrapper(module, module.exports, (specifier) => load(resolve(dirname(file), specifier)));
    return module.exports;
  };
  return load(resolve(top, name));
}

const ENTITIES = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'" };

export default async function setup(root) {
  return {
    program() {
      const { WORKOUT_DATA: days, getTodayDayId } = loadScript(root, "workout.js")._test;
      // 1 January 2024 was a Monday; ask the app which day each weekday shows.
      const week = [0, 1, 2, 3, 4, 5, 6].map((offset) => {
        const id = getTodayDayId(new Date(2024, 0, 1 + offset));
        return days.find((day) => day.id === id);
      });
      const page = readFileSync(resolve(root, "index.html"), "utf8");
      const title = /<title>([^<]*)<\/title>/i.exec(page)?.[1].replace(/&[a-z]+;|&#39;/g, (e) => ENTITIES[e] ?? e).trim();
      return { title: title || null, week };
    },
  };
}
