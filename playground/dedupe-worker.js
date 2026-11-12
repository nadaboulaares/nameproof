// Runs nameproof in a background thread so the page stays responsive on long lists.
// The list arrives by postMessage and never leaves the browser.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
// Pyodide only runs in module workers, so this loads pyodide.mjs (the module build of the
// pyodide.js pinned in index.html), checked against its Subresource Integrity hash: a
// modified file is refused.
const PYODIDE_MJS_SRI = "sha384-Lp79fMwxa4n2BLtugpUAoQMlbxIdg8iCUiP1r3h7nJLkQjwlXT1JzZTeHVL+f4Dg";

let python = null;

async function boot(wheel) {
  const response = await fetch(PYODIDE + "pyodide.mjs", { integrity: PYODIDE_MJS_SRI, mode: "cors" });
  if (!response.ok) throw new Error(`could not download Python (${response.status})`);
  const source = URL.createObjectURL(new Blob([await response.text()], { type: "text/javascript" }));
  const { loadPyodide } = await import(source);
  const pyodide = await loadPyodide({ indexURL: PYODIDE });
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync(`
import micropip
await micropip.install(${JSON.stringify(wheel)}, deps=False)
from nameproof._playground import find_in_text, inspect_csv
`);
  return {
    inspect: pyodide.globals.get("inspect_csv"),
    find: pyodide.globals.get("find_in_text"),
  };
}

const progress = (done, total) => postMessage({ type: "progress", done, total });

self.onmessage = async ({ data }) => {
  try {
    if (data.type === "boot") {
      python ??= boot(data.wheel);
      await python;
      postMessage({ type: "ready" });
    } else if (data.type === "inspect") {
      const { inspect } = await python;
      postMessage({ type: "columns", ...JSON.parse(inspect(data.text)) });
    } else if (data.type === "find") {
      const { find } = await python;
      // JavaScript undefined becomes Python None (null would become a JsNull object).
      const result = find(data.text, data.plain, data.column ?? undefined, progress);
      postMessage({ type: "result", ...JSON.parse(result) });
    }
  } catch (error) {
    // Python errors carry a traceback; the last line is the useful message.
    const lines = String(error && error.message ? error.message : error).trim().split("\n");
    postMessage({ type: "error", message: lines[lines.length - 1] });
  }
};
