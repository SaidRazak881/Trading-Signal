/* Signal Desk — frontend controller */
(() => {
  "use strict";

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  const state = {
    tab: "active",
    stats: null,
    active: [],
    history: [],
    polling: null,
    scanning: false,
  };

  // ── API ────────────────────────────────────────────────
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
  }

  // ── Helpers ────────────────────────────────────────────
  function fmtPrice(n) {
    if (n == null || Number.isNaN(+n)) return "—";
    const v = +n;
    if (v >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (v >= 1) return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
    if (v >= 0.01) return v.toFixed(5);
    return v.toPrecision(4);
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(+n)) return "—";
    const s = (+n).toFixed(2);
    return (+n >= 0 ? "+" : "") + s + "%";
  }

  function relTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    const d = Date.now() - t;
    if (d < 0) {
      const ahead = -d;
      if (ahead < 60_000) return "soon";
      if (ahead < 3_600_000) return `in ${Math.round(ahead / 60_000)}m`;
      return `in ${Math.round(ahead / 3_600_000)}h`;
    }
    if (d < 60_000) return "just now";
    if (d < 3_600_000) return `${Math.round(d / 60_000)}m ago`;
    if (d < 86_400_000) return `${Math.round(d / 3_600_000)}h ago`;
    return `${Math.round(d / 86_400_000)}d ago`;
  }

  function toast(msg, ms = 2400) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), ms);
  }

  function pairLabel(sym) {
    if (!sym) return "—";
    return sym.endsWith("USDT") ? sym.slice(0, -4) + "/USDT" : sym;
  }

  /** Progress of price between SL and TP (0 = at SL, 1 = at TP). */
  function progressPos(sig) {
    const px = +sig.current_price || +sig.trigger_price;
    const tp = +sig.tp_price;
    const sl = +sig.sl_price;
    const span = Math.abs(tp - sl);
    if (!span) return 0.5;
    if (sig.direction === "LONG") {
      return Math.min(1, Math.max(0, (px - sl) / span));
    }
    return Math.min(1, Math.max(0, (sl - px) / span));
  }

  function distPct(from, to) {
    if (!from) return 0;
    return ((to - from) / from) * 100;
  }

  // ── Render cards ───────────────────────────────────────
  function cardHTML(sig) {
    const dir = (sig.direction || "").toLowerCase();
    const st = (sig.status || "active").toLowerCase();
    const px = +sig.current_price || +sig.trigger_price;
    const toTp = distPct(px, +sig.tp_price);
    const toSl = distPct(px, +sig.sl_price);
    const pos = progressPos(sig) * 100;
    const reasons = (sig.reasons || []).slice(0, 4);
    const age = relTime(sig.detected_at);

    return `
      <article class="sig-card ${dir} ${st}" data-id="${sig.id}" role="button" tabindex="0">
        <div class="sig-head">
          <div>
            <div class="sig-pair">${pairLabel(sig.symbol)}</div>
            <div class="sig-meta">${age} · RR ${sig.risk_reward ?? "—"} · ${sig.timeframe || "15m"}</div>
          </div>
          <div class="badges">
            <span class="badge ${dir}">${sig.direction}</span>
            <span class="badge ${st}">${st}</span>
            <span class="badge score">${Math.round(sig.signal_score)} pts</span>
          </div>
        </div>

        <div class="levels">
          <div class="lvl"><span>Entry</span><strong>${fmtPrice(sig.trigger_price)}</strong></div>
          <div class="lvl tp"><span>TP</span><strong>${fmtPrice(sig.tp_price)}</strong></div>
          <div class="lvl sl"><span>SL</span><strong>${fmtPrice(sig.sl_price)}</strong></div>
        </div>

        <div class="progress-wrap">
          <div class="progress-labels">
            <span>SL ${fmtPct(toSl)}</span>
            <span class="lvl px" style="border:0;padding:0;background:0"><strong style="font-size:.75rem">${fmtPrice(px)}</strong></span>
            <span>TP ${fmtPct(toTp)}</span>
          </div>
          <div class="progress" aria-hidden="true">
            <div class="fill-sl" style="width:${Math.max(0, 100 - pos)}%"></div>
            <div class="fill-tp" style="width:${pos}%"></div>
            <i style="left:${pos}%"></i>
          </div>
        </div>

        ${reasons.length ? `<div class="tags">${reasons.map((r) => `<span class="tag">${escapeHtml(r)}</span>`).join("")}</div>` : ""}
      </article>
    `;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderActive() {
    const list = $("#activeList");
    const empty = $("#activeEmpty");
    const items = filterList(state.active.filter((s) => s.status === "active"));
    if (!items.length) {
      list.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    list.innerHTML = items.map(cardHTML).join("");
  }

  function renderHistory() {
    const list = $("#historyList");
    const empty = $("#historyEmpty");
    const items = filterList(
      state.history.filter((s) => s.status !== "active")
    );
    if (!items.length) {
      list.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");
    list.innerHTML = items.map(cardHTML).join("");
  }

  function filterList(items) {
    const st = $("#fStatus").value;
    const dir = $("#fDir").value;
    const q = ($("#fSymbol").value || "").trim().toUpperCase();
    return items.filter((s) => {
      if (st !== "all" && s.status !== st) return false;
      if (dir !== "all" && s.direction !== dir) return false;
      if (q && !(s.symbol || "").includes(q)) return false;
      return true;
    });
  }

  function renderStats() {
    const s = state.stats || {};
    $("#sActive").textContent = s.active ?? "—";
    $("#sWins").textContent = s.wins ?? "—";
    $("#sLosses").textContent = s.losses ?? "—";
    $("#sWinRate").textContent = s.win_rate != null ? s.win_rate + "%" : "—";
    $("#sExpired").textContent = s.expired ?? "—";
    $("#sAvgRR").textContent = s.avg_rr != null ? s.avg_rr + "R" : "—";

    const pill = $("#modePill");
    if (s.demo || s.data_mode === "demo") {
      pill.textContent = "DEMO";
      pill.classList.remove("hidden", "live");
    } else if (s.data_mode === "live") {
      pill.textContent = "LIVE";
      pill.classList.add("live");
      pill.classList.remove("hidden");
    } else {
      pill.classList.add("hidden");
    }

    const last = s.last_scan;
    if (last) {
      const when = relTime(last.finished_at || last.started_at);
      const modeTag = s.demo ? " · demo feed" : "";
      const msg =
        last.status === "running"
          ? "Scanning market…"
          : `Last scan ${when} · ${last.pairs_scanned || 0} pairs · ${last.signals_found || 0} hits${modeTag}`;
      $("#scanMeta").textContent = msg;
    } else {
      $("#scanMeta").textContent = "Waiting for first scan…";
    }

    // detailed panel
    $("#overviewKv").innerHTML = [
      ["Total signals", s.total_signals ?? 0],
      ["Avg score", s.avg_score ?? "—"],
      ["Active now", s.active ?? 0],
      ["Closed", (s.wins || 0) + (s.losses || 0)],
      ["Win rate", (s.win_rate ?? 0) + "%"],
      ["Avg RR", (s.avg_rr ?? 0) + "R"],
    ]
      .map(
        ([k, v]) =>
          `<div class="kv-item"><span>${k}</span><strong>${v}</strong></div>`
      )
      .join("");

    const byDir = s.by_direction || [];
    $("#byDir").innerHTML = byDir.length
      ? byDir
          .map((d) => {
            const total = Math.max(1, (d.wins || 0) + (d.losses || 0));
            const wp = ((d.wins || 0) / total) * 100;
            const lp = ((d.losses || 0) / total) * 100;
            return `
            <div class="bar-row">
              <div class="bar-lbl">${d.direction}</div>
              <div class="bar-track">
                <div class="w" style="width:${wp}%"></div>
                <div class="l" style="width:${lp}%"></div>
              </div>
              <div class="bar-num">${d.wins || 0}W / ${d.losses || 0}L</div>
            </div>`;
          })
          .join("")
      : `<p style="color:var(--muted);font-size:.85rem">No closed trades yet.</p>`;

    const tops = s.top_pairs || [];
    $("#topPairs").innerHTML = tops.length
      ? `<table class="pairs">
          <thead><tr><th>Pair</th><th>W</th><th>L</th><th>N</th><th>Score</th></tr></thead>
          <tbody>
            ${tops
              .map(
                (p) => `<tr>
              <td>${pairLabel(p.symbol)}</td>
              <td class="pos">${p.wins || 0}</td>
              <td class="neg">${p.losses || 0}</td>
              <td>${p.total || 0}</td>
              <td>${p.avg_score != null ? (+p.avg_score).toFixed(0) : "—"}</td>
            </tr>`
              )
              .join("")}
          </tbody>
        </table>`
      : `<p style="color:var(--muted);font-size:.85rem">No pair data yet.</p>`;

    const strong = s.strongest;
    const box = $("#strongest");
    if (strong) {
      box.innerHTML = cardHTML(strong);
    } else {
      box.innerHTML = `<p style="color:var(--muted);font-size:.85rem">No active signal.</p>`;
    }
  }

  // ── Detail sheet ───────────────────────────────────────
  async function openSheet(id) {
    const sheet = $("#sheet");
    const body = $("#sheetBody");
    body.innerHTML = `<div class="skel" style="height:200px"></div>`;
    sheet.classList.add("open");
    sheet.setAttribute("aria-hidden", "false");

    try {
      const data = await api(`/api/signals/${id}`);
      const sig = data.signal;
      if (!sig) {
        body.innerHTML = `<p>Signal not found.</p>`;
        return;
      }
      const events = data.events || [];
      const dir = (sig.direction || "").toLowerCase();
      const st = (sig.status || "").toLowerCase();

      body.innerHTML = `
        <div class="sheet-title">
          <div>
            <h2>${pairLabel(sig.symbol)}</h2>
            <div class="sig-meta">${sig.strategy_type || "trend_pullback"} · ${sig.timeframe}</div>
          </div>
          <div class="badges">
            <span class="badge ${dir}">${sig.direction}</span>
            <span class="badge ${st}">${st}</span>
          </div>
        </div>

        <div class="detail-grid">
          <div class="cell"><span>Score</span><strong>${sig.signal_score}</strong></div>
          <div class="cell"><span>RR</span><strong>${sig.risk_reward ?? "—"}R</strong></div>
          <div class="cell"><span>Entry</span><strong>${fmtPrice(sig.trigger_price)}</strong></div>
          <div class="cell"><span>Current</span><strong>${fmtPrice(sig.current_price)}</strong></div>
          <div class="cell"><span>Take Profit</span><strong style="color:var(--green)">${fmtPrice(sig.tp_price)}</strong></div>
          <div class="cell"><span>Stop Loss</span><strong style="color:var(--red)">${fmtPrice(sig.sl_price)}</strong></div>
          <div class="cell"><span>Detected</span><strong style="font-family:var(--font);font-size:.78rem">${formatFull(sig.detected_at)}</strong></div>
          <div class="cell"><span>Expires</span><strong style="font-family:var(--font);font-size:.78rem">${formatFull(sig.expires_at)}</strong></div>
          ${
            sig.closed_at
              ? `<div class="cell"><span>Closed</span><strong style="font-family:var(--font);font-size:.78rem">${formatFull(sig.closed_at)}</strong></div>
                 <div class="cell"><span>Close px</span><strong>${fmtPrice(sig.close_price)}</strong></div>`
              : ""
          }
        </div>

        <h3 style="font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Confluence reasons</h3>
        <ul class="reasons-list">
          ${(sig.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("") || "<li>No tags</li>"}
        </ul>

        ${
          sig.notes
            ? `<p style="margin-bottom:12px;color:var(--muted);font-size:.85rem"><strong style="color:var(--text)">Note:</strong> ${escapeHtml(sig.notes)}</p>`
            : ""
        }

        <h3 style="font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin:4px 0 10px">Timeline</h3>
        <div class="events">
          ${events
            .map(
              (e) => `
            <div class="event">
              <strong>${escapeHtml(e.event_type)}</strong>
              ${e.price != null ? ` @ ${fmtPrice(e.price)}` : ""}
              <time>${formatFull(e.event_time)}</time>
            </div>`
            )
            .join("") || `<div class="event">No events</div>`}
        </div>
      `;
    } catch (e) {
      body.innerHTML = `<p style="color:var(--red)">Failed to load signal.</p>`;
    }
  }

  function formatFull(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  function closeSheet() {
    const sheet = $("#sheet");
    sheet.classList.remove("open");
    sheet.setAttribute("aria-hidden", "true");
  }

  // ── Data load ──────────────────────────────────────────
  async function refresh() {
    const btn = $("#btnRefresh");
    btn.classList.add("spin");
    try {
      const [stats, active, all] = await Promise.all([
        api("/api/stats"),
        api("/api/signals/active"),
        api("/api/signals?limit=150"),
      ]);
      state.stats = stats;
      state.active = active.signals || [];
      state.history = all.signals || [];
      renderStats();
      renderActive();
      renderHistory();
    } catch (e) {
      console.error(e);
      $("#scanMeta").textContent = "Offline — retrying…";
    } finally {
      btn.classList.remove("spin");
    }
  }

  async function forceScan() {
    if (state.scanning) return;
    state.scanning = true;
    const btn = $("#btnScan");
    btn.classList.add("spin");
    toast("Market scan started…");
    try {
      await api("/api/scan", { method: "POST" });
      // poll a few times while scan runs
      let n = 0;
      const tick = setInterval(async () => {
        n++;
        await refresh();
        if (n >= 8) {
          clearInterval(tick);
          state.scanning = false;
          btn.classList.remove("spin");
          toast("Scan finished");
        }
      }, 4000);
    } catch (e) {
      state.scanning = false;
      btn.classList.remove("spin");
      toast("Scan failed");
    }
  }

  // ── Tabs / filters / events ────────────────────────────
  function setTab(name) {
    state.tab = name;
    $$(".tab").forEach((t) => {
      const on = t.dataset.tab === name;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$(".pane").forEach((p) => p.classList.toggle("active", p.id === `pane-${name}`));
    // status filter default per tab
    if (name === "active") {
      $("#fStatus").value = "active";
      $("#filtersBar").style.display = "";
    } else if (name === "history") {
      if ($("#fStatus").value === "active") $("#fStatus").value = "all";
      $("#filtersBar").style.display = "";
    } else {
      $("#filtersBar").style.display = "none";
    }
    renderActive();
    renderHistory();
  }

  function bind() {
    $$(".tab").forEach((t) =>
      t.addEventListener("click", () => setTab(t.dataset.tab))
    );

    $("#btnRefresh").addEventListener("click", () => refresh());
    $("#btnScan").addEventListener("click", () => forceScan());

    ["fStatus", "fDir"].forEach((id) =>
      $(`#${id}`).addEventListener("change", () => {
        renderActive();
        renderHistory();
      })
    );
    $("#fSymbol").addEventListener("input", () => {
      renderActive();
      renderHistory();
    });

    // card click (event delegation)
    $(".content").addEventListener("click", (e) => {
      const card = e.target.closest(".sig-card");
      if (card) openSheet(card.dataset.id);
    });
    $(".content").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        const card = e.target.closest(".sig-card");
        if (card) {
          e.preventDefault();
          openSheet(card.dataset.id);
        }
      }
    });

    $("#sheet").addEventListener("click", (e) => {
      if (e.target.matches("[data-close], .sheet-backdrop")) closeSheet();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeSheet();
    });

    // clock
    const tickClock = () => {
      $("#clock").textContent = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    };
    tickClock();
    setInterval(tickClock, 1000);
  }

  // ── Boot ───────────────────────────────────────────────
  async function boot() {
    bind();
    setTab("active");
    $("#activeList").innerHTML = `<div class="skel"></div><div class="skel"></div>`;
    await refresh();
    // live poll every 15s (aligns with tracker)
    state.polling = setInterval(refresh, 15_000);

    // visibility: pause when backgrounded
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        clearInterval(state.polling);
        state.polling = null;
      } else {
        refresh();
        state.polling = setInterval(refresh, 15_000);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
