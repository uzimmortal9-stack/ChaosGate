const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("storefront ships an index document", () => {
  const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");
  assert.match(html, /Nova Storefront/);
  assert.match(html, /health/);
});

test("catalog source lists products", () => {
  const js = fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8");
  assert.match(js, /Field jacket/);
});
