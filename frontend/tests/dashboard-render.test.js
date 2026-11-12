import test from "node:test";
import assert from "node:assert/strict";
import {transformSync} from "esbuild";
import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import path from "node:path";
import vm from "node:vm";
import React from "react";
import {renderToString} from "react-dom/server";

test("dashboard and child components render with the classic JSX transform", () => {
  // Reproduce the transform that needs an explicit React binding in every JSX module.
  const require = createRequire(import.meta.url);
  const cache = new Map();
  const load = (filename) => {
    if (cache.has(filename)) return cache.get(filename).exports;
    const module = {exports:{}};
    cache.set(filename, module);
    const result = transformSync(readFileSync(filename, "utf8"), {
      loader:path.extname(filename) === ".jsx" ? "jsx" : "js", format:"cjs",
      jsx:"transform", jsxFactory:"React.createElement", jsxFragment:"React.Fragment",
      define:{"import.meta.env":"{}"}, sourcefile:filename,
    });
    vm.runInNewContext(result.code, {
      module, exports:module.exports,
      require:(specifier) => specifier.startsWith(".") ? load(path.resolve(path.dirname(filename), specifier)) : require(specifier),
      URL, console, setTimeout, clearTimeout,
    }, {filename});
    return module.exports;
  };
  const Dashboard = load(fileURLToPath(new URL("../src/components/DesktopDashboard.jsx", import.meta.url))).default;
  const html = renderToString(React.createElement(Dashboard, {
    status:"idle", transcript:"", induText:"", error:"", wakeText:"Ready",
    onVoiceToggle() {}, voiceActive:false, pendingAction:null, clearPendingAction() {},
  }));
  assert.match(html, /Your day/);
  assert.match(html, /Hey Indu/);
  assert.match(html, /Conversation/);
  assert.match(html, /Open WhatsApp Web to link/);
  const Preview = load(fileURLToPath(new URL("../src/components/MessagePreview.jsx", import.meta.url))).default;
  const previewHtml = renderToString(React.createElement(Preview, {
    preview:{id:"offline-preview", recipient:"Test Contact", phone:"919000000001", message:"Preview only."},
    onComplete() {}, onCancel() {},
  }));
  assert.match(previewHtml, /Test Contact/);
  assert.match(previewHtml, /Preview only/);
});
