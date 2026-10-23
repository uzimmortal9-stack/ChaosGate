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
    policy: {},
    contract: "",
    observability: null,
    stream: null,
    
    // View state
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
    repos: () => api.req("/api/repos"),
    repo: (id) => api.req(`/api/repos/${id}`),
    addRepo: (full_name) => api.req("/api/repos", { method: "POST", body: { full_name } }),
    delRepo: (id) => api.req(`/api/repos/${id}`),
    runRepo: (id, body = {}) => api.req(`/api/repos/${id}/run`, { method: "POST", body }),

    runs: (repoId) => api.req(repoId ? `/api/runs?repo_id=${repoId}` : "/api/runs"),
    run: (id) => api.req(`/api/runs/${id}`),
    artifacts: (id) => api.req(`/api/runs/${id}/artifacts`),
    recovery: (id) => api.req(`/api/runs/${id}/recovery`),
    revert: (id) => api.req(`/api/runs/${id}/revert`, { method: "POST" }),

    policy: () => api.req("/api/policy"),
    savePolicy: (body) => api.req("/api/policy", { method: "PUT", body }),
    contract: () => api.req("/api/contract"),
    observability: () => api.req("/api/observability"),
    publishDashboard: () => api.req("/api/observability/dashboard/publish", { method: "POST" }),

    // Workspace
    files: (id, path = "") => api.req(`/api/repos/${id}/files?path=${encodeURIComponent(path)}`),
    readFile: (id, path) => api.req(`/api/repos/${id}/file?path=${encodeURIComponent(path)}`),
    saveFile: (id, path, content) => api.req(`/api/repos/${id}/file`, { method: "PUT", body: { path, content } }),
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
    }, 3500);
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

  // ---------------------------------------------------------------- Minimal Visual Components
  function Score(value, size = 36) {
    const num = Math.round(Number(value) || 0);
    const r = size / 2 - (size > 80 ? 6 : 3);
    const c = 2 * Math.PI * r;
    const color = num >= 75 ? "#34d399" : num >= 50 ? "#fcd34d" : "#fb7185";
    const strokeWidth = size > 80 ? 6 : 2.5;
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

  function Verdict(conclusion) {
    const pass = conclusion === "PASS";
    const isRun = conclusion === "running" || conclusion === "queued";
    if (isRun) {
      return `<span class="verdict verdict-run"><span class="verdict-dot bg-indigo-400"></span>Running</span>`;
    }
    return `<span class="verdict ${pass ? "verdict-pass" : "verdict-fail"}">
      <span class="verdict-dot ${pass ? "bg-emerald-400" : "bg-rose-400"}"></span>
      ${pass ? "Passed" : "Blocked"}
    </span>`;
  }

  // Floating Pill Top Navigation
  function Nav() {
    const r = parseRoute();
    const here = r.name;
    const item = (href, label, key) => {
      const active = here === key || (key === "overview" && here === "landing");
      return `<a href="${href}" class="nav-pill-item ${active ? "active" : ""}">${label}</a>`;
    };

    return `
      <header class="nav-fixed-wrap">
        <nav class="nav-pill glass">
          <a href="/" class="brand-link" title="ChaosGate Home">
            <svg class="chaos-logo" width="118" height="26" viewBox="0 0 290 64" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="cg" gradientUnits="userSpaceOnUse" x1="4" y1="4" x2="60" y2="60">
                  <stop offset="0" stop-color="#ffffff"/>
                  <stop offset="0.55" stop-color="#f2edff"/>
                  <stop offset="1" stop-color="#c4b2ff"/>
                </linearGradient>
                <clipPath id="half"><rect x="27" y="0" width="64" height="64"/></clipPath>
                <mask id="gate"><rect width="64" height="64" fill="#fff"/><path d="M30 46 V31 a7 7 0 0 1 14 0 V46 Z" fill="#000"/></mask>
                <linearGradient id="tg" gradientUnits="userSpaceOnUse" x1="76" y1="0" x2="290" y2="0">
                  <stop offset="0" stop-color="#ffffff"/>
                  <stop offset="0.6" stop-color="#f2edff"/>
                  <stop offset="1" stop-color="#cdbfff"/>
                </linearGradient>
              </defs>
              <g fill="url(#cg)" mask="url(#gate)">
                <circle cx="33" cy="32" r="24" clip-path="url(#half)"/>
                <rect x="23.77" y="8.59" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.79" y="12.12" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.78" y="15.73" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.88" y="19.25" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.72" y="22.94" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.68" y="26.60" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.76" y="30.02" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.78" y="33.60" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.84" y="37.19" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.80" y="40.97" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.76" y="44.50" width="2.61" height="2.61" rx="0.6"/>
                <rect x="23.80" y="48.05" width="2.61" height="2.61" rx="0.6"/>
                <rect x="20.24" y="22.85" width="2.42" height="2.42" rx="0.6"/>
                <rect x="19.89" y="26.53" width="2.42" height="2.42" rx="0.6"/>
                <rect x="19.76" y="34.02" width="2.42" height="2.42" rx="0.6"/>
                <rect x="20.25" y="37.66" width="2.42" height="2.42" rx="0.6"/>
                <rect x="19.74" y="40.92" width="2.42" height="2.42" rx="0.6"/>
                <rect x="19.98" y="44.78" width="2.42" height="2.42" rx="0.6"/>
                <rect x="20.33" y="48.08" width="2.42" height="2.42" rx="0.6"/>
                <rect x="16.62" y="22.65" width="2.23" height="2.23" rx="0.6"/>
                <rect x="16.01" y="26.33" width="2.23" height="2.23" rx="0.6"/>
                <rect x="16.68" y="34.14" width="2.23" height="2.23" rx="0.6"/>
                <rect x="16.18" y="37.06" width="2.23" height="2.23" rx="0.6"/>
                <rect x="16.65" y="40.83" width="2.23" height="2.23" rx="0.6"/>
                <rect x="12.02" y="19.14" width="2.04" height="2.04" rx="0.6"/>
                <rect x="11.86" y="33.54" width="2.04" height="2.04" rx="0.6"/>
                <rect x="12.19" y="37.32" width="2.04" height="2.04" rx="0.6"/>
                <rect x="13.27" y="40.55" width="2.04" height="2.04" rx="0.6"/>
              </g>
              <text x="74" y="42" fill="url(#tg)" font-family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="28" font-weight="600" letter-spacing="0.3">Chaos<tspan font-weight="300">Gate</tspan></text>
            </svg>
          </a>
          <div class="nav-pill-links">
            ${item("/", "Overview", "overview")}
            ${item("/runs", "Runs", "runs")}
            ${item("/repos", "Repositories", "repos")}
            ${item("/settings", "Policies", "settings")}
            ${item("/observability", "Observability", "observability")}
            ${item("/docs", "Contract", "docs")}
          </div>
        </nav>
      </header>`;
  }

  function Shell(inner, breadcrumb = null) {
    return `
      ${Nav()}
      <main class="app-main">
        ${breadcrumb ? `
          <div class="page-nav-bar rise">
            <a href="${breadcrumb.href}" class="back-link">
              <span>←</span> ${esc(breadcrumb.label)}
            </a>
            <span class="nav-separator">/</span>
            <span class="nav-current">${esc(breadcrumb.current)}</span>
          </div>
        ` : ""}
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
    
    const blockedRepos = repos.filter((r) => {
      const lr = r.last_run || (runs.find((x) => x.repo_id === r.id || x.repo?.id === r.id));
      return lr && lr.conclusion === "FAIL";
    });
    const passRate = s.pass_rate != null ? Math.round(s.pass_rate) : (s.runs ? Math.round((s.passed / s.runs) * 100) : 0);

    return Shell(`
      <div class="space-y-6">
        <section class="rise">
          <p style="font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-dim); margin-bottom:8px;">Release Health</p>
          <h1 class="hero-headline">
            ${blockedRepos.length === 0 ? "All checks clear." : `${blockedRepos.length} ${blockedRepos.length === 1 ? "repository" : "repositories"} blocked`}
          </h1>
        </section>

        <div class="grid-3">
          <div class="glass lift stat-panel rise">
            <p class="stat-label">Pass rate</p>
            <p class="stat-value">${passRate}%</p>
          </div>
          <div class="glass lift stat-panel rise">
            <p class="stat-label">p95 SLA</p>
            <p class="stat-value">${maxP95}<span style="font-size:16px; font-weight:400; color:var(--text-dim); margin-left:2px;">ms</span></p>
          </div>
          <div class="glass lift stat-panel rise">
            <p class="stat-label">Repositories</p>
            <p class="stat-value">${repos.length}</p>
          </div>
        </div>

        ${blockedRepos.length > 0 ? `
          <div class="grid-2">
            ${blockedRepos.map((r) => {
              const lr = r.last_run || runs.find((x) => x.repo_id === r.id || x.repo?.id === r.id) || {};
              return `
                <a href="/runs/${lr.id || ''}" class="glass lift block" style="padding:16px 20px; border-radius:var(--radius-lg);">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:600; font-size:14.5px;">${esc(r.name || r.full_name)}</span>
                    ${Verdict("FAIL")}
                  </div>
                  <p style="margin-top:6px; font-size:12.5px; color:var(--text-dim);">
                    ${lr.pr_number ? `PR #${lr.pr_number}` : (lr.branch || "main")} · ${ago(lr.created_at)}
                  </p>
                </a>
              `;
            }).join("")}
          </div>
        ` : ""}

        <div class="glass rise" style="overflow:hidden;">
          <div style="display:flex; justify-content:space-between; align-items:center; padding:18px 22px 14px;">
            <h2 style="font-size:15px; font-weight:600;">Recent runs</h2>
            <a href="/runs" style="font-size:13px; color:var(--text-muted); transition:color 0.2s;">View all →</a>
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
          </div>
        </div>

        <div style="display:flex; gap:6px; margin-bottom:14px;">
          <button data-act="filter-runs" data-filter="all" class="filter-tab ${filter === "all" ? "active" : ""}">
            All <span style="opacity:0.6; margin-left:4px;">${all.length}</span>
          </button>
          <button data-act="filter-runs" data-filter="pass" class="filter-tab ${filter === "pass" ? "active" : ""}">
            Passed <span style="opacity:0.6; margin-left:4px;">${passCount}</span>
          </button>
          <button data-act="filter-runs" data-filter="fail" class="filter-tab ${filter === "fail" ? "active" : ""}">
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
              ${Score(r.resilience_score ?? r.score, 38)}
              <div class="run-main-info">
                <p class="run-commit-msg">${esc(r.commit_message || (r.pr_number ? `Pull Request #${r.pr_number}` : "Manual check"))}</p>
                <p class="run-meta">
                  <span class="run-meta-repo">${esc(r.repo?.name || r.repo?.full_name || "repo")}</span> · 
                  ${r.pr_number ? `#${r.pr_number}` : (r.branch || "main")} · 
                  ${ago(r.created_at || r.started_at)}
                </p>
              </div>
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
    const currentStage = stages.find((s) => s.key === openStageKey) || stages[0] || {};

    const breadcrumb = {
      href: "/runs",
      label: "Runs",
      current: run.commit_sha ? run.commit_sha.slice(0, 7) : run.id
    };

    return Shell(`
      <div class="space-y-5">
        <!-- Hero Panel with Glow Orb -->
        <div class="glass run-hero-panel rise">
          <div class="run-hero-glow ${pass ? "glow-pass" : "glow-fail"}"></div>
          <div class="run-hero-flex">
            ${Score(run.resilience_score ?? run.score, 88)}
            <div style="min-width:0; flex:1;">
              <p style="font-size:13px; font-weight:600; color:${pass ? "var(--emerald)" : "var(--rose)"};">
                ${pass ? "MERGE ALLOWED" : "MERGE BLOCKED"}
              </p>
              <h1 class="run-hero-title">${esc(run.commit_message || "Manual gate verification")}</h1>
              <p class="run-hero-meta">
                ${esc(run.repo?.name || run.repo?.full_name || "repo")} · 
                ${run.pr_number ? `PR #${run.pr_number}` : (run.branch || "main")} · 
                <span class="font-mono">${esc((run.commit_sha || "").slice(0, 7))}</span> · 
                ${ago(run.created_at || run.started_at)}
              </p>
            </div>
            <div style="display:flex; gap:8px;">
              <button data-act="export-json" class="btn-ghost">Export</button>
              ${pass ? `<button data-act="open-rollback" class="btn-ghost">Roll back</button>` : ""}
              <button data-act="rerun" data-id="${run.repo_id || run.repo?.id}" class="btn-primary">Re-run</button>
            </div>
          </div>
        </div>

        <!-- Failure Callout Banner (Clean single banner) -->
        ${failedStages.length > 0 ? `
          <div class="fail-banner glass rise">
            <span class="fail-banner-dot"></span>
            <div style="min-width:0; flex:1;">
              <strong style="font-size:13px; color:var(--rose);">${esc(failedStages[0].name)}:</strong>
              <span style="font-size:13px; color:#fff0f3; margin-left:6px;">${esc(failedStages[0].summary || "Gate blocked by policy")}</span>
            </div>
            <button data-act="select-stage" data-key="${esc(failedStages[0].key)}" class="btn-ghost" style="padding:3px 12px; font-size:12px; border:1px solid var(--rose-border); color:var(--rose);">Inspect Log</button>
          </div>
        ` : ""}

        <!-- 4 Metric Cards -->
        <div class="grid-4">
          <div class="glass stat-panel">
            <p class="stat-label">p95 Latency</p>
            <p class="stat-value" style="font-size:22px;">${loadMetrics.p95_ms != null ? `${loadMetrics.p95_ms}ms` : "—"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Error Rate</p>
            <p class="stat-value" style="font-size:22px;">${loadMetrics.error_rate_pct != null ? `${loadMetrics.error_rate_pct}%` : "0.0%"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Recovery</p>
            <p class="stat-value" style="font-size:22px;">${chaosMetrics.recovery_ms != null ? `${chaosMetrics.recovery_ms}ms` : "—"}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Duration</p>
            <p class="stat-value" style="font-size:22px;">${dur(run.duration_ms ? run.duration_ms / 1000 : 18)}</p>
          </div>
        </div>

        <!-- Pipeline Stages Section -->
        <div class="glass" style="padding:22px 24px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <h2 style="font-size:15px; font-weight:600;">Pipeline Stages</h2>
              <span style="font-size:12px; color:var(--text-dim);">(${stages.length})</span>
            </div>
            <button data-act="toggle-full-log" class="btn-ghost" style="font-size:12px; padding:3px 10px;">
              ${state.showFullLog ? "← Back to Stage Inspector" : "View Full Log"}
            </button>
          </div>

          <!-- Interactive Stage Pipeline -->
          <div class="stage-pipeline-nav">
            ${stages.map((s) => {
              const isSel = openStageKey === s.key && !state.showFullLog;
              const dotColor = s.status === "passed" ? "bg-emerald-400" : s.status === "failed" ? "bg-rose-400" : s.status === "degraded" ? "bg-amber-300" : "bg-indigo-400";
              return `
                <button 
                  data-act="select-stage" 
                  data-key="${esc(s.key)}" 
                  class="stage-pill-btn ${s.status} ${isSel ? "active" : ""}">
                  <span class="stage-pill-dot ${dotColor}"></span>
                  <span>${esc(s.key)}</span>
                  ${s.duration_ms ? `<span style="font-size:11px; opacity:0.55; margin-left:2px;">${(s.duration_ms / 1000).toFixed(1)}s</span>` : ""}
                </button>
              `;
            }).join("")}
          </div>

          ${state.showFullLog ? `
            <div class="terminal-box" id="term" style="margin-top:14px; max-height:360px;">
              ${stages.map((s) => {
                const logs = s.logs || `${s.name} ${s.status}\n`;
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
            <div class="stage-inspector rise" style="margin-top:14px;">
              <div class="stage-inspector-head">
                <div style="display:flex; align-items:center; gap:10px;">
                  <span class="stage-pill-dot ${currentStage.status === "passed" ? "bg-emerald-400" : currentStage.status === "failed" ? "bg-rose-400" : currentStage.status === "degraded" ? "bg-amber-300" : "bg-indigo-400"}"></span>
                  <strong style="font-size:14.5px;">${esc(currentStage.name || currentStage.key)}</strong>
                  <span style="font-size:12px; color:var(--text-dim);">${esc(currentStage.key)} · ${currentStage.duration_ms ? `${(currentStage.duration_ms / 1000).toFixed(2)}s` : "completed"}</span>
                </div>
                <span class="verdict ${currentStage.status === "passed" ? "verdict-pass" : "verdict-fail"}">${(currentStage.status || "ready").toUpperCase()}</span>
              </div>
              <p style="font-size:13px; color:var(--text-muted); margin-bottom:12px;">${esc(currentStage.summary || "Stage completed.")}</p>
              ${currentStage.metrics && Object.keys(currentStage.metrics).length > 0 ? `
                <div class="metric-pills">
                  ${Object.entries(currentStage.metrics).map(([k, v]) => {
                    const displayVal = (typeof v === "object" && v !== null) ? (v.total ?? v.count ?? Object.keys(v).length) : v;
                    return `<span class="metric-pill">${esc(k.replace(/_/g, " "))}: <strong>${esc(displayVal)}</strong></span>`;
                  }).join("")}
                </div>
              ` : ""}
              <pre class="terminal-box" style="max-height:220px; font-size:11.5px; padding:12px;">${esc(currentStage.logs || `${currentStage.name || currentStage.key} completed.`)}</pre>
            </div>
          `}
        </div>
      </div>
    `, breadcrumb);
  }

  // 4. Repositories Screen
  function reposView() {
    const repos = state.repos || [];
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Repositories</h1>
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
                <div class="repo-tags">
                  <span class="tag-pill">${esc(r.runtime || "Python")}</span>
                  ${r.framework ? `<span class="tag-pill">${esc(r.framework)}</span>` : ""}
                  <span style="margin-left:auto; font-size:11.5px;">${lr ? ago(lr.created_at) : (r.default_branch || "main")}</span>
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

    const breadcrumb = {
      href: "/repos",
      label: "Repositories",
      current: repo.name || repo.full_name
    };

    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">${esc(repo.name || repo.full_name)}</h1>
            <p style="font-size:13px; color:var(--text-dim); margin-top:4px;">${esc(repo.runtime || "Python")}${repo.framework ? ` · ${esc(repo.framework)}` : ""} · ${esc(repo.default_branch || "main")}</p>
          </div>
          <div class="glass" style="display:flex; align-items:center; gap:8px; padding:3px 5px 3px 14px; border-radius:var(--radius-full);">
            <span style="font-size:12.5px; color:var(--text-dim);">branch</span>
            <input id="run-branch" value="${esc(repo.default_branch || "main")}" style="width:100px; font-size:13px; color:#fff;" />
            <button data-act="trigger-repo-run" data-id="${repo.id}" class="btn-primary" style="padding:6px 14px; font-size:12.5px;">Run gate</button>
          </div>
        </div>

        <div class="grid-3">
          <div class="glass stat-panel">
            <p class="stat-label">Avg. score</p>
            <p class="stat-value" style="font-size:24px;">${avgScore}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Total runs</p>
            <p class="stat-value" style="font-size:24px;">${runs.length}</p>
          </div>
          <div class="glass stat-panel">
            <p class="stat-label">Trend</p>
            <div class="score-trend-bar">
              ${scored.length ? scored.map((r) => `
                <div class="score-trend-seg" style="height:${Math.max(12, r.resilience_score ?? r.score ?? 50)}%; background:${(r.resilience_score ?? r.score ?? 0) >= 75 ? "var(--emerald)" : "var(--rose)"};"></div>
              `).join("") : `<div class="score-trend-seg" style="height:80%; background:var(--emerald);"></div><div class="score-trend-seg" style="height:90%; background:var(--emerald);"></div>`}
            </div>
          </div>
        </div>

        <!-- Navigation Tabs: History vs Workspace Code Editor -->
        <div style="display:flex; gap:6px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:10px;">
          <button data-act="set-repo-tab" data-tab="runs" class="filter-tab ${activeTab === "runs" ? "active" : ""}">Runs</button>
          <button data-act="set-repo-tab" data-tab="editor" class="filter-tab ${activeTab === "editor" ? "active" : ""}">Workspace Editor</button>
        </div>

        ${activeTab === "runs" ? `
          <div class="glass rise" style="overflow:hidden;">
            ${RunList(runs)}
          </div>
        ` : WorkspaceEditor(repo)}
      </div>
    `, breadcrumb);
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
          `).join("") : `<p style="padding:16px 8px; font-size:12px; color:var(--text-dim);">No files mounted.</p>`}
        </div>
        <div class="ws-editor-main">
          <div class="ws-editor-bar">
            <span>${esc(state.activePath || "No file opened")}</span>
            ${activeFile ? `<button data-act="save-file" class="btn-primary" style="padding:4px 14px; font-size:12px;">Save</button>` : ""}
          </div>
          <textarea id="editor" class="ws-textarea" placeholder="Select a file to inspect or edit…">${esc(activeFile?.content || "")}</textarea>
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
          </div>
        </div>

        <form data-form="save-policy" class="space-y-4">
          <div class="glass policy-group">
            <div class="policy-row">
              <span class="policy-label">p95 Latency SLA</span>
              <div class="num-input-wrap">
                <input name="max_p95_ms" type="number" class="num-input" value="${p.max_p95_ms || 300}" />ms
              </div>
            </div>

            <div class="policy-row">
              <span class="policy-label">Max Error Rate</span>
              <div class="num-input-wrap">
                <input name="max_error_rate_pct" type="number" step="0.1" class="num-input" value="${p.max_error_rate_pct || 1.0}" />%
              </div>
            </div>
          </div>

          <div class="glass policy-group">
            <div class="policy-row">
              <span class="policy-label">Block on Secrets</span>
              <button type="button" class="toggle-btn ${p.fail_on_secrets !== false ? "on" : ""}" data-act="toggle-policy" data-key="fail_on_secrets">
                <span class="toggle-thumb"></span>
              </button>
            </div>

            <div class="policy-row">
              <span class="policy-label">Fail when Degraded</span>
              <button type="button" class="toggle-btn ${p.fail_on_degraded ? "on" : ""}" data-act="toggle-policy" data-key="fail_on_degraded">
                <span class="toggle-thumb"></span>
              </button>
            </div>

            <div class="policy-row">
              <span class="policy-label">Warn Unpinned Dependencies</span>
              <button type="button" class="toggle-btn ${p.warn_unpinned_deps !== false ? "on" : ""}" data-act="toggle-policy" data-key="warn_unpinned_deps">
                <span class="toggle-thumb"></span>
              </button>
            </div>
          </div>

          <div class="glass policy-group">
            <div class="policy-row">
              <span class="policy-label">GitHub Token</span>
              <input name="github_token" type="password" placeholder="ghp_••••••••••••" value="${p.github_token ? "••••••••••••••••" : ""}" class="text-input" style="width:200px;" />
            </div>
          </div>

          <div style="display:flex; justify-content:flex-end;">
            <button type="submit" class="btn-primary">Save changes</button>
          </div>
        </form>
      </div>
    `);
  }

  // 7. Observability Screen
  function observabilityView() {
    const tools = state.me?.toolchain || {};
    return Shell(`
      <div class="space-y-5">
        <div class="page-header rise">
          <div>
            <h1 class="page-title">Observability</h1>
          </div>
          <div style="display:flex; gap:8px;">
            <a href="/metrics" target="_blank" class="btn-ghost" style="padding:6px 14px; font-size:13px;">/metrics</a>
            <button data-act="publish-grafana" class="btn-primary">Publish Grafana</button>
          </div>
        </div>

        <div class="glass" style="padding:20px;">
          <h2 style="font-size:14px; font-weight:600; margin-bottom:14px; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-dim);">Toolchain Health</h2>
          <div class="grid-3" style="gap:10px;">
            ${Object.entries(tools).map(([name, t]) => `
              <div class="glass" style="padding:12px 16px; display:flex; justify-content:space-between; align-items:center; border-radius:var(--radius-md);">
                <strong style="font-size:13.5px;">${esc(name)}</strong>
                <span class="verdict ${t.available ? "verdict-pass" : "verdict-fail"}">${t.available ? "Ready" : "Degraded"}</span>
              </div>
            `).join("")}
          </div>
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
            <h1 class="page-title">Contract Schema</h1>
          </div>
        </div>
        <div class="glass" style="padding:20px;">
          <pre class="terminal-box" style="font-size:12px; line-height:1.6;">${esc(state.contract || `# ChaosGate Contract Schema v2
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
              <p style="padding:32px 0; text-align:center; color:var(--text-dim); font-size:14px;">Analyzing 3-way merge…</p>
            ` : data ? `
              <p style="font-size:13.5px; font-weight:500; color:${data.clean ? "var(--emerald)" : "var(--amber)"};">
                ${data.clean ? "Clean revert — no merge conflicts." : "Collision detected — quarantined."}
              </p>
              <ul class="revert-file-list">
                ${(data.files || []).map((f) => `
                  <li class="revert-file-item">
                    <span class="font-mono">${esc(f.path)}</span>
                    <span style="color:${f.state === "clean" ? "var(--emerald)" : "var(--amber)"}; font-size:12px;">
                      ${f.state === "clean" ? "clean" : `conflict`}
                    </span>
                  </li>
                `).join("")}
              </ul>
              ${data.clean ? `
                <button data-act="execute-revert" data-id="${run.id}" class="btn-primary" style="width:100%; margin-top:16px; padding:10px 0;">
                  Open 1-Click Revert PR
                </button>
              ` : `
                <div class="revert-cli-box">
                  ${(data.cli || []).map((cmd) => `<div>$ ${esc(cmd)}</div>`).join("")}
                </div>
              `}
            ` : `<p style="padding:24px 0; text-align:center;">Failed to check rollback.</p>`}
          </div>
        </div>
      `;
    }

    if (state.modal.kind === "connect-repo") {
      return `
        <div class="modal-backdrop" data-act="close-modal">
          <div class="modal-sheet glass rise" data-stop>
            <div class="modal-sheet-head">
              <h3>Connect Repository</h3>
              <button class="close-btn" data-act="close-modal">✕</button>
            </div>
            <form data-form="connect-repo" class="space-y-4">
              <div>
                <input id="connect-repo-name" class="text-input" style="width:100%;" placeholder="owner/repo" required />
              </div>
              <div style="display:flex; justify-content:flex-end; gap:8px;">
                <button type="button" data-act="close-modal" class="btn-ghost">Cancel</button>
                <button type="submit" class="btn-primary">Add</button>
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
      app.innerHTML = Shell(`<div class="glass" style="padding:24px; color:var(--rose);">Failed to load: ${esc(err.message)}</div>`);
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
        toast("Revert pull request opened!");
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
        el.textContent = "Running…";
        const res = await api.runRepo(repoId, { branch });
        toast(`Gate check started`);
        go(`/runs/${res.run.id}`);
      } catch (err) {
        toast("Failed: " + err.message, "err");
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
        toast("Grafana dashboard published!");
      } catch (err) {
        toast("Publish failed: " + err.message, "err");
      } finally {
        el.disabled = false;
        el.textContent = "Publish Grafana";
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
        toast("Policies saved.");
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
        toast(`Connected ${name}`);
        state.repos = (await api.repos()).repos;
        go(`/repos/${res.repo.id}`);
      } catch (err) {
        toast("Failed: " + err.message, "err");
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
