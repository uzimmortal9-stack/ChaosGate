(() => {
  const app = document.getElementById("app");
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
    
    // View state
    activeTab: "overview",
    runStatusFilter: "all",
    selectedStage: null,
    showFullLog: false,
    revertData: null,
    revertLoading: false,

    // Workspace editor
    repoTab: "runs",
    tree: null,
    treePath: "",
    open: [],          // [{path, content, original, language, binary}]
    activePath: null,
    status: { files: [], clean: true },
    diff: "",
    diffPath: null,
    selected: null,
    modal: null,
    busy: false,
  };

  // ------------------------------------------------------------------ API
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

    // Workspace
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

  // ---------------------------------------------------------------- Utilities
  function toast(message, kind = "ok") {
    if (!toastRoot) return;
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.textContent = message;
    toastRoot.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 300);
    }, 4500);
  }

  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");

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
    if (!href || !href.startsWith("/") || a.target === "_blank") return;
    e.preventDefault();
    go(href);
  });

  function ago(iso) {
    if (!iso) return "just now";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const s = Math.max(0, (Date.now() - then) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  function dur(seconds) {
    if (seconds == null || isNaN(seconds)) return "—";
    const s = Number(seconds);
    if (s < 60) return `${s.toFixed(1)}s`;
    return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  }

  // ---------------------------------------------------------------- Visual Components
  function Score(value, size = 40) {
    const num = Math.round(Number(value) || 0);
    const r = size / 2 - (size > 80 ? 6 : 3.5);
    const c = 2 * Math.PI * r;
    const color = num >= 75 ? "#34d399" : num >= 50 ? "#fcd34d" : "#fb7185";
    const strokeWidth = size > 80 ? 6 : 3;
    const fontSize = size > 80 ? "text-4xl" : "text-xs";
    const offset = c * (1 - Math.max(0, Math.min(100, num)) / 100);
    return `
      <div class="score-wrap" style="width:${size}px; height:${size}px;">
        <svg width="${size}" height="${size}" class="score-svg">
          <circle cx="${size / 2}" cy="${size / 2}" r="${r}" stroke="rgba(255,255,255,0.08)" stroke-width="${strokeWidth}" fill="none" />
          <circle cx="${size / 2}" cy="${size / 2}" r="${r}" stroke="${color}" stroke-width="${strokeWidth}" fill="none" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${offset}" />
        </svg>
        <span class="score-num ${fontSize}">${num}</span>
      </div>`;
  }

  function Verdict(conclusion, size = "sm") {
    const pass = conclusion === "PASS";
    const isRun = conclusion === "running" || conclusion === "queued";
    if (isRun) {
      return `<span class="verdict verdict-run">
        <span class="verdict-dot bg-indigo-400"></span>
        Running
      </span>`;
    }
    return `<span class="verdict ${pass ? "verdict-pass" : "verdict-fail"} ${size === "lg" ? "verdict-lg" : ""}">
      <span class="verdict-dot ${pass ? "bg-emerald-400" : "bg-rose-400"}"></span>
      ${pass ? "Passed" : "Blocked"}
    </span>`;
  }

  function Nav() {
    const r = parseRoute();
    const here = r.name;
    const item = (href, label, key) => {
      const active = here === key || (key === "overview" && here === "landing");
      return `<a href="${href}" class="nav-link ${active ? "active" : ""}">${label}</a>`;
    };
    return `
      <div class="nav-fixed-wrap">
        <nav class="nav-pill glass">
          <a href="/" class="brand-link">
            <span class="brand-icon">C</span>
            <span class="brand-name">ChaosGate</span>
          </a>
          ${item("/", "Overview", "overview")}
          ${item("/runs", "Runs", "runs")}
          ${item("/repos", "Repositories", "repos")}
          ${item("/settings", "Policies", "settings")}
          ${item("/observability", "Observability", "observability")}
          ${item("/docs", "Docs", "docs")}
        </nav>
      </div>`;
  }

  function Shell(inner) {
    return `
      ${Nav()}
      <main class="app-main">
        ${inner}
      </main>
      ${ModalSheet()}`;
  }

  // ---------------------------------------------------------------- Screens
  // 1. Overview Screen
  function overviewView() {
    const s = state.me?.stats || {};
    const runs = state.me?.recent_runs || [];
    const repos = state.repos || [];
    const cfg = state.policy || {};
    const maxP95 = cfg.max_p95_ms || 300;
    
    // Determine blocked repos from last_run or runs
    const blockedRepos = repos.filter((r) => {
      const lr = r.last_run || (runs.find((x) => x.repo_id === r.id || x.repo?.id === r.id));
      return lr && lr.conclusion === "FAIL";
    });
    const passRate = s.pass_rate != null ? Math.round(s.pass_rate) : (s.runs ? Math.round((s.passed / s.runs) * 100) : 0);

    return Shell(`
      <div class="space-y-6">
        <section class="hero-section rise">
          <p class="hero-pill">
            <span class="pulse-dot"></span> Gate armed
          </p>
          <h1 class="hero-headline">
            ${blockedRepos.length === 0 ? "Everything is clear to ship." : `${blockedRepos.length} ${blockedRepos.length === 1 ? "repository is" : "repositories are"} blocked from merging.`}
          </h1>
          <p class="hero-sub">
            Deploy only if it survives — every pull request is load-tested, attacked and verified before main.
          </p>
        </section>

        <div class="grid-3">
          <div class="glass lift stat-panel rise">
            <p class="stat-label">Pass rate</p>
            <p class="stat-value">${passRate}%</p>
            <p class="stat-sub">${s.runs ?? runs.length} completed runs</p>
          </div>
          <div class="glass lift stat-panel rise">
            <p class="stat-label">Latency SLA</p>
            <p class="stat-value">${maxP95}ms</p>
            <p class="stat-sub">p95 SLA threshold</p>
          </div>
          <div class="glass lift stat-panel rise">
            <p class="stat-label">Repositories</p>
            <p class="stat-value">${repos.length}</p>
            <p class="stat-sub">${blockedRepos.length} blocked from merge</p>
          </div>
        </div>

        ${blockedRepos.length > 0 ? `
          <div class="grid-2">
            ${blockedRepos.map((r) => {
              const lr = r.last_run || runs.find((x) => x.repo_id === r.id || x.repo?.id === r.id) || {};
              return `
                <a href="/runs/${lr.id || ''}" class="glass lift block p-5 rounded-3xl" style="padding:22px;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:600; font-size:15px;">${esc(r.name || r.full_name)}</span>
                    ${Verdict("FAIL")}
                  </div>
                  <p style="margin-top:12px; font-size:13.5px; color:rgba(251,113,133,0.85);">${esc(lr.summary || "Policy violation detected")}</p>
                  <p style="margin-top:12px; font-size:12.5px; color:var(--text-dim);">
                    ${lr.pr_number ? `PR #${lr.pr_number}` : lr.branch || "main"} · ${esc(lr.commit_message || "Commit")} · ${ago(lr.created_at)}
                  </p>
                </a>
              `;
            }).join("")}
          </div>
        ` : ""}

        <div class="glass rise" style="overflow:hidden;">
          <div style="display:flex; justify-content:space-between; align-items:center; padding:20px 24px 14px;">
            <h2 style="font-size:16px; font-weight:600;">Recent runs</h2>
            <a href="/runs" style="font-size:13.5px; color:var(--text-muted); transition:color 0.2s;">View all →</a>
          </div>
          ${RunList(runs.slice(0, 6))}
        </div>
      </div>
    `);
  }

  // 2. Runs Screen
  function runsView() {
    const all = state.runs || [];
    const filter = state.runStatusFilter || "all";
    const filtered = filter === "pass" 
      ? all.filter((r) => r.conclusion === "PASS") 
      : filter === "fail" 
        ? all.filter((r) => r.conclusion === "FAIL") 
        : all;

    const passCount = all.filter((r) => r.conclusion === "PASS").length;
    const failCount = all.filter((r) => r.conclusion === "FAIL").length;

    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Runs</h1>
            <p class="page-subtitle">Every gate check, newest first.</p>
          </div>
        </div>

        <div style="display:flex; gap:6px; margin-bottom:16px;">
          <button data-act="filter-runs" data-filter="all" class="nav-link ${filter === "all" ? "active" : ""}">
            All <span style="opacity:0.6; margin-left:4px;">${all.length}</span>
          </button>
          <button data-act="filter-runs" data-filter="pass" class="nav-link ${filter === "pass" ? "active" : ""}">
            Passed <span style="opacity:0.6; margin-left:4px;">${passCount}</span>
          </button>
          <button data-act="filter-runs" data-filter="fail" class="nav-link ${filter === "fail" ? "active" : ""}">
            Blocked <span style="opacity:0.6; margin-left:4px;">${failCount}</span>
          </button>
        </div>

        <div class="glass rise" style="overflow:hidden;">
          ${RunList(filtered)}
        </div>
      </div>
    `);
  }

  function RunList(runs) {
    if (!runs || !runs.length) {
      return `<div style="padding:48px 24px; text-align:center; color:var(--text-dim); font-size:14px;">No runs recorded yet.</div>`;
    }
    return `
      <ul class="run-list">
        ${runs.map((r) => `
          <li class="run-list-item">
            <a href="/runs/${r.id}" class="run-row">
              ${Score(r.resilience_score ?? r.score, 40)}
              <div class="run-main-info">
                <p class="run-commit-msg">${esc(r.commit_message || "Manual run")}</p>
                <p class="run-meta">
                  <span class="run-meta-repo">${esc(r.repo?.full_name || r.repo?.name || "Repository")}</span> · 
                  ${r.pr_number ? `PR #${r.pr_number}` : r.branch || "main"} · 
                  ${esc(r.author || "developer")} · 
                  ${ago(r.created_at || r.started_at)}
                </p>
              </div>
              ${r.conclusion === "FAIL" ? `<span class="run-summary-fail">${esc(r.summary || "Policy violation")}</span>` : ""}
              ${Verdict(r.conclusion || r.status)}
              <span class="run-arrow">→</span>
            </a>
          </li>
        `).join("")}
      </ul>`;
  }

  // 3. Run Detail Screen
  function runDetailView() {
    const run = state.run;
    if (!run) {
      return Shell(`<div style="padding:48px 0; text-align:center; color:var(--text-dim);">Loading run…</div>`);
    }

    const pass = run.conclusion === "PASS";
    const stages = run.stages || [];
    const failedStages = stages.filter((s) => s.status === "failed" && s.key !== "verdict");
    const loadMetrics = stages.find((s) => s.key === "load")?.metrics || {};
    const chaosMetrics = stages.find((s) => s.key === "chaos")?.metrics || {};
    const openStageKey = state.selectedStage || (failedStages[0]?.key ?? stages[0]?.key);

    return Shell(`
      <div class="space-y-5">
        <a href="/runs" style="display:inline-flex; align-items:center; gap:6px; font-size:13.5px; color:var(--text-dim); transition:color 0.2s;">
          ← Runs
        </a>

        <!-- Hero Panel with Glow Orb -->
        <div class="glass run-hero-panel rise">
          <div class="run-hero-glow ${pass ? "glow-pass" : "glow-fail"}"></div>
          <div class="run-hero-flex">
            ${Score(run.resilience_score ?? run.score, 112)}
            <div style="min-width:0; flex:1;">
              <p class="run-hero-status ${pass ? "text-emerald-300" : "text-rose-300"}">
                ${pass ? "Gate open · merge allowed" : "Gate sealed · merge blocked"}
              </p>
              <h1 class="run-hero-title">${esc(run.commit_message || "Manual gate verification")}</h1>
              <p class="run-hero-meta">
                ${esc(run.repo?.full_name || run.repo?.name || "Repository")} · 
                ${run.pr_number ? `PR #${run.pr_number}` : run.branch || "main"} · 
                <span class="font-mono">${esc((run.commit_sha || "").slice(0, 7))}</span> · 
                ${esc(run.author || "developer")} · 
                ${ago(run.created_at || run.started_at)}
              </p>
            </div>
            <div class="btn-pill-group">
              <button data-act="export-json" class="btn-ghost">Export</button>
              ${pass ? `<button data-act="open-rollback" class="btn-ghost">Roll back</button>` : ""}
              <button data-act="rerun" data-id="${run.repo_id || run.repo?.id}" class="btn-primary">Re-run</button>
            </div>
          </div>
        </div>

        <!-- Failure Callout Banners -->
        ${failedStages.length > 0 ? `
          <div class="space-y-3">
            ${failedStages.map((s) => `
              <div class="fail-banner glass rise">
                <span class="fail-banner-dot"></span>
                <div>
                  <p class="fail-banner-title">${esc(s.name)}</p>
                  <p class="fail-banner-summary">${esc(s.summary)}</p>
                </div>
              </div>
            `).join("")}
          </div>
        ` : ""}

        <!-- 4 Metric Cards -->
        <div class="grid-4">
          <div class="glass stat-panel">
            <p class="stat-label">p95 latency</p>
            <p class="stat-value" style="font-size:24px;">${loadMetrics.p95_ms != null ? `${loadMetrics.p95_ms}ms` : "—"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Error rate</p>
            <p class="stat-value" style="font-size:24px;">${loadMetrics.error_rate_pct != null ? `${loadMetrics.error_rate_pct}%` : "0.0%"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Recovery time</p>
            <p class="stat-value" style="font-size:24px;">${chaosMetrics.recovery_ms != null ? `${chaosMetrics.recovery_ms}ms` : "—"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Duration</p>
            <p class="stat-value" style="font-size:24px;">${dur(run.duration_ms ? run.duration_ms / 1000 : 18)}</p>
          </div>
        </div>

        <!-- Pipeline Stages Section -->
        <div class="glass p-5 sm:p-6" style="padding:26px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <h2 style="font-size:16px; font-weight:600;">Pipeline Stages (13)</h2>
            <button data-act="toggle-full-log" class="btn-ghost" style="font-size:12.5px; padding:4px 12px;">
              ${state.showFullLog ? "Show stages" : "Full log"}
            </button>
          </div>

          <!-- Segmented Stepper Bar -->
          <div class="stage-stepper-wrap">
            ${stages.map((s) => `
              <button 
                title="${esc(s.name)} · ${esc(s.status)}" 
                data-act="select-stage" 
                data-key="${esc(s.key)}" 
                class="stage-seg ${s.status} ${openStageKey === s.key && !state.showFullLog ? "active-seg" : ""}">
              </button>
            `).join("")}
          </div>

          ${state.showFullLog ? `
            <div class="terminal-box" id="term">
              ${stages.map((s) => {
                const logs = s.logs || `${s.name} completed with status: ${s.status}\n`;
                return logs.split("\n").filter(Boolean).map((line, idx) => `
                  <div class="log-line">
                    <span class="log-time">${idx * 0.4}s</span>
                    <span class="log-level ${s.status === "failed" ? "level-crit" : s.status === "degraded" ? "level-warn" : "level-info"}">${s.status.toUpperCase()}</span>
                    <span class="log-stage">${esc(s.key)}</span>
                    <span class="log-msg">${esc(line)}</span>
                  </div>
                `).join("");
              }).join("")}
            </div>
          ` : `
            <ul class="stage-list">
              ${stages.map((s) => {
                const isOpen = openStageKey === s.key;
                return `
                  <li class="stage-item ${isOpen ? "open" : ""}">
                    <button class="stage-row-btn" data-act="select-stage" data-key="${esc(s.key)}">
                      <span class="stage-dot ${s.status === "passed" ? "bg-emerald-400" : s.status === "failed" ? "bg-rose-400" : s.status === "degraded" ? "bg-amber-300" : "bg-indigo-400"}"></span>
                      <span class="stage-name">${esc(s.name)}</span>
                      <span class="stage-summary" style="${s.status === "failed" ? "color:var(--rose);" : s.status === "degraded" ? "color:var(--amber);" : ""}">${esc(s.summary || "Stage passed")}</span>
                      <span class="stage-duration">${s.duration_ms ? `${(s.duration_ms / 1000).toFixed(1)}s` : "—"}</span>
                    </button>
                    ${isOpen ? `
                      <div class="stage-body">
                        ${s.metrics && Object.keys(s.metrics).length > 0 ? `
                          <div class="metric-pills">
                            ${Object.entries(s.metrics).map(([k, v]) => {
                              const displayVal = (typeof v === "object" && v !== null) ? (v.total ?? v.count ?? JSON.stringify(v)) : v;
                              return `<span class="metric-pill">${esc(k.replace(/_/g, " "))}: <strong>${esc(displayVal)}</strong></span>`;
                            }).join("")}
                          </div>
                        ` : ""}
                        <pre class="terminal-box" style="max-height:220px; font-size:11.5px; padding:12px;">${esc(s.logs || `${s.name} executed successfully with zero faults.`)}</pre>
                      </div>
                    ` : ""}
                  </li>
                `;
              }).join("")}
            </ul>
          `}
        </div>
      </div>
    `);
  }

  // 4. Repositories Screen
  function reposView() {
    const repos = state.repos || [];
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Repositories</h1>
            <p class="page-subtitle">Codebases monitored and protected by the release gate.</p>
          </div>
          <button data-act="open-connect-repo" class="btn-primary">Connect repository</button>
        </div>

        <div class="repo-grid">
          ${repos.map((r) => {
            const initials = (r.name || r.full_name || "RP").slice(0, 2).toUpperCase();
            const lr = r.last_run;
            return `
              <a href="/repos/${r.id}" class="glass lift repo-card rise">
                <div class="repo-card-head">
                  <div class="repo-avatar">${initials}</div>
                  ${lr ? Verdict(lr.conclusion) : `<span style="font-size:12px; color:var(--text-dim);">No runs</span>`}
                </div>
                <p class="repo-name">${esc(r.name || r.full_name)}</p>
                <p class="repo-full-name">${esc(r.full_name)}</p>
                <div class="repo-tags">
                  <span class="tag-pill">${esc(r.runtime || "Python")}</span>
                  ${r.framework ? `<span class="tag-pill">${esc(r.framework)}</span>` : ""}
                  <span style="margin-left:auto;">${lr ? ago(lr.created_at) : r.default_branch || "main"}</span>
                </div>
              </a>
            `;
          }).join("")}
        </div>
      </div>
    `);
  }

  // 5. Repository Detail & Workspace Editor
  function repoDetailView() {
    const repo = state.repo;
    if (!repo) {
      return Shell(`<div style="padding:48px 0; text-align:center; color:var(--text-dim);">Loading repository…</div>`);
    }

    const runs = repo.runs || [];
    const avgScore = runs.length ? Math.round(runs.reduce((a, b) => a + (b.resilience_score ?? b.score ?? 0), 0) / runs.length) : 84;
    const scored = runs.slice(0, 10);
    const activeTab = state.repoTab || "runs";

    return Shell(`
      <div class="space-y-5">
        <a href="/repos" style="display:inline-flex; align-items:center; gap:6px; font-size:13.5px; color:var(--text-dim); transition:color 0.2s;">
          ← Repositories
        </a>

        <div class="page-header rise" style="margin-bottom:18px;">
          <div>
            <h1 class="page-title">${esc(repo.name || repo.full_name)}</h1>
            <p class="page-subtitle">${esc(repo.full_name)} · ${esc(repo.runtime || "Python")}${repo.framework ? ` · ${esc(repo.framework)}` : ""} · ${esc(repo.default_branch || "main")}</p>
          </div>
          <div class="glass flex items-center gap-1 rounded-full p-1 pl-4" style="display:flex; align-items:center; gap:8px; padding:4px 6px 4px 16px; border-radius:var(--radius-full);">
            <span style="font-size:13px; color:var(--text-dim);">branch</span>
            <input id="run-branch" value="${esc(repo.default_branch || "main")}" style="width:110px; font-size:13.5px; color:#fff;" />
            <button data-act="trigger-repo-run" data-id="${repo.id}" class="btn-primary" style="padding:7px 16px; font-size:13px;">Run gate</button>
          </div>
        </div>

        <div class="grid-3">
          <div class="glass stat-panel">
            <p class="stat-label">Avg. resilience score</p>
            <p class="stat-value">${avgScore}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Total gate runs</p>
            <p class="stat-value">${runs.length}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Score trend</p>
            <div class="score-trend-bar">
              ${scored.length ? scored.map((r) => `
                <div class="score-trend-seg" style="height:${Math.max(10, r.resilience_score ?? r.score ?? 50)}%; background:${(r.resilience_score ?? r.score ?? 0) >= 75 ? "var(--emerald)" : "var(--rose)"};"></div>
              `).join("") : `<div class="score-trend-seg" style="height:80%; background:var(--emerald);"></div><div class="score-trend-seg" style="height:90%; background:var(--emerald);"></div><div class="score-trend-seg" style="height:70%; background:var(--amber);"></div>`}
            </div>
          </div>
        </div>

        <!-- Navigation Tabs: History vs Workspace Code Editor -->
        <div style="display:flex; gap:6px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:10px;">
          <button data-act="set-repo-tab" data-tab="runs" class="nav-link ${activeTab === "runs" ? "active" : ""}">Runs History</button>
          <button data-act="set-repo-tab" data-tab="editor" class="nav-link ${activeTab === "editor" ? "active" : ""}">Workspace Code Editor</button>
        </div>

        ${activeTab === "runs" ? `
          <div class="glass rise" style="overflow:hidden;">
            ${RunList(runs)}
          </div>
        ` : WorkspaceEditor(repo)}
      </div>
    `);
  }

  function WorkspaceEditor(repo) {
    const files = state.tree?.entries || [];
    const activeFile = state.open.find((f) => f.path === state.activePath);
    return `
      <div class="glass ws-editor-wrap rise">
        <div class="ws-tree">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; padding:0 4px;">
            <span style="font-weight:600; font-size:12px; text-transform:uppercase; color:var(--text-dim);">Files</span>
            <button data-act="refresh-tree" style="color:var(--text-muted); font-size:12px;">↻</button>
          </div>
          ${files.length ? files.map((f) => `
            <div class="ws-tree-item ${state.activePath === f.path ? "active-file" : ""}" data-act="open-file" data-path="${esc(f.path)}">
              <span>${f.type === "dir" ? "📁" : "📄"}</span>
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${esc(f.name)}</span>
            </div>
          `).join("") : `<p style="padding:16px 8px; font-size:12px; color:var(--text-dim);">No files found or workspace not mounted.</p>`}
        </div>
        <div class="ws-editor-main">
          <div class="ws-editor-bar">
            <span>${esc(state.activePath || "No file opened")}</span>
            ${activeFile ? `<button data-act="save-file" class="btn-primary" style="padding:4px 14px; font-size:12px;">Save</button>` : ""}
          </div>
          <textarea id="editor" class="ws-textarea" placeholder="Select a file from the workspace tree to inspect or edit…">${esc(activeFile?.content || "")}</textarea>
        </div>
      </div>`;
  }

  // 6. Settings / Policies Screen
  function settingsView() {
    const p = state.policy || {};
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Policies</h1>
            <p class="page-subtitle">What it takes to reach main. Enforced on every pull request.</p>
          </div>
        </div>

        <form data-form="save-policy" class="space-y-4">
          <div class="glass policy-group">
            <div class="policy-row">
              <div>
                <p class="policy-label">p95 latency SLA</p>
                <p class="policy-desc">Synthetic k6 concurrency test fails if response time exceeds this threshold.</p>
              </div>
              <div class="num-input-wrap">
                <input name="max_p95_ms" type="number" class="num-input" value="${p.max_p95_ms || 300}" />ms
              </div>
            </div>

            <div class="policy-row">
              <div>
                <p class="policy-label">Max error rate</p>
                <p class="policy-desc">Share of HTTP 5xx responses allowed under stress.</p>
              </div>
              <div class="num-input-wrap">
                <input name="max_error_rate_pct" type="number" step="0.1" class="num-input" value="${p.max_error_rate_pct || 1.0}" />%
              </div>
            </div>
          </div>

          <div class="glass policy-group">
            <div class="policy-row">
              <div>
                <p class="policy-label">Block on secrets</p>
                <p class="policy-desc">Instantly fail if an API token, JWT, or private credential is found in the diff.</p>
              </div>
              <button type="button" class="toggle-btn ${p.fail_on_secrets !== false ? "on" : ""}" data-act="toggle-policy" data-key="fail_on_secrets">
                <span class="toggle-thumb"></span>
              </button>
            </div>

            <div class="policy-row">
              <div>
                <p class="policy-label">Fail when degraded</p>
                <p class="policy-desc">Treat missing local Docker or Kubernetes tools as an immediate pipeline failure.</p>
              </div>
              <button type="button" class="toggle-btn ${p.fail_on_degraded ? "on" : ""}" data-act="toggle-policy" data-key="fail_on_degraded">
                <span class="toggle-thumb"></span>
              </button>
            </div>

            <div class="policy-row">
              <div>
                <p class="policy-label">Warn on unpinned dependencies</p>
                <p class="policy-desc">Flag dependency lockfiles with unpinned or wildcard package versions.</p>
              </div>
              <button type="button" class="toggle-btn ${p.warn_unpinned_deps !== false ? "on" : ""}" data-act="toggle-policy" data-key="warn_unpinned_deps">
                <span class="toggle-thumb"></span>
              </button>
            </div>
          </div>

          <div class="glass policy-group">
            <div class="policy-row">
              <div>
                <p class="policy-label">GitHub Token</p>
                <p class="policy-desc">Used to report commit statuses and open 1-click revert PRs. Stored encrypted with AES-CTR + PBKDF2.</p>
              </div>
              <input name="github_token" type="password" placeholder="ghp_••••••••••••••••••••" value="${p.github_token ? "••••••••••••••••" : ""}" class="text-input" />
            </div>
          </div>

          <div style="display:flex; justify-content:flex-end;">
            <button type="submit" class="btn-primary" style="padding:10px 28px;">Save changes</button>
          </div>
        </form>
      </div>
    `);
  }

  // 7. Observability Screen
  function observabilityView() {
    const obs = state.observability || {};
    const tools = state.me?.toolchain || {};
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Observability</h1>
            <p class="page-subtitle">Real-time system telemetry, Prometheus metrics, and Grafana dashboard status.</p>
          </div>
          <button data-act="publish-grafana" class="btn-primary">Publish Grafana dashboard</button>
        </div>

        <div class="glass p-5" style="padding:24px;">
          <h2 style="font-size:16px; font-weight:600; margin-bottom:16px;">Toolchain Capabilities</h2>
          <div class="grid-3">
            ${Object.entries(tools).map(([name, t]) => `
              <div class="glass p-4" style="padding:16px; border-radius:var(--radius-md);">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <strong style="font-size:14px;">${esc(name)}</strong>
                  <span class="verdict ${t.available ? "verdict-pass" : "verdict-fail"}">${t.available ? "Ready" : "Degraded"}</span>
                </div>
                <p style="margin-top:8px; font-size:12.5px; color:var(--text-dim);">${esc(t.detail || "")}</p>
              </div>
            `).join("")}
          </div>
        </div>

        <div class="glass p-5" style="padding:24px;">
          <h2 style="font-size:16px; font-weight:600; margin-bottom:12px;">Prometheus Metrics Scraping</h2>
          <p style="font-size:13.5px; color:var(--text-muted); margin-bottom:16px;">
            ChaosGate exposes 28 Prometheus metric families at <code>/metrics</code> including <code>chaosgate_runs_total</code>, <code>chaosgate_stage_duration_seconds</code>, and <code>chaosgate_resilience_score</code>.
          </p>
          <a href="/metrics" target="_blank" class="btn-primary" style="font-size:13px; padding:7px 18px;">Inspect /metrics live</a>
        </div>
      </div>
    `);
  }

  // 8. Docs Screen
  function docsView() {
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Contract & Specifications</h1>
            <p class="page-subtitle">Standard specifications for chaosgate.yml release gates and multi-stage evaluation.</p>
          </div>
        </div>
        <div class="glass p-6" style="padding:26px;">
          <pre class="terminal-box" style="font-size:13px; line-height:1.7;">${esc(state.contract || `# ChaosGate Contract Schema v2
version: 2
stages:
  - validate
  - detect
  - unit
  - build
  - security
  - docker
  - kubernetes
  - smoke
  - load
  - prometheus
  - chaos
  - grafana
  - verdict

policies:
  max_p95_ms: 300
  max_error_rate: 1.0
  block_on_secrets: true
`)}</pre>
        </div>
      </div>
    `);
  }

  // ---------------------------------------------------------------- Rollback Modal Sheet
  function ModalSheet() {
    if (!state.modal) return "";
    if (state.modal.kind === "rollback") {
      const data = state.revertData;
      const run = state.run;
      return `
        <div class="modal-backdrop" data-act="close-modal">
          <div class="modal-sheet glass rise" data-stop>
            <div class="modal-sheet-head">
              <h3>Roll back ${esc((run?.commit_sha || "commit").slice(0, 7))}</h3>
              <button class="close-btn" data-act="close-modal">✕</button>
            </div>
            ${state.revertLoading ? `
              <p style="padding:32px 0; text-align:center; color:var(--text-dim); font-size:14px;">Running 3-way merge conflict analysis…</p>
            ` : data ? `
              <p style="font-size:14px; font-weight:500; color:${data.clean ? "var(--emerald)" : "var(--amber)"};">
                ${data.clean ? "Reverts cleanly — no merge collisions detected." : "Collision detected — patch quarantined."}
              </p>
              <ul class="revert-file-list">
                ${(data.files || []).map((f) => `
                  <li class="revert-file-item">
                    <span class="font-mono">${esc(f.path)}</span>
                    <span style="color:${f.state === "clean" ? "var(--emerald)" : "var(--amber)"}; font-size:12px;">
                      ${f.state === "clean" ? "clean" : `conflict ${esc(f.lines || "")}`}
                    </span>
                  </li>
                `).join("")}
              </ul>
              ${data.clean ? `
                <button data-act="execute-revert" data-id="${run.id}" class="btn-primary" style="width:100%; margin-top:20px; padding:12px 0;">
                  Open 1-Click Revert Pull Request
                </button>
              ` : `
                <div class="revert-cli-box">
                  ${(data.cli || []).map((cmd) => `<div>$ ${esc(cmd)}</div>`).join("")}
                </div>
              `}
            ` : `<p style="padding:24px 0; text-align:center;">Failed to analyze rollback.</p>`}
          </div>
        </div>
      `;
    }

    if (state.modal.kind === "connect-repo") {
      return `
        <div class="modal-backdrop" data-act="close-modal">
          <div class="modal-sheet glass rise" data-stop>
            <div class="modal-sheet-head">
              <h3>Connect GitHub Repository</h3>
              <button class="close-btn" data-act="close-modal">✕</button>
            </div>
            <form data-form="connect-repo" class="space-y-4">
              <div>
                <p style="font-size:13.5px; color:var(--text-muted); margin-bottom:8px;">Enter repository full name (e.g. <code>owner/repository</code>):</p>
                <input id="connect-repo-name" class="text-input" style="width:100%;" placeholder="owner/repo" required />
              </div>
              <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button type="button" data-act="close-modal" class="btn-ghost">Cancel</button>
                <button type="submit" class="btn-primary">Add repository</button>
              </div>
            </form>
          </div>
        </div>
      `;
    }
    return "";
  }

  // ---------------------------------------------------------------- Routing & Render
  function parseRoute() {
    const p = path();
    if (p === "/" || p === "/overview" || p === "/console") return { name: "overview" };
    if (p === "/runs" || p === "/console/runs") return { name: "runs" };
    if (p === "/repos" || p === "/console/repos") return { name: "repos" };
    if (p === "/settings" || p === "/console/settings" || p === "/policy") return { name: "settings" };
    if (p === "/observability" || p === "/console/observability") return { name: "observability" };
    if (p === "/docs" || p === "/console/docs") return { name: "docs" };
    let m = p.match(/^\/(?:console\/)?repos\/([^/]+)$/);
    if (m) return { name: "repo", id: m[1] };
    m = p.match(/^\/(?:console\/)?runs\/([^/]+)$/);
    if (m) return { name: "run", id: m[1] };
    return { name: "overview" };
  }

  async function render() {
    const route = parseRoute();
    try {
      if (!state.me) state.me = await api.me();
      if (route.name === "overview") {
        state.me = await api.me();
        state.repos = (await api.repos()).repos;
        state.policy = (await api.policy()).policy;
      } else if (route.name === "runs") {
        state.runs = (await api.runs()).runs;
      } else if (route.name === "run") {
        state.run = (await api.run(route.id)).run;
        state.artifacts = (await api.artifacts(route.id)).artifacts || [];
      } else if (route.name === "repos") {
        state.repos = (await api.repos()).repos;
      } else if (route.name === "repo") {
        state.repo = (await api.repo(route.id)).repo;
        if (state.repo.workspace_cloned && !state.tree) {
          state.tree = await api.files(state.repo.id);
        }
      } else if (route.name === "settings") {
        state.policy = (await api.policy()).policy;
      } else if (route.name === "observability") {
        state.observability = await api.observability();
      } else if (route.name === "docs") {
        state.contract = (await api.contract()).content;
      }
      paint();
    } catch (err) {
      app.innerHTML = `<div class="app-main"><div class="glass p-5" style="padding:24px; color:var(--rose);">Failed to load: ${esc(err.message)}</div></div>`;
    }
  }

  function paint() {
    const route = parseRoute();
    const views = {
      overview: overviewView,
      runs: runsView,
      run: runDetailView,
      repos: reposView,
      repo: repoDetailView,
      settings: settingsView,
      observability: observabilityView,
      docs: docsView,
    };
    app.innerHTML = (views[route.name] || overviewView)();
    bindEvents();
  }

  // ---------------------------------------------------------------- Event Handlers
  function bindEvents() {
    document.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (el.dataset.act === "close-modal" && e.target.closest("[data-stop]")) return;
        e.stopPropagation();
        handleAction(el, e);
      });
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
    const id = el.dataset.id;

    if (act === "filter-runs") {
      state.runStatusFilter = el.dataset.filter;
      return paint();
    }

    if (act === "select-stage") {
      state.selectedStage = el.dataset.key;
      state.showFullLog = false;
      return paint();
    }

    if (act === "toggle-full-log") {
      state.showFullLog = !state.showFullLog;
      return paint();
    }

    if (act === "export-json") {
      if (!state.run) return;
      const blob = new Blob([JSON.stringify(state.run, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `chaosgate-run-${state.run.id}.json`;
      a.click();
      return;
    }

    if (act === "open-rollback") {
      state.modal = { kind: "rollback" };
      state.revertLoading = true;
      paint();
      try {
        state.revertData = await api.recovery(state.run.id);
      } catch (err) {
        toast("Recovery check failed: " + err.message, "err");
      } finally {
        state.revertLoading = false;
        paint();
      }
      return;
    }

    if (act === "execute-revert") {
      try {
        el.disabled = true;
        el.textContent = "Reverting…";
        const res = await api.revert(id);
        toast("Revert pull request opened successfully!");
        state.modal = null;
        if (res.pr_url) window.open(res.pr_url, "_blank");
      } catch (err) {
        toast("Rollback failed: " + err.message, "err");
      } finally {
        paint();
      }
      return;
    }

    if (act === "rerun" || act === "trigger-repo-run") {
      const repoId = id || state.repo?.id;
      const branch = document.getElementById("run-branch")?.value || "main";
      try {
        el.disabled = true;
        el.textContent = "Triggering…";
        const res = await api.runRepo(repoId, { branch });
        toast(`Release gate triggered on ${branch}`);
        go(`/runs/${res.run.id}`);
      } catch (err) {
        toast("Failed to run gate: " + err.message, "err");
      }
      return;
    }

    if (act === "open-connect-repo") {
      state.modal = { kind: "connect-repo" };
      return paint();
    }

    if (act === "close-modal") {
      state.modal = null;
      return paint();
    }

    if (act === "set-repo-tab") {
      state.repoTab = el.dataset.tab;
      return paint();
    }

    if (act === "open-file") {
      const p = el.dataset.path;
      if (!state.open.find((f) => f.path === p)) {
        const file = await api.readFile(state.repo.id, p);
        state.open.push({ path: p, content: file.content || "" });
      }
      state.activePath = p;
      return paint();
    }

    if (act === "save-file") {
      const editor = document.getElementById("editor");
      if (!editor || !state.activePath) return;
      await api.saveFile(state.repo.id, state.activePath, editor.value);
      const f = state.open.find((x) => x.path === state.activePath);
      if (f) f.content = editor.value;
      toast(`Saved ${state.activePath}`);
      return;
    }

    if (act === "refresh-tree") {
      state.tree = await api.files(state.repo.id);
      return paint();
    }

    if (act === "toggle-policy") {
      const key = el.dataset.key;
      state.policy[key] = !state.policy[key];
      el.classList.toggle("on", state.policy[key]);
      return;
    }

    if (act === "publish-grafana") {
      try {
        el.disabled = true;
        el.textContent = "Publishing…";
        await api.publishDashboard();
        toast("Grafana dashboard published to provisioned instance!");
      } catch (err) {
        toast("Publish failed: " + err.message, "err");
      } finally {
        el.disabled = false;
        el.textContent = "Publish Grafana dashboard";
      }
      return;
    }
  }

  async function handleForm(form) {
    const kind = form.dataset.form;
    if (kind === "save-policy") {
      const fd = new FormData(form);
      const payload = {
        ...state.policy,
        max_p95_ms: Number(fd.get("max_p95_ms") || 300),
        max_error_rate_pct: Number(fd.get("max_error_rate_pct") || 1.0),
      };
      const token = fd.get("github_token");
      if (token && !token.startsWith("••••")) {
        payload.github_token = token;
      }
      try {
        await api.savePolicy(payload);
        state.policy = (await api.policy()).policy;
        toast("Policies updated and saved securely.");
      } catch (err) {
        toast("Failed to save: " + err.message, "err");
      }
      return paint();
    }

    if (kind === "connect-repo") {
      const name = document.getElementById("connect-repo-name")?.value.trim();
      if (!name) return;
      try {
        const res = await api.addRepo(name);
        state.modal = null;
        toast(`Connected repository ${name}`);
        state.repos = (await api.repos()).repos;
        go(`/repos/${res.repo.id}`);
      } catch (err) {
        toast("Failed to connect repository: " + err.message, "err");
      }
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.modal) {
      state.modal = null;
      paint();
    }
  });

  render();
})();
