const fs = require("fs");
const path = require("path");

const dist = path.join(__dirname, "..", "dist");
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });
fs.cpSync(path.join(__dirname, "..", "index.html"), path.join(dist, "index.html"));
fs.cpSync(path.join(__dirname, "..", "src"), path.join(dist, "src"), { recursive: true });
fs.writeFileSync(path.join(dist, "build.json"), JSON.stringify({ ok: true, at: new Date().toISOString() }));
console.log("nova-web build → dist/");
