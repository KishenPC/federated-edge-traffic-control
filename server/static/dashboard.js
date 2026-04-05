/* ── Dashboard client ─────────────────────────────────── */
(function () {
  "use strict";

  const POLL_MS = 3000;
  const LANE_LABELS = ["Lane 1", "Lane 2", "Lane 3", "Lane 4"];
  const LANE_COLORS = ["lane-1", "lane-2", "lane-3", "lane-4"];
  const NODE_IDS = ["esp-a", "esp-b"];

  let currentLogFilter = "all";
  let allLogs = [];

  /* ── Helpers ────────────────────────────────────────── */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function fmt(val, decimals = 2) {
    if (val == null || val === "—") return "—";
    return Number(val).toFixed(decimals);
  }

  function relativeTime(iso) {
    if (!iso) return "—";
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 0) return "just now";
    if (diff < 60) return Math.floor(diff) + "s ago";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    return Math.floor(diff / 3600) + "h ago";
  }

  function shortTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  /* ── Bar Chart Renderer ─────────────────────────────── */
  function renderBars(containerId, values, maxVal) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!values || values.length === 0) {
      el.innerHTML = '<span class="hint">No data</span>';
      return;
    }
    const cap = maxVal || Math.max(...values, 0.01);
    el.innerHTML = values
      .map((v, i) => {
        const pct = Math.min((v / cap) * 100, 100);
        return `
        <div class="bar-wrapper">
          <span class="bar-value">${fmt(v)}</span>
          <div class="bar ${LANE_COLORS[i]}" style="height:${Math.max(pct, 5)}%"></div>
          <span class="bar-label">${LANE_LABELS[i]}</span>
        </div>`;
      })
      .join("");
  }

  /* ── Clock ──────────────────────────────────────────── */
  function tickClock() {
    const el = $("#header-clock");
    if (el) el.textContent = new Date().toLocaleTimeString();
  }
  setInterval(tickClock, 1000);
  tickClock();

  /* ── Status Polling ─────────────────────────────────── */
  async function pollStatus() {
    try {
      const res = await fetch("/status");
      if (!res.ok) throw new Error("status " + res.status);
      const data = await res.json();
      updateGlobalCard(data);
      updateNodeCards(data);
      setServerOnline(true);
    } catch (err) {
      setServerOnline(false);
    }
  }

  function setServerOnline(ok) {
    const badge = $("#server-status-badge");
    if (ok) {
      badge.textContent = "Online";
      badge.classList.remove("offline");
    } else {
      badge.textContent = "Offline";
      badge.classList.add("offline");
    }
  }

  function updateGlobalCard(data) {
    $("#global-round").textContent = "Round " + (data.round ?? 0);
    $("#global-updated").textContent = relativeTime(data.updated_at);
    $("#global-pending").textContent = (data.pending_nodes || []).join(", ") || "none";
    $("#global-min-clients").textContent = data.min_clients ?? "—";
    renderBars("global-weights-chart", data.weights, 3);
  }

  function updateNodeCards(data) {
    const metrics = data.latest_node_metrics || {};
    NODE_IDS.forEach((nodeId) => {
      const m = metrics[nodeId];
      const statusEl = $(`#status-${nodeId}`);
      const phasesEl = $(`#phases-${nodeId}`);
      const lossEl = $(`#loss-${nodeId}`);
      const seenEl = $(`#seen-${nodeId}`);
      const roundEl = $(`#round-${nodeId}`);

      if (!m) {
        statusEl.textContent = "Offline";
        statusEl.className = "node-status offline";
        phasesEl.textContent = "—";
        lossEl.textContent = "—";
        seenEl.textContent = "—";
        roundEl.textContent = "—";
        renderBars(`demand-${nodeId}`, [], 1);
        return;
      }

      // Staleness check: > 30s since last update
      const secsSince = (Date.now() - new Date(m.received_at).getTime()) / 1000;
      if (secsSince > 60) {
        statusEl.textContent = "Offline";
        statusEl.className = "node-status offline";
      } else if (secsSince > 30) {
        statusEl.textContent = "Stale";
        statusEl.className = "node-status stale";
      } else {
        statusEl.textContent = "Online";
        statusEl.className = "node-status online";
      }

      phasesEl.textContent = m.phase_count ?? "—";
      lossEl.textContent = fmt(m.cycle_loss);
      seenEl.textContent = relativeTime(m.received_at);
      roundEl.textContent = m.round ?? "—";
      renderBars(`demand-${nodeId}`, m.demand || [], 1);
    });
  }

  /* ── Error / Event Log ──────────────────────────────── */
  async function pollErrors() {
    try {
      const res = await fetch("/api/errors");
      if (!res.ok) return;
      allLogs = await res.json();
      renderLogs();
    } catch {
      // silent
    }
  }

  function renderLogs() {
    const container = $("#log-container");
    const filtered =
      currentLogFilter === "all"
        ? allLogs
        : allLogs.filter((e) => e.level === currentLogFilter);

    if (filtered.length === 0) {
      container.innerHTML = '<p class="empty-row" id="log-empty">No events match this filter.</p>';
      return;
    }

    container.innerHTML = filtered
      .slice()
      .reverse()
      .map(
        (e) => `
      <div class="log-entry ${e.level}">
        <span class="log-time">${shortTime(e.time)}</span>
        <span class="log-level ${e.level}">${e.level}</span>
        <span class="log-msg">${escapeHtml(e.message)}</span>
      </div>`
      )
      .join("");
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  $$(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentLogFilter = btn.dataset.level;
      renderLogs();
    });
  });

  /* ── Aggregation History ────────────────────────────── */
  async function pollHistory() {
    try {
      const res = await fetch("/api/history");
      if (!res.ok) return;
      const history = await res.json();
      renderHistory(history);
    } catch {
      // silent
    }
  }

  function renderHistory(history) {
    const tbody = $("#history-tbody");
    if (!history || history.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="empty-row">No aggregation rounds yet.</td></tr>';
      return;
    }
    tbody.innerHTML = history
      .slice()
      .reverse()
      .map(
        (r) => `
      <tr>
        <td><strong>${r.round}</strong></td>
        <td>${fmt(r.weights[0])}</td>
        <td>${fmt(r.weights[1])}</td>
        <td>${fmt(r.weights[2])}</td>
        <td>${fmt(r.weights[3])}</td>
        <td>${(r.contributors || []).join(", ")}</td>
        <td>${shortTime(r.time)}</td>
      </tr>`
      )
      .join("");
  }

  /* ── Test Runner ────────────────────────────────────── */
  const testBtn = $("#run-tests-btn");
  testBtn.addEventListener("click", async () => {
    testBtn.disabled = true;
    testBtn.textContent = "Running…";
    const hint = $("#test-hint");
    const results = $("#test-results");
    hint.style.display = "none";

    try {
      const res = await fetch("/api/test");
      if (!res.ok) throw new Error("Test endpoint returned " + res.status);
      const data = await res.json();
      renderTestResults(data);
    } catch (err) {
      results.innerHTML =
        '<div class="test-summary has-fail">Failed to reach test endpoint: ' +
        escapeHtml(err.message) +
        "</div>";
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "Run Tests";
    }
  });

  function renderTestResults(data) {
    const el = $("#test-results");
    const checks = data.checks || [];
    const allPassed = checks.every((c) => c.passed);

    let html = `<div class="test-summary ${allPassed ? "all-pass" : "has-fail"}">
      ${data.passed}/${data.total} checks passed
      ${data.run_at ? " &mdash; " + shortTime(data.run_at) : ""}
    </div>`;

    checks.forEach((c) => {
      html += `
      <div class="test-row">
        <span class="test-badge ${c.passed ? "pass" : "fail"}">${c.passed ? "PASS" : "FAIL"}</span>
        <span class="test-name">${escapeHtml(c.name)}</span>
        <span class="test-detail">${escapeHtml(c.detail || "")}</span>
      </div>`;
    });

    el.innerHTML = html;
  }

  /* ── Polling Loop ───────────────────────────────────── */
  async function poll() {
    await Promise.all([pollStatus(), pollErrors(), pollHistory()]);
  }

  poll();
  setInterval(poll, POLL_MS);
})();
