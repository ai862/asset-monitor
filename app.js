(() => {
  "use strict";

  const EXTRA_FIELD = {
    "ai-web": { key: "类型", label: "类型" },
    ics: { key: "行业", label: "行业" },
    xinchuang: { key: "层", label: "层" },
  };

  const ICON_IDS = {
    "ai-web": "i-ai-web",
    ics: "i-ics",
    xinchuang: "i-xinchuang",
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
    view: "table",
    tabsBuilt: false,
    raf: 0,
    scrollRaf: 0,
    filtered: [],
    colCount: 7,
    tableBuilt: false,
    resetScroll: false,
  };

  const $ = (id) => document.getElementById(id);

  function statusClass(s) {
    if (!s) return "badge-other";
    if (s === "可下") return "badge-ok";
    if (s === "待核") return "badge-warn";
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
    return rows.filter((r) => {
      if (state.status.size && !state.status.has(r["状态"])) return false;
      if (extraMeta && state.extra.size) {
        if (!state.extra.has(r[extraMeta.key])) return false;
      }
      if (!q) return true;
      const hay = [r["产品"], r["厂商"], r["去重键"], r["资产号"], r["备注"]]
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
        const n = state.cache[s.id]?.length ?? "…";
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
        const n = state.cache[btn.dataset.id]?.length;
        if (n != null) count.textContent = String(n);
      }
    }
  }

  function refreshTabCounts() {
    const el = $("tabs");
    for (const btn of el.querySelectorAll(".tab")) {
      const count = btn.querySelector(".count");
      const n = state.cache[btn.dataset.id]?.length;
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

  function renderFilters(rows) {
    renderChips($("status-chips"), uniqueValues(rows, "状态"), state.status, "全部");
    const extra = EXTRA_FIELD[state.sourceId];
    const extraWrap = $("extra-filters");
    if (!extra) {
      extraWrap.classList.add("hidden");
      return;
    }
    extraWrap.classList.remove("hidden");
    $("extra-label").textContent = extra.label;
    renderChips($("extra-chips"), uniqueValues(rows, extra.key), state.extra, "全部");
  }

  function headExtraAndCount(src) {
    if (src === "ai-web") {
      return { head: "<th>类型</th><th>语言</th><th>Stars</th><th>Web</th><th>部署</th>", cols: 8 };
    }
    if (src === "ics") {
      return { head: "<th>行业</th><th>地区</th><th>Web</th><th>部署</th>", cols: 7 };
    }
    return { head: "<th>层</th><th>内核系</th><th>Web</th><th>统信</th>", cols: 7 };
  }

  function rowCells(r, src) {
    let cols = "";
    if (src === "ai-web") {
      cols = `<td>${esc(r["类型"] || "—")}</td>
        <td class="cell-muted">${esc(r["语言"] || "—")}</td>
        <td class="mono">${r.Stars != null ? esc(r.Stars) : "—"}</td>
        <td>${fmtBool(r["Web服务"])}</td>
        <td>${fmtDeploy(r["部署方式"])}</td>`;
    } else if (src === "ics") {
      cols = `<td>${esc(r["行业"] || "—")}</td>
        <td class="cell-muted">${esc(r["地区"] || "—")}</td>
        <td>${fmtBool(r["Web服务"])}</td>
        <td>${fmtDeploy(r["部署方式"])}</td>`;
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
        } else {
          meta = `${esc(r["层"] || "—")} · ${esc(r["内核系"] || "—")}`;
        }
        const note = r["下载条件"] || r["备注"] || "";
        return `<article class="card">
          <div class="card-top">
            <div>
              <h3 class="card-title">${esc(r["产品"] || "—")}</h3>
              <div class="card-meta">${esc(r["厂商"] || "")}</div>
            </div>
            <span class="badge ${statusClass(r["状态"])}">${esc(r["状态"] || "—")}</span>
          </div>
          <div class="card-meta">${meta}</div>
          <div class="card-body">
            <div class="row">Web：${fmtBool(r["Web服务"])}${
          src === "xinchuang" ? ` · 统信：${fmtBool(r["统信清单"])}` : ""
        }</div>
            ${
              note
                ? `<div class="row">${esc(note).slice(0, 160)}${note.length > 160 ? "…" : ""}</div>`
                : ""
            }
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
    $("notion-edit").href = src.notion;
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
      state.tableBuilt = false;
      state.resetScroll = true;
    }

    applySourceChrome(src, { pushHash });

    if (state.cache[id]) {
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
      refreshTabCounts();
      renderFilters(state.cache[id]);
      render({ resetScroll: true });
    } catch (err) {
      $("loading").classList.add("hidden");
      $("error").classList.remove("hidden");
      $("error").textContent = String(err.message || err);
    }
  }

  function bind() {
    $("tabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".tab");
      if (!btn) return;
      loadSource(btn.dataset.id);
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

      buildTabs();
      bind();
      const hash = location.hash.replace(/^#/, "");
      const initial =
        (hash && state.config.sources.some((s) => s.id === hash) && hash) ||
        state.config.sources[0]?.id;
      await loadSource(initial, { pushHash: true });
    } catch (err) {
      $("loading").classList.add("hidden");
      $("error").classList.remove("hidden");
      $("error").textContent = String(err.message || err);
    }
  }

  init();
})();
