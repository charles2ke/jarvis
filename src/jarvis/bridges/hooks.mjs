// Load charles2ke's TypeScript projects straight from their sources.
//
// Node.js strips TypeScript types on its own (22.18 and newer), but two things
// in these projects still need help, and these hooks provide them for files
// inside the project being run:
//
// - Imports without an extension ("./config", "../types") are resolved the way
//   TypeScript resolves them: ".ts", then ".js", then "index.ts".
// - Type stripping keeps `import { SomeType } from "./types"` even when
//   SomeType is only an interface, which then fails because nothing by that
//   name exists at run time. The TypeScript compiler drops such names, and so
//   does the load hook here: it keeps only the imported names the target module
//   really exports as values. Nothing else in the source is changed.
import nodeModule from "node:module";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, resolve as resolvePath } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export class NodeTooOld extends Error {}

const isFile = (path) => existsSync(path) && statSync(path).isFile();

function findSource(path) {
  if (/\.[cm]?[jt]s$/.test(path) && isFile(path)) return path;
  const base = path.replace(/\.js$/, "");
  for (const candidate of [`${base}.ts`, `${base}.js`, `${base}/index.ts`, `${base}/index.js`]) {
    if (isFile(candidate)) return candidate;
  }
  return null;
}

const stripComments = (source) =>
  source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:\\])\/\/.*$/gm, "$1");

const valueExports = new Map();

// The names `file` exports as run-time values, following `export * from`.
function exportedValues(file, seen = new Set()) {
  if (valueExports.has(file)) return valueExports.get(file);
  if (seen.has(file)) return new Set();
  seen.add(file);
  const source = stripComments(readFileSync(file, "utf8"));
  const names = new Set();
  const declarations =
    /\bexport\s+(?!declare\b)(?:default\s+)?(?:async\s+)?(?:abstract\s+)?(?:function\s*\*?|class|const|let|var)\s+([A-Za-z_$][\w$]*)/g;
  for (const match of source.matchAll(declarations)) names.add(match[1]);
  for (const match of source.matchAll(/\bexport\s*\{([^}]*)\}/g)) {
    for (const part of match[1].split(",")) {
      const spec = part.trim();
      if (spec && !spec.startsWith("type ")) names.add(spec.split(/\s+as\s+/).pop().trim());
    }
  }
  for (const match of source.matchAll(/\bexport\s+\*\s+as\s+([A-Za-z_$][\w$]*)/g)) names.add(match[1]);
  for (const match of source.matchAll(/\bexport\s+\*\s+from\s*(['"])([^'"]+)\1/g)) {
    const target = match[2].startsWith(".") ? findSource(resolvePath(dirname(file), match[2])) : null;
    if (target) for (const name of exportedValues(target, seen)) names.add(name);
  }
  if (/\bexport\s+default\b/.test(source)) names.add("default");
  valueExports.set(file, names);
  return names;
}

function dropTypeOnlyImports(source, file) {
  return source.replace(
    /\bimport\s*\{([^}]*)\}\s*from\s*(['"])(\.[^'"]*)\2\s*;?/g,
    (statement, list, quote, specifier) => {
      const target = findSource(resolvePath(dirname(file), specifier));
      if (!target) return statement;
      const values = exportedValues(target);
      const kept = list
        .split(",")
        .map((part) => part.trim())
        .filter((spec) => spec && !spec.startsWith("type ") && values.has(spec.split(/\s+as\s+/)[0].trim()));
      // Keep the line count so stack traces still point at the right lines.
      const newlines = "\n".repeat((statement.match(/\n/g) || []).length);
      return kept.length ? `import { ${kept.join(", ")} } from ${quote}${specifier}${quote};${newlines}` : newlines;
    },
  );
}

export function registerProjectHooks(root) {
  if (typeof nodeModule.registerHooks !== "function" || !process.features?.typescript) {
    throw new NodeTooOld(`this is Node.js ${process.version}, which can't run TypeScript directly`);
  }
  const rootUrl = pathToFileURL(root.endsWith("/") ? root : `${root}/`).href;
  nodeModule.registerHooks({
    resolve(specifier, context, nextResolve) {
      const parent = context.parentURL;
      if (parent?.startsWith(rootUrl) && /^\.\.?\//.test(specifier)) {
        const found = findSource(fileURLToPath(new URL(specifier, parent)));
        if (found) return nextResolve(pathToFileURL(found).href, context);
      }
      return nextResolve(specifier, context);
    },
    load(url, context, nextLoad) {
      if (url.startsWith(rootUrl) && url.endsWith(".ts")) {
        const file = fileURLToPath(url);
        const source = dropTypeOnlyImports(readFileSync(file, "utf8"), file);
        return { format: "module-typescript", source, shortCircuit: true };
      }
      return nextLoad(url, context);
    },
  });
}
