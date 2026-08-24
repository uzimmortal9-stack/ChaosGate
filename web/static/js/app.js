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
    artifacts: [],
    githubRepos: [],
    ghFilter: "",
    ghLoading: false,
    policy: {},
    workflow: "",
    contract: "",
    observability: null,
    webhooks: [],
    stream: null,
    // editor
    tab: "files",
    tree: null,
    treePath: "",
    open: [],          // [{path, content, original, language, binary}]
    activePath: null,
    status: { files: [], clean: true },
    diff: "",
    diffPath: null,
    pushing: false,
    showRecovery: null,
    selected: null,     // Set of paths, null = all
    strategy: null,
    modal: null,
    busy: false,
  };

  // ------------------------------------------------------------------ api
  const api = {
    async req(path, opts = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
      const text = await res.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { error: text.slice(0, 200) }; }
      if (!res.ok) throw new Error(data.error || res.statusText || "Request failed");
      return data;
    },
    me: () => api.req("/api/me"),
    demo: () => api.req("/api/auth/demo", { method: "POST" }),
    githubPat: (token) => api.req("/api/auth/github", { method: "POST", body: { token } }),
    oauthUrl: () => api.req("/api/auth/github/login?json=1"),
    logout: () => api.req("/api/auth", { method: "DELETE" }),

    repos: () => api.req("/api/repos"),
    repo: (id) => api.req(`/api/repos/${id}`),
    addRepo: (full_name) => api.req("/api/repos", { method: "POST", body: { full_name } }),
    delRepo: (id) => api.req(`/api/repos/${id}`, { method: "DELETE" }),
    patchRepo: (id, body) => api.req(`/api/repos/${id}`, { method: "PATCH", body }),
    runRepo: (id, body = {}) => api.req(`/api/repos/${id}/run`, { method: "POST", body }),
    dispatch: (id) => api.req(`/api/repos/${id}/dispatch`, { method: "POST" }),
    installWorkflow: (id) => api.req(`/api/repos/${id}/workflow`, { method: "POST" }),
    installWebhook: (id) => api.req(`/api/repos/${id}/webhook`, { method: "POST" }),
    ghActions: (id) => api.req(`/api/repos/${id}/actions`),

    runs: (repoId) => api.req(repoId ? `/api/runs?repo_id=${repoId}` : "/api/runs"),
    run: (id) => api.req(`/api/runs/${id}`),
    artifacts: (id) => api.req(`/api/runs/${id}/artifacts`),
    recovery: (id) => api.req(`/api/runs/${id}/recovery`),
    revert: (id) => api.req(`/api/runs/${id}/revert`, { method: "POST" }),
    fileIncident: (id) => api.req(`/api/runs/${id}/incident`, { method: "POST" }),

    ghRepos: (q = "") => api.req(`/api/github/repos${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    policy: () => api.req("/api/policy"),
    savePolicy: (body) => api.req("/api/policy", { method: "PUT", body }),
    workflow: () => api.req("/api/workflow"),
    contract: () => api.req("/api/contract"),
    observability: () => api.req("/api/observability"),
    webhooks: () => api.req("/api/webhooks"),
    capabilities: () => api.req("/api/capabilities?refresh=1"),
    publishDashboard: () => api.req("/api/observability/dashboard/publish", { method: "POST" }),

    // workspace
    openWs: (id, body = {}) => api.req(`/api/repos/${id}/workspace`, { method: "POST", body }),
    wsInfo: (id) => api.req(`/api/repos/${id}/workspace`),
    closeWs: (id) => api.req(`/api/repos/${id}/workspace`, { method: "DELETE" }),
    pullWs: (id) => api.req(`/api/repos/${id}/workspace/pull`, { method: "POST" }),
    files: (id, path = "") => api.req(`/api/repos/${id}/files?path=${encodeURIComponent(path)}`),
    readFile: (id, path) => api.req(`/api/repos/${id}/file?path=${encodeURIComponent(path)}`),
    saveFile: (id, path, content) => api.req(`/api/repos/${id}/file`, { method: "PUT", body: { path, content } }),
    newFile: (id, path, type = "file") => api.req(`/api/repos/${id}/file`, { method: "POST", body: { path, type } }),
    delFile: (id, path) => api.req(`/api/repos/${id}/file?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
    status: (id) => api.req(`/api/repos/${id}/status`),
    diff: (id, path) => api.req(`/api/repos/${id}/diff${path ? `?path=${encodeURIComponent(path)}` : ""}`),
    discard: (id, path) => api.req(`/api/repos/${id}/discard`, { method: "POST", body: { path } }),
    push: (id, body) => api.req(`/api/repos/${id}/push`, { method: "POST", body }),
  };

  // ---------------------------------------------------------------- utils
  function toast(message, kind = "") {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    toastRoot.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");

  function path() { return location.pathname.replace(/\/+$/, "") || "/"; }

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
    if (!href || !href.startsWith("/") || a.target === "_blank") return;
    e.preventDefault();
    go(href);
  });

  function badge(status) {
    const label = (status || "idle").toUpperCase();
    return `<span class="badge ${esc(status || "idle")}">${esc(label)}</span>`;
  }

  function ago(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const s = Math.max(0, (Date.now() - then) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 2592000) return `${Math.floor(s / 86400)}d ago`;
    return new Date(iso).toLocaleDateString();
  }

  function bytes(n) {
    if (n == null) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1048576).toFixed(1)} MB`;
  }

  function dur(ms) {
    if (ms == null) return "";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  const LANG_COLORS = {
    Python: "#3572A5", JavaScript: "#f1e05a", TypeScript: "#3178c6", Go: "#00ADD8",
    Rust: "#dea584", Java: "#b07219", Ruby: "#701516", PHP: "#4F5D95",
    "C++": "#f34b7d", C: "#555555", Shell: "#89e051", HTML: "#e34c26", CSS: "#563d7c",
  };

  function brand(compact = false) {
    return `<a class="brand" href="${compact ? "/console" : "/"}">
      <img src="/static/img/mark.svg" alt="" />
      CHAOSGATE
      ${compact ? "" : "<span>RELEASE GATE</span>"}
    </a>`;
  }

  // ------------------------------------------------------------- landing
  function landing() {
    const caps = state.me?.capabilities || {};
    const tools = state.me?.toolchain || {};
    const chips = Object.entries(tools).map(([name, t]) =>
      `<span class="pill ${t.available ? "go" : "dim"}">${t.available ? "●" : "○"} ${esc(name)}</span>`
    ).join("");

    return `<div class="landing">
      <header class="topbar">
        ${brand()}
        <nav class="top-links">
          <a href="/console/docs">Contract</a>
          <a href="/console/observability">Observability</a>
          <a href="/console">Console</a>
          <a href="/console/connect">Connect GitHub</a>
        </nav>
      </header>
      <section class="hero">
        <div>
          <p class="kicker">Control plane · not a target app</p>
          <h1>The gate<br><em>chaos</em><br>must pass.</h1>
          <p class="lede">
            Connect GitHub, pick a repository, open its folder right here and edit it.
            Push, and the pipeline fires: unit tests, secret scan, a real container build,
            Kubernetes validation, k6 load, Prometheus metrics, a chaos kill, and a Grafana
            dashboard. PASS opens the merge. FAIL seals <code>main</code>.
          </p>
          <div class="cta-row">
            <button class="btn btn-go" data-act="demo">Launch demo console</button>
            <a class="btn" href="/console/connect">Connect GitHub</a>
          </div>
          <div class="row wrap" style="margin-top:20px;gap:6px">${chips}</div>
        </div>
        <aside class="gate-card">
          <div class="gate-head">
            <span>PIPELINE / 13 STAGES</span>
            <span class="lamp"><i></i> ARMED</span>
          </div>
          <div class="stages-mini">
            ${["Validate","Detect","Unit","Build","Security","Docker","Kubernetes","Smoke","k6 Load","Prometheus","Chaos","Grafana","Verdict"]
              .map((name, i) => `<div class="mini-row ${i < 7 ? "on" : ""}">
                <span class="dot ${i < 6 ? "go" : i === 6 ? "hold" : ""}"></span>
                <span>${name}</span>
                <span class="mono">${i < 6 ? "PASS" : i === 6 ? "RUN" : "—"}</span>
              </div>`).join("")}
          </div>
          <div class="metrics-mini">
            <div class="metric"><b>${caps.real_k6 ? "k6" : "built-in"}</b><span>load engine</span></div>
            <div class="metric"><b>${caps.container_builds ? "live" : "audit"}</b><span>docker</span></div>
            <div class="metric"><b>20</b><span>grafana panels</span></div>
          </div>
        </aside>
      </section>
      <section class="strip">
        <article><div class="n">01</div><h3>Connect</h3><p>OAuth or a personal access token. Browse every repository you can push to, then select one.</p></article>
        <article><div class="n">02</div><h3>Edit</h3><p>The repo is cloned into a local workspace. Open the folder, edit files, review the diff.</p></article>
        <article><div class="n">03</div><h3>Push</h3><p>Commit to a branch, open a pull request, and the gate starts automatically.</p></article>
        <article><div class="n">04</div><h3>Prove</h3><p>k6, Docker, Kubernetes, Prometheus, Grafana and a chaos experiment decide the verdict.</p></article>
      </section>
      <footer class="footer-l"><span>GATE PROTOCOL v2</span><span>LOCAL WORKSPACE · REAL TOOLS WHEN PRESENT · HONEST WHEN NOT</span></footer>
    </div>`;
  }

  function shell(inner) {
    const here = path();
    const item = (href, icon, label, exact = false) => {
      const active = exact ? here === href : here === href || (href !== "/console" && here.startsWith(href));
      return `<a href="${href}" class="${active ? "active" : ""}"><span class="ico">${icon}</span>${label}</a>`;
    };
    const login = state.me?.workspace?.github_login;
    const caps = state.me?.capabilities || {};
    const degraded = Object.values(state.me?.toolchain || {}).filter((t) => !t.available).length;
    return `<div class="shell">
      <aside class="side">
        ${brand(true)}
        <nav class="nav">
          ${item("/console", "◎", "Overview", true)}
          ${item("/console/repos", "▣", "Repositories")}
          ${item("/console/runs", "⚡", "Runs")}
          ${item("/console/observability", "◈", "Observability")}
          ${item("/console/connect", "⊕", "Connect")}
          ${item("/console/docs", "▤", "Contract")}
          ${item("/console/settings", "⚙", "Settings")}
        </nav>
        <div class="side-foot">
          ${login ? `GH @${esc(login)}` : "DEMO WORKSPACE"}<br />
          GATE ${state.me?.workspace?.connected ? "LINKED" : "LOCAL"}<br />
          ${degraded ? `${degraded} TOOL${degraded > 1 ? "S" : ""} DEGRADED` : "ALL TOOLS READY"}
        </div>
      </aside>
      <main class="main">${inner}</main>
    </div>`;
  }

  // ------------------------------------------------------------ overview
  function overview() {
    const s = state.me?.stats || {};
    const runs = state.me?.recent_runs || [];
    const pushes = state.me?.recent_pushes || [];
    const tools = state.me?.toolchain || {};

    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Workspace</p>
          <h1>Overview</h1>
          <p>Connect a repository, edit it here, push, and watch the gate decide.</p>
        </div>
        <div class="cta-row">
          <a class="btn" href="/console/connect">Connect GitHub</a>
          <a class="btn btn-go" href="/console/repos">Repositories</a>
        </div>
      </div>
      <div class="grid-4" style="margin-bottom:14px">
        <div class="stat"><b>${s.repos ?? 0}</b><span>Connected repos</span></div>
        <div class="stat"><b>${s.runs ?? 0}</b><span>Completed runs</span></div>
        <div class="stat"><b>${s.pass_rate == null ? "—" : s.pass_rate + "%"}</b><span>Pass rate</span></div>
        <div class="stat"><b>${s.pushes ?? 0}</b><span>Pushes from editor</span></div>
      </div>

      <section class="card" style="margin-bottom:14px">
        <h2>Toolchain</h2>
        <p class="help">Stages run for real where the tool exists, and degrade honestly where it does not.</p>
        <div class="obs-grid" style="margin-top:12px">
          ${Object.entries(tools).map(([name, t]) => `
            <div class="tool-card ${t.available ? "ready" : "down"}">
              <h4>${esc(name)}</h4>
              <div class="tv">${t.available ? esc(t.version || "ready") : "DEGRADED"}</div>
              <p>${esc(t.detail || "")}</p>
            </div>`).join("")}
        </div>
      </section>

      <div class="grid-2">
        <section class="card">
          <h2>Recent verdicts</h2>
          ${runs.length ? `<table class="table">
            <thead><tr><th>Repo</th><th>Trigger</th><th>Gate</th><th>Score</th><th>When</th></tr></thead>
            <tbody>${runs.map((r) => `<tr data-href="/console/runs/${r.id}">
              <td>${esc(r.repo?.full_name || "")}</td>
              <td class="mono tiny">${esc(r.trigger)}</td>
              <td>${badge(r.conclusion || r.status)}</td>
              <td class="mono">${r.score ?? "—"}</td>
              <td>${ago(r.created_at)}</td>
            </tr>`).join("")}</tbody></table>`
            : `<div class="empty">No runs yet. Open a repository and press Run Gate.</div>`}
        </section>
        <section class="card">
          <h2>Recent pushes</h2>
          ${pushes.length ? `<table class="table">
            <thead><tr><th>Branch</th><th>Message</th><th>Files</th><th>When</th></tr></thead>
            <tbody>${pushes.map((p) => `<tr ${p.run_id ? `data-href="/console/runs/${p.run_id}"` : ""}>
              <td class="mono tiny">${esc(p.branch)}</td>
              <td>${esc((p.message || "").slice(0, 40))}</td>
              <td class="mono">${p.file_count}</td>
              <td>${ago(p.created_at)}</td>
            </tr>`).join("")}</tbody></table>`
            : `<div class="empty">Nothing pushed yet. Open a repo's <b>Editor</b> tab to make a change.</div>`}
        </section>
      </div>
    `);
  }

  // ----------------------------------------------------------- repo list
  function reposView() {
    const cards = state.repos.map((r) => `
      <article class="repo" data-href="/console/repos/${r.id}">
        <div class="meta">
          ${esc(r.language || "unknown")}
          ${r.is_sample ? "· SAMPLE TARGET" : r.private ? "· PRIVATE" : ""}
          ${r.workspace_cloned ? "· WORKSPACE OPEN" : ""}
        </div>
        <h3>${esc(r.full_name)}</h3>
        <p>${esc(r.description || "Connected repository")}</p>
        <div class="repo-foot">
          ${badge(r.last_status)}
          ${r.last_run_at ? `<span class="meta">${ago(r.last_run_at)}</span>` : ""}
        </div>
      </article>`).join("");

    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Targets</p>
          <h1>Repositories</h1>
          <p>These are applications under test — not ChaosGate itself.</p>
        </div>
        <a class="btn btn-go" href="/console/connect">Connect another</a>
      </div>
      <div class="repo-grid">${cards || `<div class="empty">No repositories connected.</div>`}</div>
    `);
  }

  // =========================================================== repo detail
  const TABS = [
    ["overview", "Overview"],
    ["files", "Editor"],
    ["changes", "Changes"],
    ["runs", "Runs"],
    ["automation", "Automation"],
  ];

  function repoView() {
    const r = state.repo;
    if (!r) return shell(`<div class="empty">Repository not found.</div>`);

    const changed = state.status?.files?.length || 0;
    const tabs = TABS.map(([key, label]) => {
      const count = key === "changes" && changed ? `<span class="count">${changed}</span>` : "";
      return `<button data-act="tab" data-tab="${key}" class="${state.tab === key ? "active" : ""}">${label}${count}</button>`;
    }).join("");

    let body = "";
    if (state.tab === "overview") body = repoOverview(r);
    else if (state.tab === "files") body = editorPane(r);
    else if (state.tab === "changes") body = changesPane(r);
    else if (state.tab === "runs") body = repoRuns(r);
    else if (state.tab === "automation") body = automationPane(r);

    const wsOpen = r.workspace_cloned;
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">${esc(r.owner)} / ${r.is_sample ? "SAMPLE TARGET" : r.private ? "PRIVATE" : "CONNECTED"}</p>
          <h1>${esc(r.name)}</h1>
          <p>
            ${esc(r.description || "")}
            ${r.html_url ? ` · <a href="${esc(r.html_url)}" target="_blank" rel="noreferrer">GitHub ↗</a>` : ""}
          </p>
        </div>
        <div class="cta-row">
          <button class="btn btn-go" data-act="run" data-id="${r.id}">Run Gate</button>
          ${!r.is_sample && !wsOpen ? `<button class="btn" data-act="open-ws" data-id="${r.id}">Open folder</button>` : ""}
          ${wsOpen ? `<button class="btn" data-act="pull-ws" data-id="${r.id}">Pull</button>` : ""}
          ${r.is_sample ? "" : `<button class="btn" data-act="unlink" data-id="${r.id}">Unlink</button>`}
        </div>
      </div>
      <div class="row wrap" style="margin-bottom:16px;gap:8px">
        ${badge(r.last_status)}
        <span class="pill">${esc(r.default_branch)}</span>
        ${r.language ? `<span class="pill"><span class="lang-dot" style="background:${LANG_COLORS[r.language] || "#6a7388"}"></span>${esc(r.language)}</span>` : ""}
        ${wsOpen ? `<span class="pill go">workspace ${esc(r.workspace_branch || "")} @ ${esc(r.workspace_sha || "")}</span>` : ""}
        ${changed ? `<span class="pill hold">${changed} uncommitted change${changed > 1 ? "s" : ""}</span>` : ""}
        ${r.workflow_installed ? `<span class="pill go">workflow installed</span>` : ""}
        ${r.webhook_id ? `<span class="pill go">webhook active</span>` : ""}
      </div>
      <div class="tabs">${tabs}</div>
      ${body}
    `);
  }

  function repoOverview(r) {
    const lastRun = (r.runs || [])[0];
    return `
      <div class="grid-2">
        <section class="card">
          <h2>The loop</h2>
          <ol class="step-list" style="margin:12px 0 0;padding:0">
            <li><div><b>Open the folder</b><div class="help">Clones ${esc(r.full_name)} into a local workspace you can edit.</div></div></li>
            <li><div><b>Edit files</b><div class="help">Full text editor with dirty tracking and a diff view.</div></div></li>
            <li><div><b>Push</b><div class="help">Commits to a <code>chaosgate/*</code> branch and opens a pull request.</div></div></li>
            <li><div><b>The gate fires</b><div class="help">13 stages run and the verdict is posted back as a commit status.</div></div></li>
          </ol>
          <div style="height:16px"></div>
          ${r.is_sample
            ? `<div class="banner"><div><b>Sample target</b><p>Bundled samples are read-only fixtures. Connect one of your own GitHub repositories to use the editor and push flow.</p></div></div>`
            : r.workspace_cloned
              ? `<button class="btn btn-go" data-act="tab" data-tab="files">Open the editor →</button>`
              : `<button class="btn btn-go" data-act="open-ws" data-id="${r.id}">Open folder</button>`}
        </section>
        <section class="card">
          <h2>Last verdict</h2>
          ${lastRun ? `
            <div class="verdict-banner ${esc(lastRun.conclusion || "")}" style="margin:8px 0 0">
              <div>
                <p class="kicker">${lastRun.conclusion === "PASS" ? "GATE OPEN" : lastRun.conclusion ? "GATE SEALED" : "IN FLIGHT"}</p>
                <h2>${esc(lastRun.conclusion || lastRun.status)}</h2>
                <p>${esc(lastRun.summary || "")}</p>
              </div>
              <div class="score">${lastRun.score ?? "—"}</div>
            </div>
            <div style="height:12px"></div>
            <a class="btn btn-sm" href="/console/runs/${lastRun.id}">Open run detail</a>`
            : `<div class="empty">This target has not been through the gate yet.</div>`}
        </section>
      </div>`;
  }

  // ------------------------------------------------------------- editor
  const FILE_ICONS = { dir: "▸", py: "◆", js: "◇", json: "▪", yml: "▫", yaml: "▫", md: "▤", default: "·" };
  function fileIcon(entry) {
    if (entry.type === "dir") return "▸";
    const ext = (entry.name.split(".").pop() || "").toLowerCase();
    return FILE_ICONS[ext] || FILE_ICONS.default;
  }

  function editorPane(r) {
    if (r.is_sample) {
      return `<div class="empty">Sample targets are read-only. Connect one of your own repositories to edit and push.</div>`;
    }
    if (!r.workspace_cloned) {
      return `<section class="card">
        <h2>The folder is not open yet</h2>
        <p class="help">ChaosGate clones ${esc(r.full_name)} into a private local workspace. You edit there, then push a branch.</p>
        <div style="height:14px"></div>
        <button class="btn btn-go" data-act="open-ws" data-id="${r.id}">Open folder</button>
      </section>`;
    }

    const tree = state.tree;
    const crumbs = buildCrumbs(state.treePath);
    const rows = (tree?.entries || []).map((e) => {
      const active = state.activePath === e.path;
      return `<div class="filerow ${e.type} ${active ? "active" : ""} ${e.ignored ? "ignored" : ""}"
           data-act="${e.type === "dir" ? "cd" : "open-file"}" data-path="${esc(e.path)}" title="${esc(e.path)}">
        <span class="fi">${fileIcon(e)}</span>
        <span class="fname">${esc(e.name)}</span>
        ${e.dirty ? `<span class="fdot" title="modified"></span>`
          : e.type === "file" ? `<span class="fsize">${bytes(e.size)}</span>` : ""}
      </div>`;
    }).join("");

    const openTabs = state.open.map((f) => {
      const dirty = f.content !== f.original;
      return `<div class="ide-tab ${state.activePath === f.path ? "active" : ""}" data-act="focus-file" data-path="${esc(f.path)}">
        ${dirty ? `<span class="dirty"></span>` : ""}
        <span>${esc(f.path.split("/").pop())}</span>
        <span class="x" data-act="close-file" data-path="${esc(f.path)}">×</span>
      </div>`;
    }).join("");

    const active = state.open.find((f) => f.path === state.activePath);
    let pane;
    if (!active) {
      pane = `<div class="ide-empty">
        <b>No file open</b>
        <span class="help">Pick a file from the tree to start editing.</span>
      </div>`;
    } else if (active.binary) {
      pane = `<div class="ide-empty"><b>Binary file</b><span class="help">${esc(active.path)} · ${bytes(active.size)}</span></div>`;
    } else {
      pane = `<div class="editor-wrap">
        <textarea class="editor" id="editor" spellcheck="false" data-path="${esc(active.path)}">${esc(active.content)}</textarea>
      </div>`;
    }

    const dirtyCount = state.open.filter((f) => f.content !== f.original).length;

    return `<div class="ide">
      <aside class="ide-side">
        <div class="ide-side-head">
          <span>Files</span>
          <span class="ide-side-actions">
            <button class="icon-btn" data-act="new-file" title="New file">＋</button>
            <button class="icon-btn" data-act="refresh-tree" title="Refresh">⟳</button>
          </span>
        </div>
        <div class="crumbs">${crumbs}</div>
        <div class="filelist">${rows || `<div class="filerow"><span class="muted tiny">empty folder</span></div>`}</div>
      </aside>
      <div class="ide-main">
        <div class="ide-tabbar">${openTabs || `<div class="ide-tab muted">no open files</div>`}</div>
        ${pane}
        <div class="ide-status">
          <span>${active ? esc(active.path) : "—"}</span>
          ${active && !active.binary ? `<span>${active.content.split("\n").length} lines</span>` : ""}
          ${active ? `<span>${esc(active.language || "text")}</span>` : ""}
          <span class="spacer"></span>
          ${dirtyCount ? `<span class="pill hold">${dirtyCount} unsaved</span>` : `<span class="muted">saved</span>`}
          ${active && !active.binary ? `<button class="btn btn-sm" data-act="save-file">Save <span class="mono tiny">⌘S</span></button>` : ""}
          ${active ? `<button class="btn btn-sm" data-act="delete-file" data-path="${esc(active.path)}">Delete</button>` : ""}
        </div>
      </div>
    </div>
    <div class="row wrap" style="margin-top:14px">
      <button class="btn btn-go" data-act="tab" data-tab="changes">Review changes & push →</button>
      <span class="muted tiny">Saving writes to the local workspace. Nothing reaches GitHub until you push.</span>
    </div>`;
  }

  function buildCrumbs(p) {
    const parts = (p || "").split("/").filter(Boolean);
    let acc = "";
    const links = [`<a data-act="cd" data-path="">root</a>`];
    for (const part of parts) {
      acc = acc ? `${acc}/${part}` : part;
      links.push(`<span>/</span><a data-act="cd" data-path="${esc(acc)}">${esc(part)}</a>`);
    }
    return links.join("");
  }

  // ------------------------------------------------------------ changes
  function changesPane(r) {
    if (r.is_sample) return `<div class="empty">Sample targets are read-only.</div>`;
    if (!r.workspace_cloned) return `<div class="empty">Open the folder first.</div>`;

    const files = state.status?.files || [];
    if (!files.length) {
      return `<section class="card">
        <h2>Working tree is clean</h2>
        <p class="help">Nothing to push. Edit a file in the <b>Editor</b> tab and it will show up here.</p>
      </section>`;
    }

    const selected = state.selected;
    const isSel = (p) => !selected || selected.has(p);
    const strategy = state.strategy || state.me?.push_strategy || "branch_pr";

    const rows = files.map((f) => `
      <label class="changed-row">
        <input type="checkbox" data-act="sel-file" data-path="${esc(f.path)}" ${isSel(f.path) ? "checked" : ""} />
        <span class="cpath">${esc(f.path)}</span>
        <span class="ctag ${esc(f.status)}">${esc(f.status)}</span>
        <button class="icon-btn" data-act="show-diff" data-path="${esc(f.path)}" title="Diff">◧</button>
        <button class="icon-btn" data-act="discard-file" data-path="${esc(f.path)}" title="Discard">↺</button>
      </label>`).join("");

    const count = files.filter((f) => isSel(f.path)).length;
    const connected = state.me?.workspace?.connected;

    return `<div class="grid-2">
      <section class="card push-panel">
        <h2>${files.length} change${files.length > 1 ? "s" : ""} in the workspace</h2>
        <div class="changed-list">${rows}</div>

        ${!connected ? `<div class="banner stop"><div><b>GitHub is not connected</b><p>Connect GitHub before pushing. <a href="/console/connect">Connect now →</a></p></div></div>` : ""}

        <div>
          <div class="field">
            <label>Commit message</label>
            <textarea class="textarea" id="commit-msg" placeholder="fix: correct the health check timeout">${esc(state.commitMsg || "")}</textarea>
          </div>
          <div class="strategy-grid">
            <div class="strategy ${strategy === "branch_pr" ? "on" : ""}" data-act="strategy" data-value="branch_pr">
              <b>Branch + pull request</b>
              <span>Pushes to <code>chaosgate/&lt;timestamp&gt;</code> and opens a PR against <code>${esc(r.default_branch)}</code>. Recommended.</span>
            </div>
            <div class="strategy ${strategy === "direct" ? "on" : ""}" data-act="strategy" data-value="direct">
              <b>Direct to ${esc(r.default_branch)}</b>
              <span>Commits straight onto the default branch. No review, no PR.</span>
            </div>
          </div>
          <div style="height:12px"></div>
          <label class="row tiny"><input type="checkbox" id="run-gate" checked /> &nbsp;Run the gate immediately after pushing</label>
          <div style="height:14px"></div>
          <button class="btn btn-go" data-act="push" data-id="${r.id}" ${state.pushing || !connected ? "disabled" : ""}>
            ${state.pushing ? "Pushing…" : `Push ${count} file${count === 1 ? "" : "s"} & run gate`}
          </button>
          <button class="btn" data-act="discard-all">Discard all</button>
        </div>
      </section>
      <section class="card">
        <h2>Diff ${state.diffPath ? `<span class="mono tiny muted">${esc(state.diffPath)}</span>` : ""}</h2>
        ${state.diff ? renderDiff(state.diff) : `<div class="empty">Select a file's ◧ icon to see its diff.</div>`}
      </section>
    </div>`;
  }

  function renderDiff(text) {
    const lines = text.split("\n").slice(0, 1200).map((line) => {
      let cls = "";
      if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("new file")) cls = "meta";
      else if (line.startsWith("@@")) cls = "hunk";
      else if (line.startsWith("+")) cls = "add";
      else if (line.startsWith("-")) cls = "del";
      return `<div class="${cls}">${esc(line) || "&nbsp;"}</div>`;
    }).join("");
    return `<div class="diff">${lines}</div>`;
  }

  // --------------------------------------------------------------- runs
  function repoRuns(r) {
    const runs = r.runs || [];
    return `<section class="card">
      <h2>Run history</h2>
      ${runs.length ? `<table class="table">
        <thead><tr><th>ID</th><th>Trigger</th><th>Branch</th><th>Verdict</th><th>Score</th><th>Summary</th><th>When</th></tr></thead>
        <tbody>${runs.map((run) => `<tr data-href="/console/runs/${run.id}">
          <td class="mono tiny">${esc(run.id.slice(0, 12))}</td>
          <td class="mono tiny">${esc(run.trigger)}</td>
          <td class="mono tiny">${esc(run.branch)}</td>
          <td>${badge(run.conclusion || run.status)}</td>
          <td class="mono">${run.score ?? "—"}</td>
          <td>${esc((run.summary || "").slice(0, 60))}</td>
          <td>${ago(run.created_at)}</td>
        </tr>`).join("")}</tbody></table>`
        : `<div class="empty">This target has not been through the gate yet.</div>`}
    </section>`;
  }

  // --------------------------------------------------------- automation
  function automationPane(r) {
    const pushes = r.pushes || [];
    return `<div class="grid-2">
      <section class="card">
        <h2>Trigger the gate from GitHub</h2>
        <p class="help">Two independent paths. Both end in a commit status that can block a merge.</p>
        <div style="height:14px"></div>
        <div class="banner">
          <div>
            <b>1 · GitHub Actions workflow</b>
            <p>Installs <code>.github/workflows/chaosgate.yml</code> so the gate runs on GitHub's runners, where Docker and k6 are available.</p>
          </div>
        </div>
        <button class="btn ${r.workflow_installed ? "" : "btn-go"}" data-act="install-workflow" data-id="${r.id}">
          ${r.workflow_installed ? "Reinstall workflow" : "Install workflow"}
        </button>
        <button class="btn" data-act="dispatch" data-id="${r.id}">Dispatch now</button>
        <div style="height:20px"></div>
        <div class="banner">
          <div>
            <b>2 · Webhook into this control plane</b>
            <p>Every push and pull request calls back here and starts a run locally. Requires a publicly reachable <code>PUBLIC_URL</code>.</p>
          </div>
        </div>
        <button class="btn ${r.webhook_id ? "" : "btn-go"}" data-act="install-webhook" data-id="${r.id}">
          ${r.webhook_id ? "Webhook installed" : "Install webhook"}
        </button>
        <div style="height:18px"></div>
        <label class="row tiny">
          <input type="checkbox" data-act="toggle-autorun" data-id="${r.id}" ${r.auto_run_on_push ? "checked" : ""} />
          &nbsp;Automatically run the gate when a push arrives
        </label>
      </section>
      <section class="card">
        <h2>Pushes from the editor</h2>
        ${pushes.length ? `<table class="table">
          <thead><tr><th>Branch</th><th>Message</th><th>PR</th><th>Run</th><th>When</th></tr></thead>
          <tbody>${pushes.map((p) => `<tr>
            <td class="mono tiny">${esc(p.branch)}</td>
            <td>${esc((p.message || "").slice(0, 34))}</td>
            <td>${p.pr_url ? `<a href="${esc(p.pr_url)}" target="_blank" rel="noreferrer">#${p.pr_number} ↗</a>` : "—"}</td>
            <td>${p.run_id ? `<a href="/console/runs/${p.run_id}">open</a>` : "—"}</td>
            <td>${ago(p.created_at)}</td>
          </tr>`).join("")}</tbody></table>`
          : `<div class="empty">No pushes yet.</div>`}
      </section>
    </div>`;
  }
  // ============================================================ runs list
  function runsView() {
    const rows = state.runs.map((r) => `<tr data-href="/console/runs/${r.id}">
      <td class="mono tiny">${esc(r.id.slice(0, 12))}</td>
      <td>${esc(r.repo?.full_name || "")}</td>
      <td class="mono tiny">${esc(r.trigger)}</td>
      <td>${badge(r.conclusion || r.status)}</td>
      <td class="mono">${r.score ?? "—"}</td>
      <td>${esc((r.summary || r.status).slice(0, 60))}</td>
      <td>${ago(r.created_at)}</td>
    </tr>`).join("");

    return shell(`
      <div class="page-head">
        <div><p class="kicker">History</p><h1>Runs</h1><p>Every gate execution, with stage logs, metrics and artifacts.</p></div>
      </div>
      <section class="card">
        ${state.runs.length
          ? `<table class="table"><thead><tr><th>ID</th><th>Repo</th><th>Trigger</th><th>Gate</th><th>Score</th><th>Summary</th><th>When</th></tr></thead><tbody>${rows}</tbody></table>`
          : `<div class="empty">No pipeline runs yet.</div>`}
      </section>
    `);
  }

  // =========================================================== run detail
  function histogram(values) {
    if (!values || !values.length) return "";
    const max = Math.max(...values, 1);
    return `<div class="sparkbar">${values.map((v) => `<i style="height:${Math.max(2, (v / max) * 40)}px" title="${v}"></i>`).join("")}</div>`;
  }

  function colorize(log) {
    return esc(log).split("\n").map((line) => {
      if (/CRIT|ERROR|failed|FAIL|block:|✗/.test(line)) return `<span class="err">${line}</span>`;
      if (/PASS|passed|OK|Healthy|Recovered|✓|✅/.test(line)) return `<span class="ok">${line}</span>`;
      if (/WARN|degraded|skip/i.test(line)) return `<span style="color:var(--hold)">${line}</span>`;
      return line;
    }).join("\n");
  }

  function stageMetricBlock(stage) {
    const m = stage.metrics || {};
    if (!m || !Object.keys(m).length) return "";

    if (stage.key === "load") {
      return `<div class="grid-4" style="margin-bottom:10px">
        <div class="stat"><b>${m.p95_ms ?? "—"}<span style="font-size:12px">ms</span></b><span>p95 latency</span></div>
        <div class="stat"><b>${((m.error_rate || 0) * 100).toFixed(2)}%</b><span>error rate</span></div>
        <div class="stat"><b>${m.rps ?? "—"}</b><span>requests/sec</span></div>
        <div class="stat"><b>${m.samples ?? "—"}</b><span>samples</span></div>
      </div>
      ${m.histogram?.length ? `<div style="margin:10px 0">${histogram(m.histogram)}<p class="help tiny">latency distribution · engine: ${esc(m.engine || "?")}</p></div>` : ""}
      ${(m.objectives || []).length ? `<table class="metric-table" style="margin-bottom:10px">
        <thead><tr><th>Objective</th><th>Measured</th><th>Threshold</th><th>Result</th></tr></thead>
        <tbody>${m.objectives.map((o) => `<tr>
          <td class="mname">${esc(o.name)}</td>
          <td>${o.measured}${esc(o.unit)}</td>
          <td class="mtype">${esc(o.comparator)} ${o.threshold}${esc(o.unit)}</td>
          <td>${o.passed ? `<span class="pill go">PASS</span>` : `<span class="pill stop">FAIL</span>`}</td>
        </tr>`).join("")}</tbody></table>` : ""}
      <dl class="kv">
        <dt>engine</dt><dd>${esc(m.engine || "—")}</dd>
        <dt>avg / med</dt><dd>${m.avg_ms ?? "—"}ms / ${m.med_ms ?? "—"}ms</dd>
        <dt>p99 / max</dt><dd>${m.p99_ms ?? "—"}ms / ${m.max_ms ?? "—"}ms</dd>
        <dt>thresholds</dt><dd>p95 &lt; ${m.threshold_p95_ms}ms · err &lt; ${((m.threshold_error_rate || 0) * 100).toFixed(1)}%</dd>
        ${m.checks_passed != null ? `<dt>k6 checks</dt><dd>${m.checks_passed} passed / ${m.checks_failed} failed</dd>` : ""}
      </dl>`;
    }

    if (stage.key === "docker") {
      const lint = m.lint || [];
      const b = m.build || {};
      return `${b.tag ? `<dl class="kv" style="margin-bottom:10px">
        <dt>image</dt><dd>${esc(b.tag)}</dd>
        <dt>size</dt><dd>${b.size_mb ? b.size_mb + " MB" : "—"}</dd>
        <dt>layers</dt><dd>${b.layers ?? "—"}</dd>
        <dt>user</dt><dd>${esc(b.user || "root")}</dd>
        <dt>build time</dt><dd>${b.duration_s ?? "—"}s</dd>
      </dl>` : ""}
      ${lint.length ? `<div><b class="tiny">Dockerfile audit</b>${lint.map((f) => `
        <div class="finding-row"><span class="sev ${esc(f.severity)}">${esc(f.severity)}</span>
        <span><b class="mono tiny">${esc(f.rule)}</b><br>${esc(f.detail)}</span></div>`).join("")}</div>` : `<p class="help">Dockerfile audit clean.</p>`}
      ${m.compose ? `<p class="help tiny" style="margin-top:8px">compose services: ${esc((m.compose.services || []).join(", ") || "none")}</p>` : ""}`;
    }

    if (stage.key === "k8s") {
      const audit = m.audit || [];
      return `<dl class="kv" style="margin-bottom:10px">
        <dt>documents</dt><dd>${m.documents ?? 0}</dd>
        <dt>kinds</dt><dd>${esc((m.kinds || []).join(", ") || "—")}</dd>
        ${m.generated ? `<dt>source</dt><dd>generated by ChaosGate (repo had none)</dd>` : ""}
        ${m.dry_run ? `<dt>validation</dt><dd>${esc(m.dry_run.mode)}</dd>` : ""}
      </dl>
      ${audit.length ? audit.slice(0, 24).map((f) => `
        <div class="finding-row"><span class="sev ${esc(f.severity)}">${esc(f.severity)}</span>
        <span><b class="mono tiny">${esc(f.rule)}</b><br>${esc(f.detail)}</span></div>`).join("")
        : `<p class="help">Manifest audit clean.</p>`}`;
    }

    if (stage.key === "prometheus") {
      const e = m.exposition || {};
      return `<dl class="kv">
        <dt>families</dt><dd>${e.families ?? "—"}</dd>
        <dt>samples</dt><dd>${e.samples ?? "—"}</dd>
        <dt>types</dt><dd>${esc(Object.entries(e.by_type || {}).map(([k, v]) => `${v} ${k}`).join(" · ") || "—")}</dd>
        <dt>valid</dt><dd>${e.valid ? "yes" : "no"}</dd>
        ${m.targets?.ok ? `<dt>scrape targets</dt><dd>${m.targets.up}/${m.targets.count} up</dd>` : ""}
        ${m.pushgateway?.pushed ? `<dt>pushgateway</dt><dd>pushed</dd>` : ""}
      </dl>
      ${e.names?.length ? `<details class="stage-detail" style="margin-top:10px"><summary>${e.names.length} metric names</summary><div class="sd-body"><div class="mono tiny">${e.names.map(esc).join("<br>")}</div></div></details>` : ""}`;
    }

    if (stage.key === "chaos") {
      const exps = m.experiments || [];
      return exps.length ? `<table class="metric-table">
        <thead><tr><th>Experiment</th><th>Recovered</th><th>Time</th></tr></thead>
        <tbody>${exps.map((e) => `<tr>
          <td class="mname">${esc(e.experiment)}</td>
          <td>${e.recovered ? `<span class="pill go">yes</span>` : `<span class="pill stop">no</span>`}</td>
          <td>${(e.recovery_s * 1000).toFixed(0)}ms</td>
        </tr>`).join("")}</tbody></table>` : "";
    }

    if (stage.key === "grafana") {
      return `<dl class="kv">
        <dt>panels</dt><dd>${m.panels ?? "—"}</dd>
        <dt>rows</dt><dd>${m.rows ?? "—"}</dd>
        <dt>uid</dt><dd>${esc(m.uid || "—")}</dd>
        <dt>published</dt><dd>${m.publish?.published ? `<a href="${esc(m.publish.url)}" target="_blank" rel="noreferrer">${esc(m.publish.url)} ↗</a>` : esc(m.publish?.reason || "no")}</dd>
      </dl>`;
    }

    if (stage.key === "security") {
      const f = m.findings || [];
      const hist = m.history || {};
      const cve = m.cve || {};
      const chips = [
        hist.scanned ? `<span class="pill">history: ${hist.commits_scanned} commit(s)</span>` : "",
        cve.available === true ? `<span class="pill go">CVE: ${cve.vulnerable ?? 0}/${cve.queried ?? 0} vulnerable</span>` : "",
        cve.available === false ? `<span class="pill hold">CVE scan unavailable</span>` : "",
      ].filter(Boolean).join(" ");
      return `${chips ? `<div class="row wrap" style="margin-bottom:10px;gap:6px">${chips}</div>` : ""}
        ${cve.available === false ? `<div class="banner"><div><b>Dependencies were not checked</b>
          <p>${esc(cve.reason || "the advisory database was unreachable")}. This is not a clean bill of health.</p></div></div>` : ""}
        ${f.length ? f.slice(0, 30).map((x) => `
          <div class="finding-row"><span class="sev ${esc(x.severity)}">${esc(x.severity)}</span>
          <span><b>${esc(x.title)}</b><br><span class="muted tiny">${esc(x.detail)}</span>
          ${x.remediation ? `<br><code class="tiny" style="color:var(--go)">${esc(x.remediation)}</code>` : ""}
          </span></div>`).join("")
          : `<p class="help">No findings.</p>`}`;
    }

    if (stage.key === "detect") {
      return `<dl class="kv">
        <dt>type</dt><dd>${esc(m.type || "—")}</dd>
        <dt>language</dt><dd>${esc(m.language || "—")}</dd>
        <dt>frameworks</dt><dd>${esc((m.frameworks || []).join(", ") || "—")}</dd>
        <dt>test cmd</dt><dd>${esc(m.test_command || "—")}</dd>
        <dt>build cmd</dt><dd>${esc(m.build_command || "—")}</dd>
      </dl>`;
    }

    if (stage.key === "smoke") {
      return `<dl class="kv">
        <dt>url</dt><dd>${esc(m.url || "—")}</dd>
        <dt>status</dt><dd>${m.status ?? "—"}</dd>
        <dt>latency</dt><dd>${m.latency_ms ?? "—"}ms</dd>
        <dt>runtime</dt><dd>${esc(m.engine || "—")}</dd>
      </dl>`;
    }
    return "";
  }

  function recoveryBanner(run) {
    const plan = run.recovery;
    if (!plan) return "";
    const good = plan.last_good;
    const stages = plan.failing_stages || [];
    return `<div class="banner stop" style="border-left-color:var(--stop)">
      <div style="flex:1">
        <b>Already merged — ${esc(plan.branch)} is broken at <code>${esc(plan.bad_commit_short || "?")}</code></b>
        <p>
          This commit is on the default branch, so the pre-merge gate could not stop it.
          ${stages.length ? `Failing: ${stages.map((s) => esc(s.name)).join(", ")}.` : ""}
        </p>
        <p style="margin-top:6px">
          ${good
            ? `Last verified-good commit: <code>${esc(good.short_sha)}</code> (score ${good.score}).`
            : `No earlier passing run is recorded, so there is no verified commit to return to.`}
          Strategy: <b>${esc(plan.strategy)}</b>.
        </p>
        <div class="row wrap" style="margin-top:10px;gap:8px">
          ${plan.strategy === "revert" && !run.reverted_by
            ? `<button class="btn btn-sm btn-stop" data-act="revert-run" data-id="${esc(run.id)}">Open revert PR</button>`
            : ""}
          ${run.reverted_by
            ? `<a class="pill go" href="${esc(run.reverted_by)}" target="_blank" rel="noreferrer">revert opened ↗</a>`
            : ""}
          ${run.incident_url
            ? `<a class="pill" href="${esc(run.incident_url)}" target="_blank" rel="noreferrer">incident #${run.incident_number} ↗</a>`
            : `<button class="btn btn-sm" data-act="file-incident" data-id="${esc(run.id)}">File incident</button>`}
          <button class="btn btn-sm" data-act="show-recovery" data-id="${esc(run.id)}">Show commands</button>
        </div>
        ${state.showRecovery === run.id && (plan.commands || []).length
          ? `<pre class="code" style="margin-top:10px">${esc(plan.commands.join("\n"))}</pre>`
          : ""}
      </div>
    </div>`;
  }

  function runView() {
    const run = state.run;
    if (!run) return shell(`<div class="empty">Run not found.</div>`);
    const stages = run.stages || [];
    const report = run.report;
    const live = run.status === "running" || run.status === "queued";

    const banner = run.conclusion
      ? `<div class="verdict-banner ${esc(run.conclusion)}">
          <div>
            <p class="kicker">${run.conclusion === "PASS" ? "GATE OPEN — MERGE ALLOWED" : "GATE SEALED — MERGE BLOCKED"}</p>
            <h2>${esc(run.conclusion)}</h2>
            <p>${esc(run.summary || "")}</p>
          </div>
          <div class="score">${run.score ?? report?.score ?? "—"}</div>
        </div>`
      : `<div class="verdict-banner">
          <div>
            <p class="kicker">Evaluating</p>
            <h2>GATE LIVE</h2>
            <p>Running against <strong>${esc(run.repo?.full_name || "")}</strong>${run.commit_short ? ` @ <code>${esc(run.commit_short)}</code>` : ""}.</p>
          </div>
          ${badge(run.status)}
        </div>`;

    const reasons = report?.reasons || [];
    const degraded = report?.degraded || [];
    const activeStage = stages.find((s) => s.status === "running");

    return shell(`
      ${banner}
      <div class="page-head">
        <div>
          <p class="kicker">
            ${esc(run.id)} · ${esc(run.trigger)} · ${esc(run.branch)}
            ${run.commit_short ? ` · <span class="mono">${esc(run.commit_short)}</span>` : ""}
            ${run.duration_s ? ` · ${run.duration_s}s` : ""}
          </p>
          <h1>${esc(run.repo?.name || "Run")}</h1>
          <p><a href="/console/repos/${esc(run.repo_id)}">← ${esc(run.repo?.full_name || "repository")}</a>
          ${run.pr_url ? ` · <a href="${esc(run.pr_url)}" target="_blank" rel="noreferrer">PR #${run.pr_number} ↗</a>` : ""}</p>
        </div>
        <button class="btn" data-act="run" data-id="${esc(run.repo_id)}">Run again</button>
      </div>

      ${recoveryBanner(run)}
      ${reasons.length ? `<div class="banner stop"><div><b>${reasons.length} blocking reason${reasons.length > 1 ? "s" : ""}</b>
        <p>${reasons.map(esc).join("<br>")}</p></div></div>` : ""}
      ${degraded.length ? `<div class="banner"><div><b>${degraded.length} stage${degraded.length > 1 ? "s" : ""} ran degraded</b>
        <p>${degraded.map(esc).join("<br>")}</p></div></div>` : ""}

      <div class="run-layout">
        <div class="stage-rail">
          ${stages.map((s) => `<div class="stage ${esc(s.status)}" data-act="focus-stage" data-key="${esc(s.key)}">
            <span class="dot ${s.status === "passed" ? "go" : s.status === "failed" ? "stop" : s.status === "running" ? "hold" : s.status === "degraded" ? "hold" : ""}"></span>
            <div>${esc(s.name)}<div class="help">${esc(s.summary || s.status)}</div></div>
            <span class="dur">${dur(s.duration_ms)}</span>
          </div>`).join("")}
        </div>
        <div>
          <section class="terminal">
            <div class="term-head">
              <span>Stage recorder${activeStage ? ` · ${esc(activeStage.name)}` : ""}</span>
              <span>${esc(run.status)}${live ? " ●" : ""}</span>
            </div>
            <div class="term-body" id="term">${colorize(stages.map((s) => s.logs || "").join("")) || "waiting for engine…"}</div>
          </section>

          ${stages.filter((s) => s.metrics && Object.keys(s.metrics).length && s.key !== "verdict" && s.key !== "validate").map((s) => `
            <details class="stage-detail" ${s.status === "failed" ? "open" : ""}>
              <summary>
                <span class="dot ${s.status === "passed" ? "go" : s.status === "failed" ? "stop" : "hold"}"></span>
                <b>${esc(s.name)}</b>
                <span class="muted tiny">${esc(s.summary || "")}</span>
              </summary>
              <div class="sd-body">${stageMetricBlock(s)}</div>
            </details>`).join("")}

          ${state.artifacts.length ? `<section class="card" style="margin-top:12px">
            <h2>Artifacts</h2>
            <p class="help">Everything the run produced: k6 summary, Grafana dashboard, Prometheus scrape config and alert rules, generated Kubernetes manifests, and the full report.</p>
            <div class="artifact-grid" style="margin-top:12px">
              ${state.artifacts.map((a) => `<a class="artifact" href="${esc(a.url)}?download=1" target="_blank" rel="noreferrer">
                <span>▤</span><span>${esc(a.name)}</span><span class="asize">${bytes(a.size)}</span>
              </a>`).join("")}
            </div>
          </section>` : ""}
        </div>
      </div>
    `);
  }

  // ======================================================= observability
  function observabilityView() {
    const o = state.observability;
    if (!o) return shell(`<div class="empty">Loading observability…</div>`);
    const prom = o.prometheus || {};
    const graf = o.grafana || {};
    const expo = prom.exposition || {};

    const card = (name, tool, extra = "") => `
      <div class="tool-card ${tool?.available ? "ready" : "down"}">
        <h4>${esc(name)}</h4>
        <div class="tv">${tool?.available ? esc(tool.version || "ready") : "DEGRADED"}</div>
        <p>${esc(tool?.detail || "")}</p>
        ${extra}
      </div>`;

    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Metrics & dashboards</p>
          <h1>Observability</h1>
          <p>ChaosGate exports Prometheus metrics about itself and every gate run, and ships a Grafana dashboard built from them.</p>
        </div>
        <div class="cta-row">
          <a class="btn" href="/metrics" target="_blank" rel="noreferrer">Raw /metrics ↗</a>
          <a class="btn" href="/api/observability/dashboard?download=1" target="_blank" rel="noreferrer">Download dashboard</a>
          <button class="btn btn-go" data-act="publish-dashboard">Publish to Grafana</button>
        </div>
      </div>

      <div class="obs-grid" style="margin-bottom:16px">
        ${card("Prometheus", prom.tool)}
        ${card("Grafana", graf.tool)}
        ${card("k6", o.k6)}
        ${card("Docker", o.docker)}
        ${card("Kubernetes", o.kubernetes, `<p class="tiny muted" style="margin-top:6px">namespace: ${esc(o.kubernetes?.namespace || "—")}</p>`)}
      </div>

      <div class="grid-2">
        <section class="card">
          <h2>Exported metrics</h2>
          <p class="help">${expo.families} families · ${expo.samples} samples · exposition ${expo.valid ? "valid" : "INVALID"}</p>
          <div style="height:10px"></div>
          <table class="metric-table">
            <thead><tr><th>Metric</th></tr></thead>
            <tbody>${(expo.names || []).slice(0, 40).map((n) => `<tr><td class="mname">${esc(n)}</td></tr>`).join("")}</tbody>
          </table>
        </section>
        <section class="card">
          <h2>Wire it up</h2>
          <p class="help">Point a Prometheus at this endpoint, then import the dashboard.</p>
          <pre class="code">scrape_configs:
  - job_name: chaosgate
    metrics_path: /metrics
    static_configs:
      - targets: ["chaosgate:5000"]</pre>
          <div style="height:12px"></div>
          <p class="help">Or bring the whole stack up with the bundled compose profile:</p>
          <pre class="code">docker compose --profile observability up -d
# Prometheus  → http://localhost:9090
# Grafana     → http://localhost:3000  (admin / admin)</pre>
          <div style="height:12px"></div>
          <p class="help">The Grafana dashboard is provisioned automatically by that profile — 20 panels covering verdicts, stage timings, k6 latency, chaos recovery, image sizes and toolchain health.</p>
        </section>
      </div>

      <section class="card" style="margin-top:14px">
        <h2>Webhook deliveries</h2>
        <p class="help">Inbound GitHub events and the runs they triggered.</p>
        ${state.webhooks.length ? `<table class="table">
          <thead><tr><th>Event</th><th>Repo</th><th>Branch</th><th>Commit</th><th>Verified</th><th>Result</th><th>When</th></tr></thead>
          <tbody>${state.webhooks.map((w) => `<tr ${w.run_id ? `data-href="/console/runs/${w.run_id}"` : ""}>
            <td class="mono tiny">${esc(w.event)}</td>
            <td>${esc(w.repo || "—")}</td>
            <td class="mono tiny">${esc(w.branch || "—")}</td>
            <td class="mono tiny">${esc(w.sha || "—")}</td>
            <td>${w.verified ? `<span class="pill go">yes</span>` : `<span class="pill dim">no</span>`}</td>
            <td class="tiny">${esc(w.note || "")}</td>
            <td>${ago(w.created_at)}</td>
          </tr>`).join("")}</tbody></table>`
          : `<div class="empty">No webhook deliveries yet. Install a webhook from a repository's Automation tab.</div>`}
      </section>
    `);
  }
  // ============================================================== connect
  function connectView() {
    const ws = state.me?.workspace || {};
    const linked = ws.connected;
    const oauth = state.me?.oauth_enabled;
    const params = new URLSearchParams(location.search);
    const err = params.get("error");

    const filtered = (state.githubRepos || []).filter((r) =>
      !state.ghFilter || r.full_name.toLowerCase().includes(state.ghFilter.toLowerCase())
    );

    const rows = filtered.map((r) => `
      <div class="gh-item">
        <div class="ghmain">
          <strong>${esc(r.full_name)}</strong>
          <div class="ghmeta">
            ${r.language ? `<span><span class="lang-dot" style="background:${LANG_COLORS[r.language] || "#6a7388"}"></span>${esc(r.language)}</span>` : ""}
            ${r.private ? `<span>private</span>` : `<span>public</span>`}
            ${r.pushed_at ? `<span>pushed ${ago(r.pushed_at)}</span>` : ""}
            ${r.permissions?.push === false ? `<span style="color:var(--hold)">read-only</span>` : ""}
          </div>
        </div>
        ${r.connected
          ? `<span class="pill go">connected</span>`
          : `<button class="btn btn-sm btn-go" data-act="add" data-name="${esc(r.full_name)}">Select</button>`}
      </div>`).join("");

    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">GitHub</p>
          <h1>Connect</h1>
          <p>Link your account, then select the repositories the gate should guard.</p>
        </div>
        ${linked ? `<button class="btn" data-act="logout">Disconnect</button>` : ""}
      </div>

      ${err ? `<div class="banner stop"><div><b>Sign-in failed</b><p>${esc(err)}</p></div></div>` : ""}
      ${linked ? `<div class="banner go"><div>
        <b>Connected as @${esc(ws.github_login)}</b>
        <p>${esc(ws.github_name || "")} · auth via ${esc(ws.auth_method || "token")}${ws.scopes?.length ? ` · scopes: ${esc(ws.scopes.join(", "))}` : ""}</p>
      </div></div>` : ""}

      <div class="grid-2">
        <section class="card">
          <h2>${linked ? "Authentication" : "Sign in"}</h2>
          ${oauth
            ? `<p class="help">One click, no token handling. Grants <code>repo</code> and <code>workflow</code>.</p>
               <div style="height:12px"></div>
               <button class="btn btn-go" data-act="oauth">Continue with GitHub</button>
               <div style="height:22px"></div>
               <h2>Or use a token</h2>`
            : `<div class="banner"><div><b>OAuth is not configured</b>
                 <p>Set <code>GITHUB_CLIENT_ID</code> and <code>GITHUB_CLIENT_SECRET</code> in <code>.env</code> to enable one-click sign-in. A personal access token works right now.</p></div></div>`}
          <form data-form="github">
            <div class="field">
              <label>Personal access token <span class="muted tiny">(scopes: repo, workflow)</span></label>
              <input name="token" type="password" autocomplete="off" placeholder="ghp_… or github_pat_…" />
            </div>
            <button class="btn ${oauth ? "" : "btn-go"}" type="submit">Save token</button>
          </form>
          <div style="height:22px"></div>
          <h2>Add a public repo by name</h2>
          <p class="help">No account needed — the gate can test any public repository read-only.</p>
          <form data-form="add-repo">
            <div class="field">
              <label>owner/name</label>
              <input name="full_name" placeholder="pallets/flask" />
            </div>
            <button class="btn" type="submit">Connect repository</button>
          </form>
        </section>

        <section class="card">
          <div class="split-head">
            <h2>Your repositories</h2>
            ${linked ? `<button class="btn btn-sm" data-act="refresh-gh">Refresh</button>` : ""}
          </div>
          ${linked ? `
            <div class="gh-toolbar">
              <input id="gh-filter" placeholder="Filter ${state.githubRepos.length} repositories…" value="${esc(state.ghFilter)}" />
            </div>
            ${state.ghLoading
              ? `<div class="empty">Loading…</div>`
              : rows
                ? `<div class="gh-list">${rows}</div>`
                : `<div class="empty">No repositories match.</div>`}`
            : `<div class="empty">Sign in to list the repositories you can push to.</div>`}
        </section>
      </div>
    `);
  }

  // ================================================================= docs
  function docsView() {
    return shell(`
      <div class="page-head">
        <div>
          <p class="kicker">Target contract</p>
          <h1>How foreign apps are tested</h1>
          <p>ChaosGate cannot invent a health endpoint. Ship a contract, or accept autodetect with reduced runtime stages.</p>
        </div>
      </div>
      <div class="grid-2">
        <section class="card">
          <h2>chaosgate.yml</h2>
          <p class="help">Drop this at the root of the repository under test.</p>
          <pre class="code">${esc(state.contract || "# loading")}</pre>
        </section>
        <section class="card">
          <h2>.github/workflows/chaosgate.yml</h2>
          <p class="help">Copy into a target repo and mark the ChaosGate check as required on <code>main</code>. Failed PRs then cannot merge — pushed commits are not un-pushed, they are kept out of the protected branch.</p>
          <pre class="code">${esc(state.workflow || "# loading")}</pre>
        </section>
      </div>
    `);
  }

  // ============================================================= settings
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
          <h2>Seal the merge when</h2>
          <div class="checks">
            ${row("fail_on_unit", "Unit tests fail", "pytest · node --test · npm test")}
            ${row("fail_on_build", "Build fails", "compileall · npm run build")}
            ${row("fail_on_secret", "Secrets are committed", "AWS keys, PATs, Stripe live keys, private keys")}
            ${row("fail_on_docker", "Container build fails", "docker build, or a critical Dockerfile issue")}
            ${row("fail_on_k8s", "Kubernetes manifests are rejected", "server-side dry-run or a critical audit finding")}
            ${row("fail_on_load", "Load thresholds are exceeded", "k6 p95 and error-rate budgets")}
            ${row("fail_on_chaos", "Chaos does not recover", "process kill + restart")}
            ${row("require_config", "chaosgate.yml is missing", "off by default so autodetect still works")}
            ${row("fail_on_degraded", "A stage runs degraded", "strict mode: fail when Docker/K8s/k6 are unavailable")}
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
              <input name="max_error_rate" type="number" step="0.01" min="0" max="1" value="${esc(p.max_error_rate ?? 0.05)}" />
            </div>
            <button class="btn btn-go" type="submit">Save thresholds</button>
          </form>
          <div style="height:22px"></div>
          <h2>Host toolchain</h2>
          <p class="help">Refresh after installing Docker, kubectl or k6 on this machine.</p>
          <button class="btn btn-sm" data-act="refresh-caps">Re-probe toolchain</button>
        </section>
      </div>
    `);
  }

  // =============================================================== modals
  function modalView() {
    const m = state.modal;
    if (!m) return "";
    if (m.kind === "new-file") {
      return `<div class="modal-back" data-act="close-modal">
        <div class="modal" data-stop="1">
          <div class="modal-head"><h3>New file</h3><button class="icon-btn" data-act="close-modal">×</button></div>
          <div class="modal-body">
            <div class="field">
              <label>Path, relative to the repository root</label>
              <input id="new-file-path" placeholder="${esc(state.treePath ? state.treePath + "/" : "")}notes.md" value="${esc(state.treePath ? state.treePath + "/" : "")}" />
            </div>
            <p class="help tiny">Intermediate folders are created automatically. End with <code>/</code> to make a directory.</p>
          </div>
          <div class="modal-foot">
            <button class="btn" data-act="close-modal">Cancel</button>
            <button class="btn btn-go" data-act="create-file">Create</button>
          </div>
        </div>
      </div>`;
    }
    if (m.kind === "pushed") {
      const pr = m.pull_request;
      return `<div class="modal-back" data-act="close-modal">
        <div class="modal" data-stop="1">
          <div class="modal-head"><h3>Pushed</h3><button class="icon-btn" data-act="close-modal">×</button></div>
          <div class="modal-body">
            <div class="banner go"><div>
              <b>${m.push.file_count} file(s) on <code>${esc(m.push.branch)}</code></b>
              <p>commit <span class="mono">${esc(m.push.short_sha || "")}</span> — ${esc(m.push.message)}</p>
            </div></div>
            ${pr ? `<p>Pull request <a href="${esc(pr.html_url)}" target="_blank" rel="noreferrer">#${pr.number} ↗</a> is open against <code>${esc(m.push.base_branch)}</code>.</p>`
                 : m.pr_error ? `<div class="banner"><div><b>Pull request not opened</b><p>${esc(m.pr_error)}</p></div></div>` : ""}
            ${m.run ? `<p>The gate is running now. The verdict will be posted back to GitHub as a commit status.</p>` : ""}
          </div>
          <div class="modal-foot">
            <button class="btn" data-act="close-modal">Stay here</button>
            ${m.run ? `<button class="btn btn-go" data-act="goto-run" data-id="${esc(m.run.id)}">Watch the gate →</button>` : ""}
          </div>
        </div>
      </div>`;
    }
    return "";
  }

  // ============================================================== routing
  function parseRoute() {
    const p = path();
    if (p === "/") return { name: "landing" };
    if (p === "/console") return { name: "overview" };
    if (p === "/console/repos") return { name: "repos" };
    if (p === "/console/runs") return { name: "runs" };
    if (p === "/console/connect") return { name: "connect" };
    if (p === "/console/docs") return { name: "docs" };
    if (p === "/console/settings") return { name: "settings" };
    if (p === "/console/observability") return { name: "observability" };
    let m = p.match(/^\/console\/repos\/([^/]+)$/);
    if (m) return { name: "repo", id: m[1] };
    m = p.match(/^\/console\/runs\/([^/]+)$/);
    if (m) return { name: "run", id: m[1] };
    return { name: "overview" };
  }

  function stopStream() {
    if (state.stream) { state.stream.close(); state.stream = null; }
  }

  function watchRun(id) {
    stopStream();
    const src = new EventSource(`/api/runs/${id}/stream`);
    state.stream = src;
    src.onerror = () => { /* browser retries automatically */ };
    src.onmessage = async (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.kind === "done" || msg.kind === "error") {
        src.close(); state.stream = null;
        try {
          state.run = (await api.run(id)).run;
          state.artifacts = (await api.artifacts(id)).artifacts || [];
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
          if (msg.payload.metrics && Object.keys(msg.payload.metrics).length) st.metrics = msg.payload.metrics;
          st.degraded = !!msg.payload.degraded;
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
    const stick = opts.keepScroll && term && term.scrollHeight - term.scrollTop - term.clientHeight < 90;

    // preserve editor caret across repaints
    const ed = document.getElementById("editor");
    const caret = ed ? { start: ed.selectionStart, end: ed.selectionEnd, top: ed.scrollTop, path: ed.dataset.path } : null;

    const route = parseRoute();
    const views = {
      landing, overview, repos: reposView, repo: repoView, runs: runsView,
      run: runView, connect: connectView, docs: docsView, settings: settingsView,
      observability: observabilityView,
    };
    app.innerHTML = (views[route.name] || overview)() + modalView();
    bind();

    const next = document.getElementById("term");
    if (next && (stick || !opts.keepScroll)) next.scrollTop = next.scrollHeight;

    const ed2 = document.getElementById("editor");
    if (ed2 && caret && ed2.dataset.path === caret.path) {
      try { ed2.setSelectionRange(caret.start, caret.end); ed2.scrollTop = caret.top; } catch (_) {}
      if (opts.focusEditor) ed2.focus();
    } else if (ed2 && opts.focusEditor) {
      ed2.focus();
    }
  }

  // =============================================================== events
  function bind() {
    document.querySelectorAll("[data-href]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("a,button,input,label")) return;
        go(el.getAttribute("data-href"));
      });
    });
    document.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (el.dataset.act === "close-modal" && e.target.closest("[data-stop]")) return;
        e.stopPropagation();
        handleAction(el, e);
      });
    });
    document.querySelectorAll("form[data-form]").forEach((form) => {
      form.addEventListener("submit", (e) => { e.preventDefault(); handleForm(form); });
    });

    const editor = document.getElementById("editor");
    if (editor) {
      editor.addEventListener("input", () => {
        const f = state.open.find((x) => x.path === editor.dataset.path);
        if (f) {
          f.content = editor.value;
          const tab = [...document.querySelectorAll(".ide-tab")].find((t) => t.textContent.includes(f.path.split("/").pop()));
          if (tab && !tab.querySelector(".dirty") && f.content !== f.original) {
            tab.insertAdjacentHTML("afterbegin", '<span class="dirty"></span>');
          }
        }
      });
      editor.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveActive(); }
        if (e.key === "Tab") {
          e.preventDefault();
          const s = editor.selectionStart, en = editor.selectionEnd;
          editor.value = editor.value.slice(0, s) + "  " + editor.value.slice(en);
          editor.selectionStart = editor.selectionEnd = s + 2;
          editor.dispatchEvent(new Event("input"));
        }
      });
    }

    const filter = document.getElementById("gh-filter");
    if (filter) {
      filter.addEventListener("input", () => {
        state.ghFilter = filter.value;
        const pos = filter.selectionStart;
        paint();
        const f2 = document.getElementById("gh-filter");
        if (f2) { f2.focus(); f2.setSelectionRange(pos, pos); }
      });
    }

    const msg = document.getElementById("commit-msg");
    if (msg) msg.addEventListener("input", () => { state.commitMsg = msg.value; });
  }

  async function saveActive() {
    const f = state.open.find((x) => x.path === state.activePath);
    if (!f || f.binary) return;
    try {
      const res = await api.saveFile(state.repo.id, f.path, f.content);
      f.original = f.content;
      state.status = res.status || state.status;
      await refreshTree();
      toast(`Saved ${f.path}`);
      paint({ focusEditor: true });
    } catch (err) { toast(err.message); }
  }

  async function refreshTree() {
    if (!state.repo?.workspace_cloned) return;
    try { state.tree = await api.files(state.repo.id, state.treePath); } catch (_) {}
  }

  async function handleAction(el, event) {
    const act = el.dataset.act;
    const id = el.dataset.id || state.repo?.id;
    try {
      switch (act) {
        case "demo": return void (await bootDemo());

        case "tab": {
          state.tab = el.dataset.tab;
          if (state.tab === "files" && state.repo?.workspace_cloned && !state.tree) await refreshTree();
          if (state.tab === "changes" && state.repo?.workspace_cloned) {
            state.status = await api.status(state.repo.id);
            const d = await api.diff(state.repo.id);
            state.diff = d.diff; state.diffPath = null;
          }
          return paint();
        }

        case "run": {
          el.disabled = true;
          const data = await api.runRepo(id);
          return go(`/console/runs/${data.run.id}`);
        }

        case "open-ws": {
          el.disabled = true;
          el.textContent = "Cloning…";
          const res = await api.openWs(id);
          state.repo = (await api.repo(id)).repo;
          state.tab = "files"; state.treePath = ""; state.open = []; state.activePath = null;
          await refreshTree();
          state.status = await api.status(id);
          toast(res.existed ? "Workspace already open" : `Cloned ${state.repo.full_name}`);
          return paint();
        }

        case "pull-ws": {
          const res = await api.pullWs(id);
          state.repo = (await api.repo(id)).repo;
          await refreshTree();
          state.status = await api.status(id);
          toast(res.ok ? "Pulled latest" : "Pull failed — see the log");
          return paint();
        }

        case "cd": {
          state.treePath = el.dataset.path || "";
          await refreshTree();
          return paint();
        }

        case "refresh-tree": { await refreshTree(); return paint(); }

        case "open-file": {
          const p = el.dataset.path;
          if (!state.open.find((f) => f.path === p)) {
            const file = await api.readFile(state.repo.id, p);
            state.open.push({
              path: p, content: file.content || "", original: file.content || "",
              language: file.language, binary: file.binary, size: file.size,
            });
            if (state.open.length > 8) state.open.shift();
          }
          state.activePath = p;
          return paint({ focusEditor: true });
        }

        case "focus-file": { state.activePath = el.dataset.path; return paint({ focusEditor: true }); }

        case "close-file": {
          const p = el.dataset.path;
          const f = state.open.find((x) => x.path === p);
          if (f && f.content !== f.original && !confirm(`${p} has unsaved changes. Close anyway?`)) return;
          state.open = state.open.filter((x) => x.path !== p);
          if (state.activePath === p) state.activePath = state.open.at(-1)?.path || null;
          return paint();
        }

        case "save-file": return void (await saveActive());

        case "new-file": { state.modal = { kind: "new-file" }; return paint(); }

        case "create-file": {
          const input = document.getElementById("new-file-path");
          const p = (input?.value || "").trim();
          if (!p) return toast("Enter a path");
          const isDir = p.endsWith("/");
          await api.newFile(state.repo.id, p.replace(/\/$/, ""), isDir ? "dir" : "file");
          state.modal = null;
          await refreshTree();
          state.status = await api.status(state.repo.id);
          if (!isDir) {
            state.open.push({ path: p, content: "", original: "", language: "text", binary: false, size: 0 });
            state.activePath = p;
          }
          toast(`Created ${p}`);
          return paint({ focusEditor: true });
        }

        case "delete-file": {
          const p = el.dataset.path;
          if (!confirm(`Delete ${p}? This only changes the local workspace.`)) return;
          await api.delFile(state.repo.id, p);
          state.open = state.open.filter((x) => x.path !== p);
          if (state.activePath === p) state.activePath = state.open.at(-1)?.path || null;
          await refreshTree();
          state.status = await api.status(state.repo.id);
          toast(`Deleted ${p}`);
          return paint();
        }

        case "close-modal": { state.modal = null; return paint(); }

        case "sel-file": {
          const p = el.dataset.path;
          if (!state.selected) state.selected = new Set((state.status.files || []).map((f) => f.path));
          if (el.checked) state.selected.add(p); else state.selected.delete(p);
          const btn = document.querySelector('[data-act="push"]');
          if (btn) btn.textContent = `Push ${state.selected.size} file${state.selected.size === 1 ? "" : "s"} & run gate`;
          return;
        }

        case "show-diff": {
          state.diffPath = el.dataset.path;
          const d = await api.diff(state.repo.id, state.diffPath);
          state.diff = d.diff;
          return paint();
        }

        case "discard-file": {
          const p = el.dataset.path;
          if (!confirm(`Discard changes to ${p}?`)) return;
          const res = await api.discard(state.repo.id, p);
          state.status = res.status;
          state.open = state.open.filter((x) => x.path !== p);
          if (state.activePath === p) state.activePath = state.open.at(-1)?.path || null;
          await refreshTree();
          toast(`Reverted ${p}`);
          return paint();
        }

        case "discard-all": {
          if (!confirm("Discard every uncommitted change in the workspace?")) return;
          const res = await api.discard(state.repo.id, null);
          state.status = res.status; state.open = []; state.activePath = null; state.diff = "";
          await refreshTree();
          toast("Workspace reset");
          return paint();
        }

        case "strategy": { state.strategy = el.dataset.value; return paint(); }

        case "push": {
          const message = (document.getElementById("commit-msg")?.value || "").trim();
          if (!message) return toast("A commit message is required");
          const runGate = document.getElementById("run-gate")?.checked !== false;
          const paths = state.selected ? [...state.selected] : null;
          if (paths && !paths.length) return toast("Select at least one file");

          state.pushing = true; paint();
          try {
            const res = await api.push(id, {
              message,
              strategy: state.strategy || state.me?.push_strategy || "branch_pr",
              paths,
              run_gate: runGate,
              open_pr: true,
            });
            state.pushing = false;
            state.commitMsg = ""; state.selected = null; state.diff = ""; state.diffPath = null;
            state.repo = (await api.repo(id)).repo;
            state.status = await api.status(id);
            state.open = state.open.map((f) => ({ ...f, original: f.content }));
            state.me = await api.me();
            state.modal = { kind: "pushed", ...res };
            toast(`Pushed to ${res.push.branch}`);
            return paint();
          } catch (err) {
            state.pushing = false; paint();
            throw err;
          }
        }

        case "goto-run": { state.modal = null; return go(`/console/runs/${el.dataset.id}`); }

        case "show-recovery": {
          state.showRecovery = state.showRecovery === el.dataset.id ? null : el.dataset.id;
          return paint();
        }

        case "revert-run": {
          if (!confirm("Open a pull request that reverts this commit?\n\nChaosGate never pushes directly to a shared branch — you review and merge the PR.")) return;
          el.disabled = true;
          el.textContent = "Opening revert…";
          const res = await api.revert(el.dataset.id);
          state.run = (await api.run(el.dataset.id)).run;
          toast(res.pull_request ? `Revert PR #${res.pull_request.number} opened` : `Revert branch ${res.branch} pushed`);
          return paint();
        }

        case "file-incident": {
          el.disabled = true;
          const res = await api.fileIncident(el.dataset.id);
          state.run = (await api.run(el.dataset.id)).run;
          toast(res.existed ? "Incident already open" : `Incident #${res.number} filed`);
          return paint();
        }

        case "focus-stage": {
          const key = el.dataset.key;
          const det = [...document.querySelectorAll(".stage-detail")]
            .find((d) => d.querySelector("summary b")?.textContent === state.run.stages.find((s) => s.key === key)?.name);
          if (det) { det.open = true; det.scrollIntoView({ behavior: "smooth", block: "center" }); }
          return;
        }

        case "oauth": {
          const { authorize_url } = await api.oauthUrl();
          window.location.href = authorize_url;
          return;
        }

        case "refresh-gh": {
          state.ghLoading = true; paint();
          state.githubRepos = (await api.ghRepos()).repos;
          state.ghLoading = false;
          return paint();
        }

        case "add": {
          el.disabled = true;
          const data = await api.addRepo(el.dataset.name);
          toast(`Connected ${data.repo.full_name}`);
          return go(`/console/repos/${data.repo.id}`);
        }

        case "unlink": {
          if (!confirm("Unlink this repository and delete its local workspace?")) return;
          await api.delRepo(id);
          toast("Repository unlinked");
          return go("/console/repos");
        }

        case "logout": {
          await api.logout();
          state.githubRepos = []; state.me = await api.me();
          toast("GitHub disconnected");
          return paint();
        }

        case "install-workflow": {
          el.disabled = true; el.textContent = "Installing…";
          const res = await api.installWorkflow(id);
          state.repo = res.repo ? { ...state.repo, ...res.repo } : state.repo;
          toast("Workflow committed to .github/workflows/chaosgate.yml");
          return paint();
        }

        case "install-webhook": {
          el.disabled = true;
          const res = await api.installWebhook(id);
          state.repo = (await api.repo(id)).repo;
          toast(`Webhook pointed at ${res.url}`);
          return paint();
        }

        case "dispatch": {
          const data = await api.dispatch(id);
          return toast(data.message || "Dispatched");
        }

        case "toggle-autorun": {
          await api.patchRepo(id, { auto_run_on_push: el.checked });
          toast(el.checked ? "Auto-run enabled" : "Auto-run disabled");
          return;
        }

        case "toggle": {
          const key = el.dataset.key;
          state.policy = (await api.savePolicy({ ...state.policy, [key]: !state.policy[key] })).policy;
          return paint();
        }

        case "refresh-caps": {
          await api.capabilities();
          state.me = await api.me();
          toast("Toolchain re-probed");
          return paint();
        }

        case "publish-dashboard": {
          el.disabled = true;
          try {
            const res = await api.publishDashboard();
            toast(`Dashboard published: ${res.url}`);
          } catch (err) {
            toast(err.message);
          }
          el.disabled = false;
          return;
        }
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
        if (!data.token?.trim()) return toast("Paste a token first");
        const res = await api.githubPat(data.token.trim());
        state.me = await api.me();
        if (res.warning) toast(res.warning);
        state.ghLoading = true; paint();
        try { state.githubRepos = (await api.ghRepos()).repos; } catch (err) { toast(err.message); }
        state.ghLoading = false;
        toast(`Connected as ${state.me.workspace.github_login}`);
        paint();
      }
      if (kind === "add-repo") {
        if (!data.full_name?.trim()) return toast("Enter owner/name");
        const res = await api.addRepo(data.full_name.trim());
        toast(`Connected ${res.repo.full_name}`);
        go(`/console/repos/${res.repo.id}`);
      }
      if (kind === "policy-num") {
        state.policy = (await api.savePolicy({
          max_p95_ms: Number(data.max_p95_ms),
          max_error_rate: Number(data.max_error_rate),
        })).policy;
        toast("Thresholds saved");
        paint();
      }
    } catch (err) { toast(err.message); }
  }

  async function bootDemo() {
    bootEl.classList.remove("hidden");
    await api.demo();
    state.me = await api.me();
    await new Promise((r) => setTimeout(r, 1000));
    bootEl.classList.add("hidden");
    go("/console");
  }

  // ================================================================ render
  async function render() {
    const route = parseRoute();
    if (route.name !== "run") stopStream();
    try {
      if (!state.me) state.me = await api.me();

      if (route.name === "landing") return paint();

      if (route.name === "overview") {
        state.me = await api.me();
        state.repos = (await api.repos()).repos;
      } else if (route.name === "repos") {
        state.repos = (await api.repos()).repos;
      } else if (route.name === "repo") {
        const fresh = (await api.repo(route.id)).repo;
        const switched = state.repo?.id !== fresh.id;
        state.repo = fresh;
        if (switched) {
          state.tab = fresh.workspace_cloned ? "files" : "overview";
          state.open = []; state.activePath = null; state.treePath = "";
          state.tree = null; state.diff = ""; state.selected = null; state.commitMsg = "";
        }
        if (fresh.workspace_cloned) {
          state.status = await api.status(fresh.id);
          if (state.tab === "files" && !state.tree) await refreshTree();
          if (state.tab === "changes" && !state.diff) {
            try { state.diff = (await api.diff(fresh.id)).diff; } catch (_) {}
          }
        }
      } else if (route.name === "runs") {
        state.runs = (await api.runs()).runs;
      } else if (route.name === "run") {
        state.run = (await api.run(route.id)).run;
        state.artifacts = (await api.artifacts(route.id)).artifacts || [];
        if (state.run && (state.run.status === "queued" || state.run.status === "running")) {
          watchRun(state.run.id);
        }
      } else if (route.name === "connect") {
        if (state.me?.workspace?.connected && !state.githubRepos.length) {
          state.ghLoading = true; paint();
          try { state.githubRepos = (await api.ghRepos()).repos; } catch (_) {}
          state.ghLoading = false;
        }
      } else if (route.name === "docs") {
        state.workflow = (await api.workflow()).content;
        state.contract = (await api.contract()).content;
      } else if (route.name === "settings") {
        state.policy = (await api.policy()).policy;
      } else if (route.name === "observability") {
        state.observability = await api.observability();
        state.webhooks = (await api.webhooks()).events;
      }
      paint();
    } catch (err) {
      app.innerHTML = `<div class="main"><div class="empty">${esc(err.message)}</div></div>`;
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.modal) { state.modal = null; paint(); }
  });

  render();
})();
