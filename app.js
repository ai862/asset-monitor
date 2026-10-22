(() => {
  "use strict";

  const EXTRA_FIELD = {
    "ai-web": { key: "类型", label: "类型" },
    ics: { key: "行业", label: "行业" },
    xinchuang: { key: "层", label: "层" },
    intel: { key: "类型", label: "类型" },
  };

  const ICON_IDS = {
    "ai-web": "i-ai-web",
    ics: "i-ics",
    xinchuang: "i-xinchuang",
    intel: "i-intel",
  };

  const LINK_ICON_IDS = {
    官网: "i-link-web",
    GitHub: "i-link-github",
    下载页: "i-link-download",
    文档: "i-link-docs",
  };

  const LINK_SPECS = [
    { key: "官网", label: "官网" },
    { key: "GitHub", label: "GitHub" },
    { key: "下载页", label: "下载" },
    { key: "文档", label: "文档" },
  ];

  const ROW_HEIGHT = 60;
  const OVERSCAN = 8;

  const state = {
    config: null,
    cache: {},
    sourceId: null,
    search: "",
    status: new Set(),
    extra: new Set(),
    difficulty: new Set(),
    view: "table",
    tabsBuilt: false,
    raf: 0,
    scrollRaf: 0,
    filtered: [],
    colCount: 7,
    tableBuilt: false,
    resetScroll: false,
    guideKey: null,
    /** null = 近14天合并视图；YYYY-MM-DD = X 日归档 */
    intelDate: null,
    /** 原始 data/intel.json（近14天合并，含 SRC） */
    intelMerged: null,
    /** data/x-daily/index.json */
    xDailyIndex: null,
  };

  const $ = (id) => document.getElementById(id);

  function statusClass(s) {
    if (!s) return "badge-other";
    if (s === "可下" || s === "SRC速报") return "badge-ok";
    if (s === "待核" || s === "赏金技巧") return "badge-warn";
    if (s === "推荐流") return "badge-other";
    if (
      s.includes("跳过") ||
      s.includes("商务") ||
      s.includes("太热") ||
      s.includes("非 Web") ||
      s.includes("不合格")
    ) {
      return "badge-mute";
    }
    return "badge-other";
  }


  function diffClass(d) {
    if (d === "易") return "badge-diff-easy";
    if (d === "中") return "badge-diff-mid";
    if (d === "难") return "badge-diff-hard";
    return "badge-diff-unk";
  }

  function triageBadge(r) {
    const st = r["研判状态"];
    if (st === "已研判") return `<span class="badge badge-triage">已研判</span>`;
    if (st === "索引缺失") return `<span class="badge badge-triage-miss">索引缺失</span>`;
    return "";
  }

  function difficultyBadge(r) {
    const d = r["搭建难度"];
    if (!d) return "";
    return `<span class="badge ${diffClass(d)}">${esc(d)}</span>`;
  }


  function hasGuide(r) {
    return !!(r && (r["启动指引"] || r["研判摘要"] || r["推荐启动"]));
  }

  const PAGES_ORIGIN = "https://ai862.github.io/asset-monitor";

  function guidanceJsonUrl(r) {
    if (!r) return "";
    if (r["指引URL"] && /^https?:\/\//i.test(String(r["指引URL"]))) return String(r["指引URL"]);
    const key = r["去重键"];
    if (!key) return "";
    return `${PAGES_ORIGIN}/assets/ai-web/${encodeURIComponent(key)}.json`;
  }

  function humanDeepLink(key, sourceId) {
    const src = sourceId || "ai-web";
    const u = new URL(location.href);
    u.searchParams.set("source", src);
    u.searchParams.set("id", key);
    u.hash = src;
    return u.toString();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isHttp(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u);
  }

  function iconUse(id, size) {
    if (!id) return "";
    return `<svg class="ico" width="${size}" height="${size}" aria-hidden="true"><use href="#${id}"></use></svg>`;
  }

  function linkPills(item) {
    return LINK_SPECS.filter((s) => isHttp(item[s.key]))
      .map((s) => {
        const ico = iconUse(LINK_ICON_IDS[s.key], 12);
        return `<a class="link-pill" href="${esc(item[s.key])}" target="_blank" rel="noopener">${ico}${esc(s.label)}</a>`;
      })
      .join("");
  }

  function fmtDeploy(v) {
    if (Array.isArray(v)) return v.map((x) => `<span class="tag">${esc(x)}</span>`).join("");
    if (!v) return '<span class="cell-muted">—</span>';
    return `<span class="tag">${esc(v)}</span>`;
  }

  function fmtBool(v) {
    if (v === true) return '<span class="bool-yes">是</span>';
    if (v === false) return '<span class="bool-no">否</span>';
    return '<span class="cell-muted">—</span>';
  }

  function setAccent(color) {
    document.documentElement.style.setProperty("--accent", color || "#0071e3");
  }

  function formatUpdated(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      const parts = new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).formatToParts(d);
      const get = (t) => parts.find((p) => p.type === t)?.value || "";
      return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")} (Asia/Shanghai)`;
    } catch {
      return iso;
    }
  }

  function uniqueValues(rows, key) {
    const map = new Map();
    for (const r of rows) {
      const v = r[key];
      if (v == null || v === "") continue;
      map.set(v, (map.get(v) || 0) + 1);
    }
    return [...map.entries()].sort(
      (a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0]), "zh")
    );
  }

  function filteredRows(rows) {
    const q = state.search.trim().toLowerCase();
    const extraMeta = EXTRA_FIELD[state.sourceId];
    const isAi = state.sourceId === "ai-web";
    return rows.filter((r) => {
      if (state.status.size && !state.status.has(r["状态"])) return false;
      if (extraMeta && state.extra.size) {
        if (!state.extra.has(r[extraMeta.key])) return false;
      }
      if (isAi && state.difficulty.size) {
        const d = r["搭建难度"] || "未知";
        // 未研判无难度字段 → 视为「未知」以便筛选仍能看到
        if (!state.difficulty.has(d)) return false;
      }
      if (!q) return true;
      const hay = [
        r["产品"],
        r["厂商"],
        r["去重键"],
        r["资产号"],
        r["备注"],
        r["实用价值"],
        r["类型"],
        r["批次"],
        r["研判摘要"],
        r["启动指引"],
        r["推荐启动"],
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }

  function buildTabs() {
    const el = $("tabs");
    el.innerHTML = state.config.sources
      .map((s) => {
        const n = sourceCount(s.id) ?? "…";
        const active = s.id === state.sourceId ? " active" : "";
        const icon = iconUse(ICON_IDS[s.id], 15);
        return `<button type="button" class="tab${active}" role="tab" data-id="${esc(s.id)}" aria-selected="${
          s.id === state.sourceId
        }">${icon}<span class="tab-label">${esc(s.name)}</span><span class="count">${n}</span></button>`;
      })
      .join("");
    state.tabsBuilt = true;
  }

  function updateTabActive() {
    const el = $("tabs");
    if (!state.tabsBuilt || !el.children.length) {
      buildTabs();
      return;
    }
    for (const btn of el.querySelectorAll(".tab")) {
      const on = btn.dataset.id === state.sourceId;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
      const count = btn.querySelector(".count");
      if (count) {
        const n = sourceCount(btn.dataset.id);
        if (n != null) count.textContent = String(n);
      }
    }
  }

  function sourceCount(id) {
    if (id === "intel" && state.intelMerged) return state.intelMerged.length;
    return state.cache[id]?.length;
  }

  function refreshTabCounts() {
    const el = $("tabs");
    for (const btn of el.querySelectorAll(".tab")) {
      const count = btn.querySelector(".count");
      const n = sourceCount(btn.dataset.id);
      if (count && n != null) count.textContent = String(n);
    }
  }

  function renderChips(container, values, selected, allLabel) {
    const total = values.reduce((a, [, n]) => a + n, 0);
    const chips = [
      `<button type="button" class="chip${!selected.size ? " active" : ""}" data-value="__all__">${allLabel}<span class="n">${total}</span></button>`,
      ...values.map(
        ([v, n]) =>
          `<button type="button" class="chip${selected.has(v) ? " active" : ""}" data-value="${esc(v)}">${esc(
            v
          )}<span class="n">${n}</span></button>`
      ),
    ];
    container.innerHTML = chips.join("");
  }


  async function ensureXDailyIndex() {
    if (state.xDailyIndex) return state.xDailyIndex;
    try {
      const res = await fetch("data/x-daily/index.json");
      if (!res.ok) throw new Error(`index ${res.status}`);
      const data = await res.json();
      state.xDailyIndex = Array.isArray(data) ? data : [];
    } catch {
      state.xDailyIndex = [];
    }
    return state.xDailyIndex;
  }

  function renderDateChips() {
    const wrap = $("date-filters");
    const chipsEl = $("date-chips");
    const hint = $("intel-hint");
    if (!wrap || !chipsEl || !hint) return;

    if (state.sourceId !== "intel") {
      wrap.classList.add("hidden");
      hint.classList.add("hidden");
      hint.textContent = "";
      return;
    }

    wrap.classList.remove("hidden");
    hint.classList.remove("hidden");
    const index = state.xDailyIndex || [];
    const mergedN = state.intelMerged?.length ?? state.cache.intel?.length ?? 0;
    const parts = [
      `<button type="button" class="chip${!state.intelDate ? " active" : ""}" data-date="__merged__">近14天（合并）<span class="n">${mergedN}</span></button>`,
    ];
    for (const e of index) {
      const on = state.intelDate === e.date;
      parts.push(
        `<button type="button" class="chip chip-archive${on ? " active" : ""}" data-date="${esc(e.date)}">${esc(
          e.date
        )}<span class="n">${e.total ?? 0}</span><span class="chip-tag">X</span></button>`
      );
    }
    chipsEl.innerHTML = parts.join("");

    if (state.intelDate) {
      hint.textContent =
        `X 日归档 · ${state.intelDate}（仅赏金技巧与推荐流；SRC 见近14天合并视图）`;
    } else {
      hint.textContent =
        "按日归档仅含赏金技巧与推荐流；SRC 见近14天合并视图";
    }
  }

  async function selectIntelDate(dateKey) {
    if (state.sourceId !== "intel") return;

    if (dateKey === "__merged__" || !dateKey) {
      state.intelDate = null;
      if (state.intelMerged) state.cache.intel = state.intelMerged;
      state.status = new Set();
      state.tableBuilt = false;
      state.resetScroll = true;
      renderDateChips();
      renderFilters(state.cache.intel || []);
      render({ resetScroll: true });
      return;
    }

    $("loading").classList.remove("hidden");
    $("empty").classList.add("hidden");
    $("error").classList.add("hidden");
    try {
      const res = await fetch(`data/x-daily/${encodeURIComponent(dateKey)}.json`);
      if (!res.ok) throw new Error(`加载 X 日归档 ${dateKey} 失败 (${res.status})`);
      const rows = await res.json();
      state.intelDate = dateKey;
      state.cache.intel = Array.isArray(rows) ? rows : [];
      state.status = new Set();
      state.tableBuilt = false;
      state.resetScroll = true;
      $("loading").classList.add("hidden");
      renderDateChips();
      renderFilters(state.cache.intel);
      render({ resetScroll: true });
    } catch (err) {
      $("loading").classList.add("hidden");
      $("error").classList.remove("hidden");
      $("error").textContent = String(err.message || err);
    }
  }

  function renderFilters(rows) {
    renderChips($("status-chips"), uniqueValues(rows, "状态"), state.status, "全部");
    const extra = EXTRA_FIELD[state.sourceId];
    const extraWrap = $("extra-filters");
    if (!extra) {
      extraWrap.classList.add("hidden");
    } else {
      extraWrap.classList.remove("hidden");
      $("extra-label").textContent = extra.label;
      renderChips($("extra-chips"), uniqueValues(rows, extra.key), state.extra, "全部");
    }
    const diffWrap = $("diff-filters");
    if (state.sourceId !== "ai-web") {
      diffWrap.classList.add("hidden");
    } else {
      diffWrap.classList.remove("hidden");
      // Normalize empty 搭建难度 → 未知 for chip counts
      const norm = rows.map((r) => ({
        ...r,
        搭建难度: r["搭建难度"] || "未知",
      }));
      const order = ["易", "中", "难", "未知"];
      const counts = uniqueValues(norm, "搭建难度");
      counts.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]) || b[1] - a[1]);
      renderChips($("diff-chips"), counts, state.difficulty, "全部");
    }
    renderDateChips();
  }

  function headExtraAndCount(src) {
    if (src === "ai-web") {
      return {
        head: "<th>类型</th><th>语言</th><th>Stars</th><th>Web</th><th>部署</th><th>研判</th>",
        cols: 9,
      };
    }
    if (src === "ics") {
      return { head: "<th>行业</th><th>地区</th><th>Web</th><th>部署</th>", cols: 7 };
    }
    if (src === "intel") {
      return { head: "<th>类型</th><th>批次</th><th>要点</th>", cols: 6 };
    }
    return { head: "<th>层</th><th>内核系</th><th>Web</th><th>统信</th>", cols: 7 };
  }

  function rowCells(r, src) {
    let cols = "";
    if (src === "ai-web") {
      const guide = hasGuide(r)
        ? `<button type="button" class="guide-btn" data-guide="${esc(r["去重键"] || "")}">指引</button>`
        : '<span class="cell-muted">—</span>';
      cols = `<td>${esc(r["类型"] || "—")}</td>
        <td class="cell-muted">${esc(r["语言"] || "—")}</td>
        <td class="mono">${r.Stars != null ? esc(r.Stars) : "—"}</td>
        <td>${fmtBool(r["Web服务"])}</td>
        <td>${fmtDeploy(r["部署方式"])}</td>
        <td><div class="triage-cell">${difficultyBadge(r) || '<span class="cell-muted">未研判</span>'}${triageBadge(r)}${guide}</div></td>`;
    } else if (src === "ics") {
      cols = `<td>${esc(r["行业"] || "—")}</td>
        <td class="cell-muted">${esc(r["地区"] || "—")}</td>
        <td>${fmtBool(r["Web服务"])}</td>
        <td>${fmtDeploy(r["部署方式"])}</td>`;
    } else if (src === "intel") {
      const tip = String(r["备注"] || "");
      const tipShort = tip.slice(0, 80) + (tip.length > 80 ? "…" : "");
      cols = `<td>${esc(r["类型"] || "—")}</td>
        <td class="cell-muted">${esc(r["批次"] || "—")}</td>
        <td class="cell-muted" title="${esc(tip)}">${esc(tipShort || "—")}</td>`;
    } else {
      cols = `<td>${esc(r["层"] || "—")}</td>
        <td class="cell-muted">${esc(r["内核系"] || "—")}</td>
        <td>${fmtBool(r["Web服务"])}</td>
        <td>${fmtBool(r["统信清单"])}</td>`;
    }
    return `<td>
        <div class="product">${esc(r["产品"] || "—")}</div>
        <div class="vendor">${esc(r["厂商"] || "")}</div>
        <div class="mono">${esc(r["去重键"] || "")}</div>
      </td>
      <td><span class="badge ${statusClass(r["状态"])}">${esc(r["状态"] || "—")}</span></td>
      ${cols}
      <td><div class="links">${linkPills(r) || '<span class="cell-muted">—</span>'}</div></td>`;
  }

  function rebuildTableShell() {
    const wrap = $("table-view");
    const { head, cols } = headExtraAndCount(state.sourceId);
    state.colCount = cols;
    const scrollTop = state.resetScroll ? 0 : wrap.scrollTop;
    wrap.innerHTML = `<table>
      <thead><tr>
        <th>产品</th><th>状态</th>${head}<th>链接</th>
      </tr></thead>
      <tbody id="table-body"></tbody>
    </table>`;
    state.tableBuilt = true;
    if (!wrap._scrollBound) {
      wrap.addEventListener("scroll", onTableScroll, { passive: true });
      wrap._scrollBound = true;
    }
    wrap.scrollTop = scrollTop;
  }

  function onTableScroll() {
    if (state.scrollRaf) return;
    state.scrollRaf = requestAnimationFrame(() => {
      state.scrollRaf = 0;
      paintVirtualRows();
    });
  }

  function paintVirtualRows() {
    const wrap = $("table-view");
    const tbody = $("table-body");
    if (!tbody || !wrap) return;

    const rows = state.filtered;
    const total = rows.length;
    const src = state.sourceId;
    const rh = ROW_HEIGHT;
    const scrollTop = wrap.scrollTop;
    const viewH = wrap.clientHeight || 480;
    const start = Math.max(0, Math.floor(scrollTop / rh) - OVERSCAN);
    const visible = Math.ceil(viewH / rh) + OVERSCAN * 2;
    const end = Math.min(total, start + visible);
    const topPad = start * rh;
    const bottomPad = Math.max(0, (total - end) * rh);

    const parts = [];
    if (topPad > 0) {
      parts.push(`<tr class="v-spacer" aria-hidden="true"><td colspan="${state.colCount}" style="height:${topPad}px;padding:0;border:0"></td></tr>`);
    }
    for (let i = start; i < end; i++) {
      const even = i % 2 === 1 ? " even" : "";
      parts.push(`<tr class="v-row${even}" data-i="${i}">${rowCells(rows[i], src)}</tr>`);
    }
    if (bottomPad > 0) {
      parts.push(`<tr class="v-spacer" aria-hidden="true"><td colspan="${state.colCount}" style="height:${bottomPad}px;padding:0;border:0"></td></tr>`);
    }

    tbody.innerHTML = parts.join("") || "";
  }

  function renderTable(rows, { forceShell = false } = {}) {
    state.filtered = rows;
    const wrap = $("table-view");

    if (forceShell || !state.tableBuilt || !wrap.querySelector("#table-body")) {
      rebuildTableShell();
    } else {
      // Column count may change when switching source
      const { cols } = headExtraAndCount(state.sourceId);
      if (cols !== state.colCount || !wrap.querySelector("thead th")) {
        rebuildTableShell();
      }
    }

    if (state.resetScroll) {
      wrap.scrollTop = 0;
      state.resetScroll = false;
    }

    paintVirtualRows();
  }

  function renderCards(rows) {
    const src = state.sourceId;
    $("cards-view").innerHTML = rows
      .map((r) => {
        let meta = "";
        if (src === "ai-web") {
          meta = `${esc(r["类型"] || "—")} · ${esc(r["语言"] || "—")}${
            r.Stars != null ? ` · ★ ${esc(r.Stars)}` : ""
          }`;
        } else if (src === "ics") {
          meta = `${esc(r["行业"] || "—")} · ${esc(r["地区"] || "—")}`;
        } else if (src === "intel") {
          meta = `${esc(r["类型"] || "—")} · ${esc(r["批次"] || "—")}`;
        } else {
          meta = `${esc(r["层"] || "—")} · ${esc(r["内核系"] || "—")}`;
        }
        const note = src === "intel" ? r["备注"] || "" : r["下载条件"] || r["备注"] || "";
        const value = src === "intel" ? r["实用价值"] || "" : "";
        const snippet = r["研判摘要"] || "";
        const triageRow =
          src === "ai-web"
            ? `<div class="card-triage">${difficultyBadge(r)}${triageBadge(r)}${
                hasGuide(r)
                  ? `<button type="button" class="guide-btn" data-guide="${esc(r["去重键"] || "")}">查看指引</button>`
                  : ""
              }</div>${
                snippet
                  ? `<div class="card-snippet">${esc(snippet).slice(0, 120)}${snippet.length > 120 ? "…" : ""}</div>`
                  : ""
              }`
            : "";
        const bodyTop =
          src === "intel"
            ? `${
                note
                  ? `<div class="row">${esc(note).slice(0, 200)}${note.length > 200 ? "…" : ""}</div>`
                  : ""
              }${
                value
                  ? `<div class="row cell-muted">实用：${esc(value).slice(0, 120)}${value.length > 120 ? "…" : ""}</div>`
                  : ""
              }`
            : `<div class="row">Web：${fmtBool(r["Web服务"])}${
                src === "xinchuang" ? ` · 统信：${fmtBool(r["统信清单"])}` : ""
              }</div>
            ${
              note
                ? `<div class="row">${esc(note).slice(0, 160)}${note.length > 160 ? "…" : ""}</div>`
                : ""
            }`;
        return `<article class="card">
          <div class="card-top">
            <div>
              <h3 class="card-title">${esc(r["产品"] || "—")}</h3>
              <div class="card-meta">${esc(r["厂商"] || "")}</div>
            </div>
            <span class="badge ${statusClass(r["状态"])}">${esc(r["状态"] || "—")}</span>
          </div>
          <div class="card-meta">${meta}</div>
          ${triageRow}
          <div class="card-body">
            ${bodyTop}
            <div class="row mono">${esc(r["去重键"] || "")}</div>
          </div>
          <div class="card-footer">${linkPills(r)}</div>
        </article>`;
      })
      .join("");
  }

  function paint() {
    const rows = state.cache[state.sourceId] || [];
    const filtered = filteredRows(rows);
    $("visible-count").textContent = String(filtered.length);
    $("total-count").textContent = String(rows.length);

    $("loading").classList.add("hidden");
    $("error").classList.add("hidden");

    if (!filtered.length) {
      $("empty").classList.remove("hidden");
      $("table-view").classList.add("hidden");
      $("cards-view").classList.add("hidden");
      return;
    }
    $("empty").classList.add("hidden");

    if (state.view === "table") {
      renderTable(filtered);
      $("table-view").classList.remove("hidden");
      $("cards-view").classList.add("hidden");
    } else {
      renderCards(filtered);
      $("cards-view").classList.remove("hidden");
      $("table-view").classList.add("hidden");
    }
  }

  function render({ resetScroll = false } = {}) {
    if (resetScroll) state.resetScroll = true;
    if (state.raf) cancelAnimationFrame(state.raf);
    state.raf = requestAnimationFrame(() => {
      state.raf = 0;
      paint();
    });
  }

  function applySourceChrome(src, { pushHash }) {
    setAccent(src.accent);
    const notionBtn = $("notion-edit");
    const notionUrl = (src.notion || "").trim();
    if (notionUrl) {
      notionBtn.href = notionUrl;
      notionBtn.classList.remove("hidden");
      notionBtn.removeAttribute("aria-hidden");
    } else {
      notionBtn.href = "#";
      notionBtn.classList.add("hidden");
      notionBtn.setAttribute("aria-hidden", "true");
    }
    if (pushHash) {
      const hash = `#${src.id}`;
      if (location.hash !== hash) history.replaceState(null, "", hash);
    }
    updateTabActive();
  }

  async function loadSource(id, { pushHash = true } = {}) {
    const src = state.config.sources.find((s) => s.id === id);
    if (!src) return;

    const same = state.sourceId === id;
    state.sourceId = id;
    if (!same) {
      state.status = new Set();
      state.extra = new Set();
      state.difficulty = new Set();
      state.tableBuilt = false;
      state.resetScroll = true;
      closeGuide();
      // Leaving or entering intel: restore merged view
      if (id === "intel" && state.intelMerged) {
        state.intelDate = null;
        state.cache.intel = state.intelMerged;
      } else if (id !== "intel") {
        state.intelDate = null;
      }
    }

    applySourceChrome(src, { pushHash });

    if (id === "intel") {
      await ensureXDailyIndex();
    }

    if (state.cache[id]) {
      if (id === "intel" && !state.intelMerged) {
        state.intelMerged = state.cache.intel;
      }
      renderFilters(state.cache[id]);
      render({ resetScroll: !same });
      return;
    }

    $("loading").classList.remove("hidden");
    $("empty").classList.add("hidden");
    $("error").classList.add("hidden");
    $("table-view").classList.add("hidden");
    $("cards-view").classList.add("hidden");

    try {
      const res = await fetch(src.data);
      if (!res.ok) throw new Error(`加载 ${src.data} 失败 (${res.status})`);
      state.cache[id] = await res.json();
      if (id === "intel") {
        state.intelMerged = state.cache.intel;
        state.intelDate = null;
      }
      refreshTabCounts();
      renderFilters(state.cache[id]);
      render({ resetScroll: true });
    } catch (err) {
      $("loading").classList.add("hidden");
      $("error").classList.remove("hidden");
      $("error").textContent = String(err.message || err);
    }
  }


  function findByKey(key) {
    const rows = state.cache[state.sourceId] || [];
    return rows.find((r) => r["去重键"] === key);
  }

  function closeGuide() {
    state.guideKey = null;
    const panel = $("guide-panel");
    const overlay = $("guide-overlay");
    if (panel) {
      panel.classList.add("hidden");
      panel.setAttribute("aria-hidden", "true");
    }
    if (overlay) {
      overlay.classList.add("hidden");
      overlay.setAttribute("aria-hidden", "true");
    }
    document.body.style.overflow = "";
    const app = document.querySelector(".app");
    if (app) app.classList.remove("is-guide-open");
    try {
      const u = new URL(location.href);
      if (u.searchParams.has("id")) {
        u.searchParams.delete("id");
        history.replaceState(null, "", u.toString());
      }
    } catch (_) { /* ignore */ }
  }

  function foldSection(title, innerHtml, { open = false } = {}) {
    return (
      `<details class="guide-fold"${open ? " open" : ""}>` +
        `<summary>${esc(title)}</summary>` +
        `<div class="guide-fold-body">${innerHtml}</div>` +
      `</details>`
    );
  }

  /** Long prose: clamp + expand so the drawer stays short and scroll stays light. */
  function proseBlock(text, { clampAt = 280 } = {}) {
    const raw = String(text || "");
    const body = `<div class="guide-prose">${esc(raw)}</div>`;
    if (raw.length < clampAt) return body;
    return (
      `<div class="guide-clamp-wrap">` +
        `<div class="guide-prose guide-clamp">${esc(raw)}</div>` +
        `<button type="button" class="guide-more" data-guide-more>展开全部</button>` +
      `</div>`
    );
  }

  function openGuide(key) {
    const r = findByKey(key);
    if (!r || !hasGuide(r)) return;
    state.guideKey = key;
    $("guide-title").textContent = r["产品"] || "启动指引";
    $("guide-sub").textContent = [r["厂商"], r["去重键"]].filter(Boolean).join(" · ");

    const links = Array.isArray(r["开工前先看"]) ? r["开工前先看"] : [];
    const qs = Array.isArray(r["建议追问"]) ? r["建议追问"] : [];
    const parts = [];
    parts.push(`<div class="guide-meta">${difficultyBadge(r)}${triageBadge(r)}</div>`);
    const jsonUrl = guidanceJsonUrl(r);
    if (jsonUrl) {
      parts.push(
        `<section class="guide-section guide-share">` +
          `<h3>可分享链接（Agent 可读）</h3>` +
          `<div class="guide-share-row">` +
            `<a class="guide-share-link" href="${esc(jsonUrl)}" target="_blank" rel="noopener">${esc(jsonUrl)}</a>` +
            `<button type="button" class="guide-copy-btn" data-copy="${esc(jsonUrl)}">复制</button>` +
          `</div>` +
          `<p class="guide-share-hint">Agent 请 <code>fetch</code> 此 JSON；人类也可打开。</p>` +
        `</section>`
      );
    }
    if (r["研判摘要"]) {
      parts.push(`<section class="guide-section"><h3>研判摘要</h3><p>${esc(r["研判摘要"])}</p></section>`);
    }
    if (r["推荐启动"]) {
      parts.push(`<section class="guide-section"><h3>推荐启动</h3><pre class="guide-cmd">${esc(r["推荐启动"])}</pre></section>`);
    }
    if (r["启动指引"]) {
      parts.push(foldSection("启动指引", proseBlock(r["启动指引"]), { open: true }));
    }
    if (links.length) {
      parts.push(
        foldSection(
          "开工前先看",
          `<ul class="guide-links">${links
            .filter((x) => x && x.url)
            .map((x) => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title || x.url)}</a></li>`)
            .join("")}</ul>`,
          { open: true }
        )
      );
    }
    if (qs.length) {
      parts.push(
        foldSection(
          "建议追问",
          `<ol class="guide-qs">${qs.map((q) => `<li>${esc(q)}</li>`).join("")}</ol>`,
          { open: false }
        )
      );
    }
    if (r["已知坑"]) {
      parts.push(foldSection("已知坑", proseBlock(r["已知坑"], { clampAt: 160 }), { open: false }));
    }
    if (r["成功标准"]) {
      parts.push(foldSection("成功标准", proseBlock(r["成功标准"], { clampAt: 160 }), { open: false }));
    }
    if (isHttp(r["DeepWiki"])) {
      parts.push(
        foldSection(
          "DeepWiki",
          `<ul class="guide-links"><li><a href="${esc(r["DeepWiki"])}" target="_blank" rel="noopener">打开 DeepWiki</a></li></ul>`,
          { open: false }
        )
      );
    }
    if (r["agentHint"]) {
      parts.push(foldSection("Agent 提示", `<p>${esc(r["agentHint"])}</p>`, { open: false }));
    }
    if (r["研判时间"]) {
      parts.push(
        `<section class="guide-section"><h3>研判时间</h3><p class="cell-muted">${esc(formatUpdated(r["研判时间"]))}</p></section>`
      );
    }

    const body = $("guide-body");
    body.innerHTML = parts.join("");
    body.scrollTop = 0;
    $("guide-panel").classList.remove("hidden");
    $("guide-panel").setAttribute("aria-hidden", "false");
    $("guide-overlay").classList.remove("hidden");
    $("guide-overlay").setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    const app = document.querySelector(".app");
    if (app) app.classList.add("is-guide-open");
  }

  function bind() {
    $("tabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".tab");
      if (!btn) return;
      loadSource(btn.dataset.id);
    });

    $("date-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn || !btn.dataset.date) return;
      selectIntelDate(btn.dataset.date);
    });

    $("status-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const v = btn.dataset.value;
      if (v === "__all__") state.status = new Set();
      else {
        if (state.status.has(v)) state.status.delete(v);
        else state.status.add(v);
      }
      renderFilters(state.cache[state.sourceId] || []);
      render({ resetScroll: true });
    });

    $("extra-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const v = btn.dataset.value;
      if (v === "__all__") state.extra = new Set();
      else {
        if (state.extra.has(v)) state.extra.delete(v);
        else state.extra.add(v);
      }
      renderFilters(state.cache[state.sourceId] || []);
      render({ resetScroll: true });
    });

    $("diff-chips").addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      const v = btn.dataset.value;
      if (v === "__all__") state.difficulty = new Set();
      else {
        if (state.difficulty.has(v)) state.difficulty.delete(v);
        else state.difficulty.add(v);
      }
      renderFilters(state.cache[state.sourceId] || []);
      render({ resetScroll: true });
    });

    document.addEventListener("click", (e) => {
      const moreBtn = e.target.closest("[data-guide-more]");
      if (moreBtn) {
        e.preventDefault();
        const wrap = moreBtn.closest(".guide-clamp-wrap");
        const clamp = wrap && wrap.querySelector(".guide-clamp");
        if (clamp) {
          const expanded = clamp.classList.toggle("is-expanded");
          moreBtn.textContent = expanded ? "收起" : "展开全部";
        }
        return;
      }
      const copyBtn = e.target.closest(".guide-copy-btn");
      if (copyBtn && copyBtn.dataset.copy) {
        e.preventDefault();
        const val = copyBtn.dataset.copy;
        const done = () => {
          const prev = copyBtn.textContent;
          copyBtn.textContent = "已复制";
          setTimeout(() => {
            copyBtn.textContent = prev || "复制";
          }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(val).then(done).catch(() => {
            window.prompt("复制链接：", val);
          });
        } else {
          window.prompt("复制链接：", val);
        }
        return;
      }
      const btn = e.target.closest(".guide-btn");
      if (btn && btn.dataset.guide) {
        e.preventDefault();
        openGuide(btn.dataset.guide);
        return;
      }
    });

    $("guide-close").addEventListener("click", closeGuide);
    $("guide-overlay").addEventListener("click", closeGuide);

    let t = null;
    $("search").addEventListener("input", (e) => {
      clearTimeout(t);
      t = setTimeout(() => {
        state.search = e.target.value;
        render({ resetScroll: true });
      }, 120);
    });

    document.querySelectorAll(".view-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.view = btn.dataset.view;
        document.querySelectorAll(".view-btn").forEach((b) => b.classList.toggle("active", b === btn));
        render({ resetScroll: true });
      });
    });

    window.addEventListener("hashchange", () => {
      const id = location.hash.replace(/^#/, "");
      if (id && state.config.sources.some((s) => s.id === id) && id !== state.sourceId) {
        loadSource(id, { pushHash: false });
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.guideKey) {
        closeGuide();
        return;
      }
      if (e.key === "/" && document.activeElement !== $("search") && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        $("search").focus();
      }
    });

    window.addEventListener(
      "resize",
      () => {
        if (state.view === "table" && state.filtered.length) paintVirtualRows();
      },
      { passive: true }
    );
  }

  async function init() {
    try {
      const res = await fetch("config.json");
      if (!res.ok) throw new Error(`无法读取 config.json (${res.status})`);
      state.config = await res.json();
      $("page-title").textContent = state.config.title || "资产监控中心";
      document.title = state.config.title || "资产监控中心";
      $("updated-at").textContent = formatUpdated(state.config.updatedAt);
      $("footer-links").innerHTML = state.config.sources
        .map((s) => `<a href="${esc(s.notion)}" target="_blank" rel="noopener">${esc(s.name)} Notion</a>`)
        .join("");

      await Promise.all(
        state.config.sources.map(async (s) => {
          try {
            const r = await fetch(s.data);
            if (r.ok) state.cache[s.id] = await r.json();
          } catch {
            /* ignore prefetch errors */
          }
        })
      );

      if (state.cache.intel && !state.intelMerged) {
        state.intelMerged = state.cache.intel;
      }
      // Prefetch x-daily index (non-blocking if intel not first tab)
      ensureXDailyIndex().catch(() => {});
      buildTabs();
      bind();
      const params = new URLSearchParams(location.search);
      const qSource = params.get("source");
      const qId = params.get("id");
      const hash = location.hash.replace(/^#/, "");
      const initial =
        (qSource && state.config.sources.some((s) => s.id === qSource) && qSource) ||
        (hash && state.config.sources.some((s) => s.id === hash) && hash) ||
        state.config.sources[0]?.id;
      await loadSource(initial, { pushHash: true });
      if (qId && initial === "ai-web") {
        openGuide(qId);
      } else if (qId && state.cache[initial]) {
        // Prefer matching source; fall back to ai-web if key lives there
        if (findByKey(qId)) openGuide(qId);
        else if (state.cache["ai-web"]?.some((r) => r["去重键"] === qId)) {
          await loadSource("ai-web", { pushHash: true });
          openGuide(qId);
        }
      }
    } catch (err) {
      $("loading").classList.add("hidden");
      $("error").classList.remove("hidden");
      $("error").textContent = String(err.message || err);
    }
  }

  init();
})();
