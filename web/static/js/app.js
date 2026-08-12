(() => {
  const app = document.getElementById("app");
  const bootEl = document.getElementById("boot");
  const toastRoot = document.getElementById("toasts");

  const state = {
    me: null,
    repos: [],
    runs: [],
    repo: null,
    run: null,
    githubRepos: [],
    policy: {},
    workflow: "",
    contract: "",
    stream: null,
  };

  const api = {
    async req(path, opts = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || res.statusText || "Request failed");
      return data;
    },
    me: () => api.req("/api/me"),
    demo: () => api.req("/api/auth/demo", { method: "POST" }),
    github: (token) => api.req("/api/auth/github", { method: "POST", body: { token } }),
    logout: () => api.req("/api/auth", { method: "DELETE" }),
    repos: () => api.req("/api/repos"),
    repo: (id) => api.req(`/api/repos/${id}`),
    addRepo: (full_name) => api.req("/api/repos", { method: "POST", body: { full_name } }),
    delRepo: (id) => api.req(`/api/repos/${id}`, { method: "DELETE" }),
    runRepo: (id) => api.req(`/api/repos/${id}/run`, { method: "POST", body: { trigger: "manual" } }),
    dispatch: (id) => api.req(`/api/repos/${id}/dispatch`, { method: "POST" }),
    runs: (repoId) => api.req(repoId ? `/api/runs?repo_id=${repoId}` : "/api/runs"),
    run: (id) => api.req(`/api/runs/${id}`),
    ghRepos: () => api.req("/api/github/repos"),
    policy: () => api.req("/api/policy"),
    savePolicy: (body) => api.req("/api/policy", { method: "PUT", body }),
    workflow: () => api.req("/api/workflow"),
    contract: () => api.req("/api/contract"),
  };

  function toast(message) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    toastRoot.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function path() {
    return location.pathname.replace(/\/+$/, "") || "/";
  }

  function go(href, replace = false) {
    if (replace) history.replaceState({}, "", href);
    else history.pushState({}, "", href);
    render();
  }

  window.addEventListener("popstate", () => render());
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!a) return;
    const href = a.getAttribute("href");
    if (!href.startsWith("/")) return;
    e.preventDefault();
    go(href);
  });

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function badge(status) {
    const label = (status || "idle").toUpperCase();
    return `<span class="badge ${esc(status || "idle")}">${esc(label)}</span>`;
  }

  function ago(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    const s = Math.max(0, (Date.now() - then) / 1000);
    if (s < 60) return `${Math.floor(s)}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  function brand(compact = false) {
    return `<a class="brand" href="${compact ? "/console" : "/"}">
      <img src="/static/img/mark.svg" alt="" />
      CHAOSGATE
      ${compact ? "" : "<span>RELEASE GATE</span>"}
    </a>`;
  }

  function landing() {
    return `<div class="landing">
      <header class="topbar">
        ${brand()}
        <nav class="top-links">
          <a href="/console/docs">Contract</a>
          <a href="/console">Console</a>
          <a href="/console/connect">Connect GitHub</a>
        </nav>
      </header>
      <section class="hero">
        <div>
          <p class="kicker">Control plane · not a target app</p>
          <h1>The gate<br><em>chaos</em><br>must pass.</h1>
          <p class="lede">
            Bring a real Python, JavaScript, or React repository. ChaosGate pulls it,
            detects the stack, runs unit tests, scans for secrets, boots the app,
            hits it with traffic, and optionally kills a process to see if it recovers.
            PASS opens the merge. FAIL seals <code>main</code>.
          </p>
          <div class="cta-row">
            <button class="btn btn-go" data-act="demo">Launch demo console</button>
            <a class="btn" href="/console/connect">Connect GitHub</a>
          </div>
        </div>
        <aside class="gate-card">
          <div class="gate-head">
            <span>PIPELINE / LIVE PREVIEW</span>
            <span class="lamp"><i></i> ARMED</span>
          </div>
          <div class="stages-mini" id="mini-stages">
            ${["Validate", "Detect", "Unit", "Build", "Security", "Smoke", "Load", "Chaos", "Verdict"]
              .map((name, i) => `<div class="mini-row ${i < 5 ? "on" : ""}">
                <span class="dot ${i < 4 ? "go" : i === 4 ? "hold" : ""}"></span>
                <span>${name}</span>
                <span class="mono">${i < 4 ? "PASS" : i === 4 ? "RUN" : "—"}</span>
              </div>`)
              .join("")}
          </div>
          <div class="metrics-mini">
            <div class="metric"><b>41ms</b><span>p95 latency</span></div>
            <div class="metric"><b>0.0%</b><span>error rate</span></div>
            <div class="metric"><b>0</b><span>secrets</span></div>
          </div>
        </aside>
      </section>
      <section class="strip">
        <article><div class="n">01</div><h3>Contract</h3><p>A chaosgate.yml tells the gate how to start the app, which URLs to hit, and which experiments to run.</p></article>
        <article><div class="n">02</div><h3>Detect</h3><p>Python, Node, React, Docker Compose. Autodetect works. A contract makes runtime tests real.</p></article>
        <article><div class="n">03</div><h3>Prove</h3><p>Unit, build, secret scan, smoke, k6-style traffic, optional process kill. Every stage leaves logs.</p></article>
        <article><div class="n">04</div><h3>Verdict</h3><p>Failed code is not un-pushed. It is kept out of main by a required status check.</p></article>
      </section>
      <footer class="footer-l"><span>GATE PROTOCOL v1</span><span>LOCAL WORKSPACE · DEMO TARGETS IN /samples</span></footer>
    </div>`;
  }

  function shell(inner) {
    const here = path();
    const item = (href, icon, label) => {
      const active = here === href || (href !== "/console" && here.startsWith(href));
      return `<a href="${href}" class="${active ? "active" : ""}"><span class="ico">${icon}</span>${label}</a>`;
    };
    const login = state.me?.workspace?.github_login;
    return `<div class="shell">
      <aside class="side">
        ${brand(true)}
        <nav class="nav">
          ${item("/console", "◎", "Overview")}
          ${item("/console/repos", "▣", "Repositories")}
          ${item("/console/runs", "⚡", "Runs")}
          ${item("/console/connect", "⊕", "Connect")}
          ${item("/console/docs", "▤", "Contract")}
          ${item("/console/settings", "⚙", "Settings")}
        </nav>
        <div class="side-foot">
          ${login ? `GH @${esc(login)}` : "DEMO WORKSPACE"}<br />
          GATE ${state.me?.workspace?.mode === "github" ? "LINKED" : "LOCAL"}
        </div>
      </aside>
      <main class="main">${inner}</main>
    </div>`;
  }

  function overview() {
    const s = state.me?.stats || {};
    const runs = state.me?.recent_runs || [];
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Workspace</p>
          <h1>Overview</h1>
          <p>Three sample targets are already connected. Run the green API, then seal the broken checkout.</p>
        </div>
        <a class="btn btn-go" href="/console/repos">Open repositories</a>
      </div>
      <div class="grid-4" style="margin-bottom:14px">
        <div class="stat"><b>${s.repos ?? 0}</b><span>Connected repos</span></div>
        <div class="stat"><b>${s.runs ?? 0}</b><span>Completed runs</span></div>
        <div class="stat"><b>${s.pass_rate == null ? "—" : s.pass_rate + "%"}</b><span>Pass rate</span></div>
        <div class="stat"><b>${s.blocked ?? 0}</b><span>Blocked releases</span></div>
      </div>
      <div class="grid-2">
        <section class="card">
          <h2>Recent verdicts</h2>
          ${
            runs.length
              ? `<table class="table">
                  <thead><tr><th>Run</th><th>Repo</th><th>Gate</th><th>When</th></tr></thead>
                  <tbody>
                    ${runs
                      .map(
                        (r) => `<tr data-href="/console/runs/${r.id}">
                          <td class="mono">${esc(r.id.slice(0, 14))}</td>
                          <td>${esc(r.repo?.full_name || "")}</td>
                          <td>${badge(r.conclusion || r.status)}</td>
                          <td>${ago(r.created_at)}</td>
                        </tr>`
                      )
                      .join("")}
                  </tbody>
                </table>`
              : `<div class="empty">No runs yet. Open a repository and press Run Gate.</div>`
          }
        </section>
        <section class="card">
          <h2>How the gate decides</h2>
          <p class="help">Unit failures, committed secrets, failed builds, unhealthy smoke, load p95 / error-rate, and failed chaos recovery all seal the merge. Warnings (unpinned deps, missing lockfile) do not, unless you tighten policy.</p>
          <div style="height:14px"></div>
          <a class="btn btn-sm" href="/console/settings">Edit policy</a>
        </section>
      </div>
    `);
  }

  function reposView() {
    const cards = state.repos
      .map(
        (r) => `<article class="repo" data-href="/console/repos/${r.id}">
          <div class="meta">${esc(r.language || "unknown")} ${r.is_sample ? "· SAMPLE TARGET" : ""}</div>
          <h3>${esc(r.full_name)}</h3>
          <p>${esc(r.description || "Connected repository")}</p>
          <div class="repo-foot">${badge(r.last_status)}${r.last_run_at ? `<span class="meta">${ago(r.last_run_at)}</span>` : ""}</div>
        </article>`
      )
      .join("");
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Targets</p>
          <h1>Repositories</h1>
          <p>These are applications under test — not ChaosGate itself.</p>
        </div>
        <a class="btn" href="/console/connect">Connect another</a>
      </div>
      <div class="repo-grid">${cards || `<div class="empty">No repositories connected.</div>`}</div>
    `);
  }

  function repoView() {
    const r = state.repo;
    if (!r) return shell(`<div class="empty">Repository not found.</div>`);
    const runs = r.runs || [];
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">${esc(r.owner)} / ${r.is_sample ? "SAMPLE TARGET" : "CONNECTED"}</p>
          <h1>${esc(r.name)}</h1>
          <p>${esc(r.description || "")} ${r.html_url ? `· <a href="${esc(r.html_url)}" target="_blank" rel="noreferrer">GitHub ↗</a>` : ""}</p>
        </div>
        <div class="cta-row">
          <button class="btn btn-go" data-act="run" data-id="${r.id}">Run Gate</button>
          ${r.html_url ? `<button class="btn" data-act="dispatch" data-id="${r.id}">Dispatch Action</button>` : ""}
          ${r.is_sample ? "" : `<button class="btn" data-act="unlink" data-id="${r.id}">Unlink</button>`}
        </div>
      </div>
      <div class="grid-3" style="margin-bottom:14px">
        <div class="stat"><b>${badge(r.last_status)}</b><span>Last status</span></div>
        <div class="stat"><b>${esc(r.language || "—")}</b><span>Detected language</span></div>
        <div class="stat"><b>${esc(r.default_branch)}</b><span>Branch</span></div>
      </div>
      <section class="card">
        <h2>Run history</h2>
        ${
          runs.length
            ? `<table class="table">
                <thead><tr><th>ID</th><th>Engine</th><th>Verdict</th><th>Summary</th><th>When</th></tr></thead>
                <tbody>
                  ${runs
                    .map(
                      (run) => `<tr data-href="/console/runs/${run.id}">
                        <td class="mono">${esc(run.id)}</td>
                        <td>${esc(run.engine)}</td>
                        <td>${badge(run.conclusion || run.status)}</td>
                        <td>${esc(run.summary || "")}</td>
                        <td>${ago(run.created_at)}</td>
                      </tr>`
                    )
                    .join("")}
                </tbody>
              </table>`
            : `<div class="empty">This target has not been through the gate yet.</div>`
        }
      </section>
    `);
  }

  function runsView() {
    const rows = state.runs
      .map(
        (r) => `<tr data-href="/console/runs/${r.id}">
          <td class="mono">${esc(r.id)}</td>
          <td>${esc(r.repo?.full_name || "")}</td>
          <td>${badge(r.conclusion || r.status)}</td>
          <td>${esc(r.summary || r.status)}</td>
          <td>${ago(r.created_at)}</td>
        </tr>`
      )
      .join("");
    return shell(`
      <div class="page-head">
        <div><p class="kicker">History</p><h1>Runs</h1><p>Every press of Run Gate is recorded with stage logs and a verdict.</p></div>
      </div>
      <section class="card">
        ${
          state.runs.length
            ? `<table class="table"><thead><tr><th>ID</th><th>Repo</th><th>Gate</th><th>Summary</th><th>When</th></tr></thead><tbody>${rows}</tbody></table>`
            : `<div class="empty">No pipeline runs yet.</div>`
        }
      </section>
    `);
  }

  function histogram(values) {
    if (!values || !values.length) return "";
    const max = Math.max(...values, 1);
    return `<div class="bars">${values.map((v) => `<i style="height:${Math.max(4, (v / max) * 56)}px"></i>`).join("")}</div>`;
  }

  function colorize(log) {
    return esc(log)
      .split("\n")
      .map((line) => {
        if (/CRIT|ERROR|failed|FAIL|block:/.test(line)) return `<span class="err">${line}</span>`;
        if (/PASS|passed|OK|Healthy|Recovered/.test(line)) return `<span class="ok">${line}</span>`;
        return line;
      })
      .join("\n");
  }

  function runView() {
    const run = state.run;
    if (!run) return shell(`<div class="empty">Run not found.</div>`);
    const stages = run.stages || [];
    const report = run.report;
    const logs = stages.map((s) => s.logs || "").join("");
    const load = stages.find((s) => s.key === "load");
    const banner = run.conclusion
      ? `<div class="verdict-banner ${esc(run.conclusion)}">
          <div>
            <p class="kicker">${run.conclusion === "PASS" ? "GATE OPEN" : "GATE SEALED"}</p>
            <h2>${esc(run.conclusion)}</h2>
            <p>${esc(run.summary || "")}</p>
          </div>
          <div class="score">${report?.score ?? "—"}</div>
        </div>`
      : `<div class="verdict-banner">
          <div>
            <p class="kicker">Evaluating</p>
            <h2>GATE LIVE</h2>
            <p>Stages are running against <strong>${esc(run.repo?.full_name || "")}</strong>.</p>
          </div>
          ${badge(run.status)}
        </div>`;

    const findings = report?.findings || [];
    return shell(`
      ${banner}
      <div class="page-head">
        <div>
          <p class="kicker">${esc(run.id)} · ${esc(run.engine)} · ${esc(run.branch)}</p>
          <h1>${esc(run.repo?.name || "Run")}</h1>
          <p><a href="/console/repos/${esc(run.repo_id)}">← ${esc(run.repo?.full_name || "repository")}</a></p>
        </div>
        <button class="btn" data-act="run" data-id="${esc(run.repo_id)}">Run again</button>
      </div>
      <div class="run-layout">
        <div class="stage-rail">
          ${stages
            .map(
              (s) => `<div class="stage ${esc(s.status)}">
                <span class="dot ${s.status === "passed" ? "go" : s.status === "failed" ? "stop" : s.status === "running" ? "hold" : ""}"></span>
                <div>${esc(s.name)}<div class="help">${esc(s.summary || s.status)}</div></div>
                <span class="dur">${s.duration_ms != null ? s.duration_ms + "ms" : ""}</span>
              </div>`
            )
            .join("")}
        </div>
        <div>
          <section class="terminal">
            <div class="term-head"><span>Stage recorder</span><span>${esc(run.status)}</span></div>
            <div class="term-body" id="term">${colorize(logs) || "waiting for engine…"}</div>
          </section>
          ${
            load?.metrics?.histogram
              ? `<section class="card" style="margin-top:12px"><h2>Load latency histogram</h2>
                  ${histogram(load.metrics.histogram)}
                  <p class="help">p95 ${load.metrics.p95_ms ?? "—"}ms · ${load.metrics.rps ?? "—"} rps · error ${((load.metrics.error_rate || 0) * 100).toFixed(2)}%</p>
                </section>`
              : ""
          }
          ${
            findings.length
              ? `<section class="card" style="margin-top:12px"><h2>Findings</h2>
                  <div class="find-list">
                    ${findings
                      .map(
                        (f) => `<div class="find ${esc(f.severity)}">
                          <b>${esc(f.title)}</b>
                          <span>${esc(f.detail)}${f.file ? ` · ${esc(f.file)}` : ""}</span>
                        </div>`
                      )
                      .join("")}
                  </div>
                </section>`
              : ""
          }
        </div>
      </div>
    `);
  }

  function connectView() {
    const linked = state.me?.workspace?.connected;
    const rows = (state.githubRepos || [])
      .map(
        (r) => `<div class="gh-row">
          <div><strong>${esc(r.full_name)}</strong><div class="help">${esc(r.language || "n/a")} · ${esc(r.description || "")}</div></div>
          <button class="btn btn-sm" data-act="add" data-name="${esc(r.full_name)}">Connect</button>
        </div>`
      )
      .join("");
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">GitHub</p>
          <h1>Connect</h1>
          <p>MVP auth is a personal access token with <code>repo</code> and <code>workflow</code> scopes. OAuth is the next phase.</p>
        </div>
      </div>
      <div class="grid-2">
        <section class="card">
          <h2>${linked ? "Token connected" : "Paste a token"}</h2>
          <form data-form="github">
            <div class="field">
              <label>GitHub personal access token</label>
              <input name="token" type="password" autocomplete="off" placeholder="ghp_…" />
            </div>
            <button class="btn btn-go" type="submit">Save token</button>
            ${linked ? ` <button class="btn" type="button" data-act="logout">Disconnect</button>` : ""}
          </form>
          <div style="height:22px"></div>
          <h2>Or add any public repo</h2>
          <form data-form="add-repo">
            <div class="field">
              <label>owner/name</label>
              <input name="full_name" placeholder="pallets/flask" />
            </div>
            <button class="btn" type="submit">Connect repository</button>
          </form>
        </section>
        <section class="card">
          <h2>Your GitHub repositories</h2>
          ${
            linked
              ? rows || `<div class="empty">No repositories returned.</div>`
              : `<div class="empty">Connect a token to list your repositories.</div>`
          }
        </section>
      </div>
    `);
  }

  function docsView() {
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Target contract</p>
          <h1>How foreign apps are tested</h1>
          <p>ChaosGate cannot invent a health endpoint. Ship a contract, or accept autodetect with skipped runtime stages.</p>
        </div>
      </div>
      <div class="grid-2">
        <section class="card">
          <h2>chaosgate.yml</h2>
          <pre class="code">${esc(state.contract || "# loading")}</pre>
        </section>
        <section class="card">
          <h2>.github/workflows/chaosgate.yml</h2>
          <p class="help">Copy this into a target repo and mark the ChaosGate check as required on <code>main</code>. Failed PRs cannot merge. Pushed commits are not un-pushed.</p>
          <pre class="code">${esc(state.workflow || "# loading")}</pre>
        </section>
      </div>
    `);
  }

  function settingsView() {
    const p = state.policy || {};
    const row = (key, label, hint) => `<div class="check">
      <div><b>${label}</b><div class="help">${hint}</div></div>
      <button class="toggle ${p[key] ? "on" : ""}" data-act="toggle" data-key="${key}" type="button"><i></i></button>
    </div>`;
    return shell(`
      <div class="page-head">
        <div><p class="kicker">Policy</p><h1>Settings</h1><p>These rules decide whether the gate opens.</p></div>
      </div>
      <div class="grid-2">
        <section class="card">
          <h2>Fail the merge when</h2>
          <div class="checks">
            ${row("fail_on_unit", "Unit tests fail", "pytest / node --test / npm test")}
            ${row("fail_on_build", "Build fails", "compileall, npm run build, Dockerfile")}
            ${row("fail_on_secret", "Secrets are committed", "AWS keys, PATs, Stripe live, private keys")}
            ${row("fail_on_chaos", "Chaos does not recover", "Process kill + restart")}
            ${row("require_config", "chaosgate.yml is missing", "Off by default so autodetect still works")}
          </div>
        </section>
        <section class="card">
          <h2>Load thresholds</h2>
          <form data-form="policy-num">
            <div class="field">
              <label>Max p95 latency (ms)</label>
              <input name="max_p95_ms" type="number" value="${esc(p.max_p95_ms ?? 800)}" />
            </div>
            <div class="field">
              <label>Max error rate (0–1)</label>
              <input name="max_error_rate" type="number" step="0.01" value="${esc(p.max_error_rate ?? 0.05)}" />
            </div>
            <button class="btn btn-go" type="submit">Save thresholds</button>
          </form>
        </section>
      </div>
    `);
  }

  function parseRoute() {
    const p = path();
    if (p === "/") return { name: "landing" };
    if (p === "/console") return { name: "overview" };
    if (p === "/console/repos") return { name: "repos" };
    if (p === "/console/runs") return { name: "runs" };
    if (p === "/console/connect") return { name: "connect" };
    if (p === "/console/docs") return { name: "docs" };
    if (p === "/console/settings") return { name: "settings" };
    let m = p.match(/^\/console\/repos\/([^/]+)$/);
    if (m) return { name: "repo", id: m[1] };
    m = p.match(/^\/console\/runs\/([^/]+)$/);
    if (m) return { name: "run", id: m[1] };
    return { name: "overview" };
  }

  function stopStream() {
    if (state.stream) {
      state.stream.close();
      state.stream = null;
    }
  }

  function watchRun(id) {
    stopStream();
    const src = new EventSource(`/api/runs/${id}/stream`);
    state.stream = src;
    src.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.kind === "done" || msg.kind === "error") {
        src.close();
        state.stream = null;
        try {
          state.run = (await api.run(id)).run;
          state.me = await api.me();
        } catch (_) {}
        if (parseRoute().name === "run") paint();
        return;
      }
      if (parseRoute().name !== "run" || state.run?.id !== id) return;
      if (msg.kind === "stage" && state.run?.stages) {
        const st = state.run.stages.find((s) => s.key === msg.payload.key);
        if (st) {
          st.status = msg.payload.status;
          if (msg.payload.summary) st.summary = msg.payload.summary;
        }
      }
      if (msg.kind === "log" && state.run?.stages) {
        const st = state.run.stages.find((s) => s.key === msg.payload.key);
        if (st) st.logs = (st.logs || "") + msg.payload.line + "\n";
      }
      paint({ keepScroll: true });
    };
  }

  function paint(opts = {}) {
    const term = document.getElementById("term");
    const stick = opts.keepScroll && term && term.scrollHeight - term.scrollTop - term.clientHeight < 80;
    const route = parseRoute();
    if (route.name === "landing") app.innerHTML = landing();
    else if (route.name === "overview") app.innerHTML = overview();
    else if (route.name === "repos") app.innerHTML = reposView();
    else if (route.name === "repo") app.innerHTML = repoView();
    else if (route.name === "runs") app.innerHTML = runsView();
    else if (route.name === "run") app.innerHTML = runView();
    else if (route.name === "connect") app.innerHTML = connectView();
    else if (route.name === "docs") app.innerHTML = docsView();
    else if (route.name === "settings") app.innerHTML = settingsView();
    bind();
    const next = document.getElementById("term");
    if (next && (stick || !opts.keepScroll)) next.scrollTop = next.scrollHeight;
  }

  function bind() {
    document.querySelectorAll("[data-href]").forEach((el) => {
      el.addEventListener("click", () => go(el.getAttribute("data-href")));
    });
    document.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", () => handleAction(el));
    });
    document.querySelectorAll("form[data-form]").forEach((form) => {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        handleForm(form);
      });
    });
  }

  async function handleAction(el) {
    const act = el.dataset.act;
    try {
      if (act === "demo") {
        await bootDemo();
        return;
      }
      if (act === "run") {
        el.disabled = true;
        const data = await api.runRepo(el.dataset.id);
        go(`/console/runs/${data.run.id}`);
        return;
      }
      if (act === "dispatch") {
        const data = await api.dispatch(el.dataset.id);
        toast(data.message || "Dispatched");
        return;
      }
      if (act === "unlink") {
        await api.delRepo(el.dataset.id);
        toast("Repository unlinked");
        go("/console/repos");
        return;
      }
      if (act === "add") {
        const data = await api.addRepo(el.dataset.name);
        toast(`Connected ${data.repo.full_name}`);
        go(`/console/repos/${data.repo.id}`);
        return;
      }
      if (act === "logout") {
        await api.logout();
        state.githubRepos = [];
        await reload();
        toast("GitHub disconnected");
        paint();
        return;
      }
      if (act === "toggle") {
        const key = el.dataset.key;
        const next = { ...state.policy, [key]: !state.policy[key] };
        state.policy = (await api.savePolicy(next)).policy;
        paint();
      }
    } catch (err) {
      toast(err.message);
      el.disabled = false;
    }
  }

  async function handleForm(form) {
    const kind = form.dataset.form;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      if (kind === "github") {
        await api.github(data.token);
        state.me = await api.me();
        try {
          state.githubRepos = (await api.ghRepos()).repos;
        } catch (err) {
          toast(err.message);
        }
        toast(`Connected as ${state.me.workspace.github_login}`);
        paint();
      }
      if (kind === "add-repo") {
        const res = await api.addRepo(data.full_name);
        toast(`Connected ${res.repo.full_name}`);
        go(`/console/repos/${res.repo.id}`);
      }
      if (kind === "policy-num") {
        state.policy = (
          await api.savePolicy({
            max_p95_ms: Number(data.max_p95_ms),
            max_error_rate: Number(data.max_error_rate),
          })
        ).policy;
        toast("Thresholds saved");
        paint();
      }
    } catch (err) {
      toast(err.message);
    }
  }

  async function bootDemo() {
    bootEl.classList.remove("hidden");
    await api.demo();
    await reload();
    await new Promise((r) => setTimeout(r, 1100));
    bootEl.classList.add("hidden");
    go("/console");
  }

  async function reload() {
    state.me = await api.me();
    const route = parseRoute();
    if (route.name !== "landing") {
      state.repos = (await api.repos()).repos;
    }
  }

  async function render() {
    const route = parseRoute();
    if (route.name !== "run") stopStream();
    try {
      if (!state.me) state.me = await api.me();
      if (route.name === "landing") {
        paint();
        return;
      }
      if (route.name === "overview") {
        state.me = await api.me();
        state.repos = (await api.repos()).repos;
      } else if (route.name === "repos") {
        state.repos = (await api.repos()).repos;
      } else if (route.name === "repo") {
        state.repo = (await api.repo(route.id)).repo;
      } else if (route.name === "runs") {
        state.runs = (await api.runs()).runs;
      } else if (route.name === "run") {
        state.run = (await api.run(route.id)).run;
        if (state.run && (state.run.status === "queued" || state.run.status === "running")) {
          watchRun(state.run.id);
        }
      } else if (route.name === "connect") {
        if (state.me?.workspace?.connected) {
          try {
            state.githubRepos = (await api.ghRepos()).repos;
          } catch (_) {}
        }
      } else if (route.name === "docs") {
        state.workflow = (await api.workflow()).content;
        state.contract = (await api.contract()).content;
      } else if (route.name === "settings") {
        state.policy = (await api.policy()).policy;
      }
      paint();
    } catch (err) {
      app.innerHTML = `<div class="main"><div class="empty">${esc(err.message)}</div></div>`;
    }
  }

  render();
})();
