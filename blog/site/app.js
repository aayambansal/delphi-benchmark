/* Retrieval, Measured — page logic. All numbers come from data/*.json. */
"use strict";

const fmt = (x, d = 3) => (x == null ? "—" : Number(x).toFixed(d));
const pct = (x, d = 1) => (x == null ? "—" : (100 * x).toFixed(d) + "%");
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
  );
const el = (id) => document.getElementById(id);
const COLORS = {
  delphi: "#8e2f22",
  nia: "#1e5f5b",
  context7: "#b8860b",
  control: "#8a7f70",
  bm25: "#4d8d88",
  lexical: "#6a5f8e",
  lexical_bm25: "#1e5f5b",
};
const ENGINE_LABELS = {
  delphi: "Delphi",
  bm25: "BM25 (whole-file)",
  lexical: "Lexical ranker",
  lexical_bm25: "Lexical+BM25 RRF",
};

async function fetchJSON(name) {
  const resp = await fetch(`data/${name}`);
  if (!resp.ok) throw new Error(`failed to load ${name}`);
  return resp.json();
}

/* ---------- tiny SVG chart helpers ---------- */

function svgTag(w, h) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", `0 0 ${w} ${h}`);
  s.setAttribute("width", "100%");
  s.style.maxWidth = w + "px";
  s.style.display = "block";
  return s;
}
function add(parent, tag, attrs = {}, text) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  parent.appendChild(node);
  return node;
}

/* Horizontal bars with optional CI whiskers and per-repeat dots. */
function hBarChart(container, rows, opts = {}) {
  const width = opts.width || 760;
  const labelW = opts.labelW || 250;
  const rowH = 42;
  const max = opts.max || Math.max(...rows.map((r) => r.value)) * 1.15;
  const h = rows.length * rowH + 30;
  const svg = svgTag(width, h);
  const plotW = width - labelW - 90;
  const x = (v) => labelW + (v / max) * plotW;

  rows.forEach((row, i) => {
    const y = i * rowH + 12;
    add(svg, "text", { x: labelW - 10, y: y + 15, "text-anchor": "end", class: "bar-name" }, row.label);
    add(svg, "rect", { x: labelW, y, width: Math.max(2, x(row.value) - labelW), height: 22, fill: row.color || "#8e2f22", opacity: 0.92, rx: 1.5 });
    add(svg, "text", { x: x(row.value) + 8, y: y + 15, class: "bar-value" }, fmt(row.value, opts.digits ?? 3));
    if (row.ci) {
      const y2 = y + 11;
      add(svg, "line", { x1: x(row.ci[0]), x2: x(row.ci[1]), y1: y2, y2: y2, stroke: "#1c1712", "stroke-width": 1.4 });
      add(svg, "line", { x1: x(row.ci[0]), x2: x(row.ci[0]), y1: y2 - 5, y2: y2 + 5, stroke: "#1c1712", "stroke-width": 1.4 });
      add(svg, "line", { x1: x(row.ci[1]), x2: x(row.ci[1]), y1: y2 - 5, y2: y2 + 5, stroke: "#1c1712", "stroke-width": 1.4 });
    }
    if (row.dots) {
      for (const d of row.dots) {
        add(svg, "circle", { cx: x(d), cy: y + 11, r: 3.4, fill: "#fffdf7", stroke: "#1c1712", "stroke-width": 1.1 });
      }
    }
  });
  if (opts.refLine != null) {
    const rx = x(opts.refLine);
    add(svg, "line", { x1: rx, x2: rx, y1: 2, y2: rows.length * rowH + 6, stroke: "#8a7f70", "stroke-width": 1.2, "stroke-dasharray": "5 4" });
    add(svg, "text", { x: rx + 5, y: rows.length * rowH + 20, class: "axis-label" }, opts.refLabel || "");
  }
  container.appendChild(svg);
}

/* Dot-with-CI chart for paired deltas around zero. */
function deltaChart(container, rows, opts = {}) {
  const width = opts.width || 760;
  const labelW = 280;
  const rowH = 44;
  const values = rows.flatMap((r) => r.ci);
  const lo = Math.min(...values, 0) * 1.25;
  const hi = Math.max(...values, 0) * 1.25;
  const h = rows.length * rowH + 44;
  const svg = svgTag(width, h);
  const plotW = width - labelW - 60;
  const x = (v) => labelW + ((v - lo) / (hi - lo)) * plotW;

  add(svg, "line", { x1: x(0), x2: x(0), y1: 4, y2: rows.length * rowH + 10, stroke: "#1c1712", "stroke-width": 1.6 });
  add(svg, "text", { x: x(0), y: rows.length * rowH + 32, "text-anchor": "middle", class: "axis-label" }, "0 (no difference)");

  rows.forEach((row, i) => {
    const y = i * rowH + 24;
    add(svg, "text", { x: labelW - 12, y: y + 4, "text-anchor": "end", class: "bar-name" }, row.label);
    const excl = row.ci[0] > 0 || row.ci[1] < 0;
    const color = excl ? (row.delta > 0 ? "#2e6b34" : "#b03a2e") : "#8a7f70";
    add(svg, "line", { x1: x(row.ci[0]), x2: x(row.ci[1]), y1: y, y2: y, stroke: color, "stroke-width": 3, opacity: 0.55 });
    add(svg, "line", { x1: x(row.ci[0]), x2: x(row.ci[0]), y1: y - 6, y2: y + 6, stroke: color, "stroke-width": 2 });
    add(svg, "line", { x1: x(row.ci[1]), x2: x(row.ci[1]), y1: y - 6, y2: y + 6, stroke: color, "stroke-width": 2 });
    add(svg, "circle", { cx: x(row.delta), cy: y, r: 6, fill: color });
    add(svg, "text", { x: x(row.ci[1]) + 10, y: y + 4, class: "bar-value" }, `${row.delta > 0 ? "+" : ""}${fmt(row.delta, 3)}`);
  });
  container.appendChild(svg);
}

/* ---------- boot ---------- */

let DATA = {};
const TRACE_CACHE = {};

async function boot() {
  const [overview, repo, docs, ds, det, lat] = await Promise.all([
    fetchJSON("overview.json"),
    fetchJSON("repo_finals.json"),
    fetchJSON("docs_fair.json"),
    fetchJSON("ds1000.json"),
    fetchJSON("determinism.json"),
    fetchJSON("latency.json"),
  ]);
  DATA = { overview, repo, docs, ds, det, lat };

  el("hero-commit").textContent = overview.frozen_commit;
  el("hero-boot").textContent = `${overview.bootstrap.samples.toLocaleString()} × seed ${overview.bootstrap.seed}`;
  el("hero-date").textContent = overview.generated;
  el("gen-model").textContent = overview.generation_model;

  renderVerdicts();
  renderRepo("arb");
  renderTabs();
  renderDocs();
  renderDownstream();
  renderDeterminism();
  renderLatency();
  renderHosted();
  renderClaims();
  renderArtifacts();
  railSpy();
}

/* ---------- verdict cards ---------- */

function renderVerdicts() {
  const { repo, docs, ds, overview } = DATA;
  const arb = repo.arb;
  const rrf = arb.deltas_vs_delphi_candidate.lexical_bm25;
  const cards = [
    {
      cls: "",
      flag: ["flag-win", "Decisive"],
      title: "Repository retrieval · ARB final (220 cases)",
      metric: fmt(arb.aggregates.delphi.MRR, 3),
      small: "MRR",
      sub: `vs ${fmt(arb.aggregates.lexical_bm25.MRR, 3)} for the best local fusion — ` +
        `Δ +${fmt(rrf.MRR.delta, 3)} [${fmt(rrf.MRR.ci[0], 3)}, ${fmt(rrf.MRR.ci[1], 3)}]. ` +
        `Every metric, every baseline: intervals exclude zero.`,
    },
    {
      cls: "",
      flag: ["flag-win", "Criterion met"],
      title: "Documentation · matched output contracts",
      metric: fmt(docs.arms.delphi_synthesis.case_mean, 3),
      small: "identifier hit",
      sub: `vs ${fmt(docs.arms.nia_synthesis.case_mean, 3)} for the hosted synthesis engine — ` +
        `ahead on point estimate, statistically tied ` +
        `[${fmt(docs.paired.delphi_vs_nia.case_cluster_bootstrap_95_ci[0], 2)}, ` +
        `${fmt(docs.paired.delphi_vs_nia.case_cluster_bootstrap_95_ci[1], 2)}]. ` +
        `Model-alone floor: ${fmt(docs.arms.control.case_mean, 3)}.`,
    },
    {
      cls: "tie",
      flag: ["flag-tie", "Unresolved"],
      title: "Downstream coding · DS-1000 pass@1",
      metric: fmt(ds.conditions.delphi_synthesis.mean, 3),
      small: "pass@1",
      sub: `No engine separates from the no-retrieval control ` +
        `(${fmt(ds.conditions.none.mean, 3)}) at n=40 — every 95% interval includes zero.`,
    },
    {
      cls: "blocked",
      flag: ["flag-blocked", "Externally blocked"],
      title: "Hosted repository head-to-head",
      metric: `${overview.nia_repo_status.visible_indexed_pairs}/${overview.nia_repo_status.required_pairs}`,
      small: "snapshots ready",
      sub: "The hosted engine's ingestion queue accepts new sources but does not finish " +
        "indexing them — reproduced on a minimal 1.5 MB shard. Head-to-head runs the " +
        "moment coverage reaches 68/68.",
    },
  ];
  el("verdict-cards").innerHTML = cards
    .map(
      (c) => `<div class="verdict ${c.cls}">
        <div class="v-title">${c.title}</div>
        <div class="v-metric">${c.metric} <small>${c.small}</small></div>
        <div class="v-sub">${c.sub}</div>
        <span class="v-flag ${c.flag[0]}">${c.flag[1]}</span>
      </div>`,
    )
    .join("");
}

/* ---------- repository section ---------- */

function renderTabs() {
  const tabs = [
    ["arb", "ARB final · 220"],
    ["trackd", "SWE-bench · 62"],
    ["independent", "Independent · 18"],
  ];
  const holder = el("track-tabs");
  holder.innerHTML = "";
  tabs.forEach(([key, label], i) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.className = i === 0 ? "active" : "";
    b.onclick = () => {
      holder.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      renderRepo(key);
    };
    holder.appendChild(b);
  });
}

let CURRENT_TRACK = "arb";

function renderRepo(track) {
  CURRENT_TRACK = track;
  const spec = DATA.repo[track];
  el("track-title").textContent = `${spec.title} — ${spec.cases} cases, scored once from frozen code`;
  const chart = el("track-chart");
  chart.innerHTML = "";

  for (const metric of ["MRR", "Recall@20"]) {
    const head = document.createElement("h4");
    head.textContent = metric;
    head.style.cssText = "font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-faint);margin:14px 0 4px";
    chart.appendChild(head);
    const rows = ["delphi", "lexical_bm25", "lexical", "bm25"].map((eng) => ({
      label: ENGINE_LABELS[eng],
      value: spec.aggregates[eng][metric],
      color: eng === "delphi" ? COLORS.delphi : "#a09580",
    }));
    hBarChart(chart, rows, { max: Math.max(0.8, ...rows.map((r) => r.value)) * 1.12 });
  }

  const deltas = spec.deltas_vs_delphi_candidate;
  const metricNames = ["MRR", "Recall@5", "Recall@20", "BCY@8k"];
  let html = `<table><thead><tr><th>Δ Delphi vs</th>${metricNames.map((m) => `<th>${m}</th>`).join("")}<th>any-gold moved</th></tr></thead><tbody>`;
  for (const [eng, d] of Object.entries(deltas)) {
    html += `<tr><td>${ENGINE_LABELS[eng]}</td>`;
    for (const m of metricNames) {
      const cell = d[m];
      if (!cell) { html += "<td>—</td>"; continue; }
      const excl = cell.ci[0] > 0 || cell.ci[1] < 0;
      html += `<td class="${excl ? "win" : "tie"}">${cell.delta > 0 ? "+" : ""}${fmt(cell.delta, 3)}<br><span style="opacity:.65">[${fmt(cell.ci[0], 3)}, ${fmt(cell.ci[1], 3)}]</span></td>`;
    }
    const ag = d.any_gold || {};
    html += `<td>+${ag.recovered ?? "—"} / −${ag.lost ?? "—"}${ag.mcnemar_p != null ? `<br><span style="opacity:.65">p=${Number(ag.mcnemar_p).toExponential(1)}</span>` : ""}</td></tr>`;
  }
  html += "</tbody></table>";
  el("track-deltas").innerHTML = html;

  el("trace-count").textContent = `· ${spec.cases} cases`;
  el("trace-list").innerHTML = "<p class='note' style='padding:10px'>Loading traces…</p>";
  loadTraces(track);
}

async function loadTraces(track) {
  if (!TRACE_CACHE[track]) TRACE_CACHE[track] = await fetchJSON(`traces_${track}.json`);
  if (CURRENT_TRACK !== track) return;
  drawTraces();
}

function bestBaselineHit(engines) {
  return ["lexical_bm25", "lexical", "bm25"].some(
    (e) => engines[e] && engines[e].hit_rank != null,
  );
}

function drawTraces() {
  const rows = TRACE_CACHE[CURRENT_TRACK] || [];
  const q = el("trace-search").value.trim().toLowerCase();
  const mode = el("trace-filter").value;
  const filtered = rows.filter((r) => {
    const hay = `${r.id} ${r.repo} ${r.task_type} ${r.gold.join(" ")} ${r.query}`.toLowerCase();
    if (q && !hay.includes(q)) return false;
    const dHit = r.engines.delphi && r.engines.delphi.hit_rank != null;
    const bHit = bestBaselineHit(r.engines);
    if (mode === "delphi-only") return dHit && !bHit;
    if (mode === "baseline-only") return !dHit && bHit;
    if (mode === "both-miss") return !dHit && !bHit;
    return true;
  });
  const list = el("trace-list");
  list.innerHTML = filtered.length ? "" : "<p class='note' style='padding:10px'>No cases match.</p>";
  for (const r of filtered.slice(0, 250)) list.appendChild(traceCard(r));
  if (filtered.length > 250) {
    const p = document.createElement("p");
    p.className = "note";
    p.textContent = `…and ${filtered.length - 250} more — narrow the filter.`;
    list.appendChild(p);
  }
}

function traceCard(r) {
  const card = document.createElement("div");
  card.className = "case-card";
  const dHit = r.engines.delphi?.hit_rank;
  const head = document.createElement("div");
  head.className = "case-head";
  head.innerHTML = `
    <span class="cid">${esc(r.id)}</span>
    <span class="crepo">${esc(r.repo)}@${esc(r.commit)}</span>
    <span class="ctask">${esc(r.task_type || "")}</span>
    <span class="case-badges">
      <span class="badge ${dHit != null ? "hit" : "miss"}">Delphi ${dHit != null ? "hit @" + dHit : "miss"}</span>
      <span class="badge ${bestBaselineHit(r.engines) ? "hit" : "miss"}" style="opacity:.75">baselines ${bestBaselineHit(r.engines) ? "hit" : "miss"}</span>
    </span>`;
  const body = document.createElement("div");
  body.className = "case-body";
  head.onclick = () => {
    if (!body.dataset.filled) {
      body.dataset.filled = "1";
      body.innerHTML = `
        <div class="case-query">${esc(r.query || "(query withheld from bundle)")}</div>
        <div class="gold-list">gold: ${r.gold.map((g) => `<b>${esc(g)}</b>`).join(" · ")}</div>
        <div class="engine-cols">${["delphi", "lexical_bm25", "lexical", "bm25"]
          .filter((e) => r.engines[e])
          .map((e) => engineCol(e, r.engines[e], new Set(r.gold)))
          .join("")}</div>`;
    }
    card.classList.toggle("open");
  };
  card.appendChild(head);
  card.appendChild(body);
  return card;
}

function engineCol(name, data, goldSet) {
  const items = data.top
    .map((p, i) => {
      const isGold = goldSet.has(p);
      return `<li class="${isGold ? "gold-hit" : ""}">${isGold ? `<span class="rank-badge">${i + 1}</span> ` : ""}${esc(p)}</li>`;
    })
    .join("");
  return `<div class="engine-col">
    <h4>${ENGINE_LABELS[name]} · MRR ${fmt(data.mrr, 2)} · ${data.latency_ms} ms</h4>
    <ol>${items}</ol>
  </div>`;
}

el("trace-search")?.addEventListener("input", drawTraces);
el("trace-filter")?.addEventListener("change", drawTraces);

/* ---------- docs section ---------- */

function renderDocs() {
  const docs = DATA.docs;
  const holder = el("docs-chart");
  holder.innerHTML = "";
  const rows = [];
  const order = ["delphi_synthesis", "nia_synthesis", "context7_synthesis", "control"];
  for (const key of order) {
    const arm = docs.arms[key];
    if (!arm) continue;
    rows.push({
      label: arm.label,
      value: arm.case_mean,
      color:
        key === "delphi_synthesis" ? COLORS.delphi
        : key === "nia_synthesis" ? COLORS.nia
        : key === "context7_synthesis" ? COLORS.context7
        : COLORS.control,
      dots: arm.per_repeat.length > 1 ? arm.per_repeat : null,
    });
  }
  hBarChart(holder, rows, {
    max: 0.75,
    refLine: docs.arms.control.case_mean,
    refLabel: "model-alone floor",
    labelW: 300,
  });

  const p = docs.paired;
  const c7Note = p.context7_vs_nia
    ? `<div class="docs-note-card"><b>Three-way engine tie:</b> Delphi vs N Δ +${fmt(p.delphi_vs_nia.mean_delta, 3)},
      C7 vs N Δ +${fmt(p.context7_vs_nia.mean_delta, 3)}, Delphi vs C7 Δ ${fmt(p.delphi_vs_context7.mean_delta, 3)} —
      every engine-vs-engine interval includes zero. Once synthesis is allowed, this metric stops separating engines.</div>`
    : "";
  el("docs-notes").innerHTML = `
    <div class="docs-note-card"><b>Delphi vs hosted N:</b> Δ ${p.delphi_vs_nia.mean_delta > 0 ? "+" : ""}${fmt(p.delphi_vs_nia.mean_delta, 3)}
      [${fmt(p.delphi_vs_nia.case_cluster_bootstrap_95_ci[0], 3)}, ${fmt(p.delphi_vs_nia.case_cluster_bootstrap_95_ci[1], 3)}] —
      ${p.delphi_vs_nia.wins} wins / ${p.delphi_vs_nia.losses} losses / ${p.delphi_vs_nia.ties} ties. Parity-or-better; superiority unresolved.</div>
    ${c7Note}
    <div class="docs-note-card"><b>Retrieval over the floor:</b> Delphi adds +${fmt(p.delphi_vs_control.mean_delta, 3)}
      [${fmt(p.delphi_vs_control.case_cluster_bootstrap_95_ci[0], 3)}, ${fmt(p.delphi_vs_control.case_cluster_bootstrap_95_ci[1], 3)}]${
        p.context7_vs_control
          ? `; C7 adds +${fmt(p.context7_vs_control.mean_delta, 3)}
      [${fmt(p.context7_vs_control.case_cluster_bootstrap_95_ci[0], 3)}, ${fmt(p.context7_vs_control.case_cluster_bootstrap_95_ci[1], 3)}]`
          : ""
      }; the hosted N engine adds +${fmt(-p.control_vs_nia.mean_delta, 3)}. Roughly half of everyone's score is the model, not retrieval.</div>
    <div class="docs-note-card"><b>Raw-retrieval reference:</b> under raw contracts Delphi reads ${fmt(docs.raw_reference.delphi_compact_k20, 3)} (k=20)
      and hosted C7 ${fmt(docs.raw_reference.context7_guided_compact, 3)}; hosted N exposes no raw mode within the recorded budget.</div>`;

  drawDocsStrip();
  el("docs-count").textContent = `· ${docs.cases.length} cases × all arms`;
  el("docs-search").addEventListener("input", drawDocsCases);
  el("docs-filter").addEventListener("change", drawDocsCases);
  drawDocsCases();
}

function docsOutcome(c) {
  const d = c.delphi.hits.filter(Boolean).length >= 2;
  const n = c.nia.hit;
  if (d && !n) return "delphi-win";
  if (!d && n) return "nia-win";
  if (d && n) return "both";
  return "neither";
}

function drawDocsStrip() {
  const docs = DATA.docs;
  const holder = el("docs-strip");
  holder.innerHTML = "";
  const cell = 17, gap = 3, rows = 4;
  const arms = [
    ["Delphi+synth", (c) => c.delphi.hits.filter(Boolean).length / Math.max(1, c.delphi.hits.length)],
    ["Hosted N", (c) => (c.nia.hit ? 1 : 0)],
    ...(docs.context7_synthesis_available ? [["C7+synth", (c) => c.context7.hits.filter(Boolean).length / Math.max(1, c.context7.hits.length)]] : []),
    ["Model alone", (c) => c.control.hits.filter(Boolean).length / Math.max(1, c.control.hits.length)],
  ];
  const w = docs.cases.length * (cell + gap) + 130;
  const svg = svgTag(w, arms.length * (cell + gap) + 40);
  arms.forEach(([label, fn], ri) => {
    add(svg, "text", { x: 122, y: ri * (cell + gap) + cell - 3, "text-anchor": "end", class: "axis-label" }, label);
    docs.cases.forEach((c, ci) => {
      const v = fn(c);
      add(svg, "rect", {
        x: 130 + ci * (cell + gap),
        y: ri * (cell + gap),
        width: cell, height: cell, rx: 2,
        fill: v === 0 ? "#e7ddc8" : `rgba(142,47,34,${0.25 + 0.75 * v})`,
        class: "strip-cell",
      }).appendChild(
        (() => { const t = document.createElementNS("http://www.w3.org/2000/svg", "title"); t.textContent = `case ${c.id} (${c.library}) — ${label}: ${pct(v, 0)}`; return t; })(),
      );
    });
  });
  docs.cases.forEach((c, ci) => {
    if (ci % 5 === 0)
      add(svg, "text", { x: 130 + ci * (cell + gap), y: arms.length * (cell + gap) + 14, class: "axis-label" }, c.id);
  });
  holder.appendChild(svg);
}

function markIdentifiers(text, identifiers) {
  let safe = esc(text);
  for (const ident of identifiers) {
    if (!ident) continue;
    const escaped = esc(ident).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    safe = safe.replace(new RegExp(escaped, "gi"), (m) => `<mark>${m}</mark>`);
  }
  return safe;
}

function drawDocsCases() {
  const docs = DATA.docs;
  const q = el("docs-search").value.trim().toLowerCase();
  const mode = el("docs-filter").value;
  const list = el("docs-list");
  list.innerHTML = "";
  const filtered = docs.cases.filter((c) => {
    const hay = `${c.id} ${c.library} ${c.gold_identifiers.join(" ")}`.toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (mode !== "all" && docsOutcome(c) !== mode) return false;
    return true;
  });
  if (!filtered.length) list.innerHTML = "<p class='note' style='padding:10px'>No cases match.</p>";
  for (const c of filtered) list.appendChild(docsCard(c));
}

function docsCard(c) {
  const card = document.createElement("div");
  card.className = "case-card";
  const dHit = c.delphi.hits.filter(Boolean).length;
  const head = document.createElement("div");
  head.className = "case-head";
  head.innerHTML = `
    <span class="cid">case ${esc(c.id)}</span>
    <span class="crepo">${esc(c.library)}</span>
    <span class="ctask">gold: ${c.gold_identifiers.map(esc).join(", ")}</span>
    <span class="case-badges">
      <span class="badge ${dHit >= 2 ? "hit" : "miss"}">Delphi ${dHit}/${c.delphi.hits.length}</span>
      <span class="badge ${c.nia.hit ? "hit" : "miss"}">N ${c.nia.hit ? "hit" : "miss"}</span>
    </span>`;
  const body = document.createElement("div");
  body.className = "case-body";
  head.onclick = () => {
    if (!body.dataset.filled) {
      body.dataset.filled = "1";
      const tabs = [];
      c.delphi.synth_texts.forEach((t, i) => tabs.push([`Delphi r${i + 1} ${c.delphi.hits[i] ? "✓" : "✗"}`, t]));
      tabs.push([`Hosted N ${c.nia.hit ? "✓" : "✗"}`, c.nia.synth_text]);
      if (c.context7.synth_texts.length)
        c.context7.synth_texts.forEach((t, i) => tabs.push([`C7 r${i + 1} ${c.context7.hits[i] ? "✓" : "✗"}`, t]));
      c.control.texts.forEach((t, i) => tabs.push([`Model r${i + 1} ${c.control.hits[i] ? "✓" : "✗"}`, t]));
      const tabRow = document.createElement("div");
      tabRow.className = "synth-tabs";
      const textBox = document.createElement("div");
      textBox.className = "synth-text";
      tabs.forEach(([label, text], i) => {
        const b = document.createElement("button");
        b.textContent = label;
        if (i === 0) b.classList.add("active");
        b.onclick = (ev) => {
          ev.stopPropagation();
          tabRow.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
          b.classList.add("active");
          textBox.innerHTML = markIdentifiers(text || "(empty)", c.gold_identifiers);
        };
        tabRow.appendChild(b);
      });
      textBox.innerHTML = markIdentifiers(tabs[0][1] || "(empty)", c.gold_identifiers);
      const paths = document.createElement("div");
      paths.className = "gold-list";
      paths.innerHTML = `Delphi retrieved: ${c.delphi.retrieved_paths.slice(0, 5).map(esc).join(" · ") || "—"}`;
      body.appendChild(paths);
      body.appendChild(tabRow);
      body.appendChild(textBox);
    }
    card.classList.toggle("open");
  };
  card.appendChild(head);
  card.appendChild(body);
  return card;
}

/* ---------- downstream ---------- */

function renderDownstream() {
  const ds = DATA.ds;
  const holder = el("gen-chart");
  holder.innerHTML = "";
  const order = ["nia_synthesis", "delphi_synthesis", "none", "context7_guided"];
  hBarChart(
    holder,
    order.map((k) => ({
      label: ds.conditions[k].label,
      value: ds.conditions[k].mean,
      color: k === "delphi_synthesis" ? COLORS.delphi : k === "nia_synthesis" ? COLORS.nia : k === "context7_guided" ? COLORS.context7 : COLORS.control,
      dots: ds.conditions[k].per_repeat,
    })),
    { max: 0.8, refLine: ds.conditions.none.mean, refLabel: "no-retrieval control", labelW: 300 },
  );
  const holder2 = document.createElement("div");
  holder2.style.marginTop = "18px";
  deltaChart(holder2, [
    { label: "Hosted N vs no retrieval", delta: ds.paired.nia_vs_none.delta, ci: ds.paired.nia_vs_none.ci },
    { label: "Delphi+synthesis vs no retrieval", delta: ds.paired.delphi_synthesis_vs_none.delta, ci: ds.paired.delphi_synthesis_vs_none.ci },
    { label: "Hosted C7 vs no retrieval", delta: ds.paired.context7_vs_none.delta, ci: ds.paired.context7_vs_none.ci },
    { label: "Delphi+synthesis vs hosted N", delta: ds.paired.delphi_synthesis_vs_nia.delta, ci: ds.paired.delphi_synthesis_vs_nia.ci },
  ]);
  holder.appendChild(holder2);
  el("gen-note").textContent =
    "Dots are per-repeat pass rates. Every paired 95% interval includes zero: at 40 cases, " +
    "no retrieval condition demonstrably helps or hurts this generator on DS-1000.";

  const m = el("gen-matrix");
  m.innerHTML = "";
  const conds = ["none", "delphi_synthesis", "nia_synthesis", "context7_guided"];
  const cell = 17, gap = 3;
  const w = ds.cases.length * (cell + gap) + 190;
  const svg = svgTag(w, conds.length * (cell + gap) + 40);
  conds.forEach((k, ri) => {
    add(svg, "text", { x: 182, y: ri * (cell + gap) + cell - 3, "text-anchor": "end", class: "axis-label" }, ds.conditions[k].label);
    ds.cases.forEach((c, ci) => {
      const passes = c.passes[k] || [];
      const v = passes.filter(Boolean).length / Math.max(1, passes.length);
      const r = add(svg, "rect", {
        x: 190 + ci * (cell + gap), y: ri * (cell + gap),
        width: cell, height: cell, rx: 2,
        fill: v === 0 ? "#e7ddc8" : `rgba(30,95,91,${0.2 + 0.8 * v})`,
      });
      const t = document.createElementNS("http://www.w3.org/2000/svg", "title");
      t.textContent = `case ${c.id} (${c.library}) — ${ds.conditions[k].label}: ${passes.filter(Boolean).length}/${passes.length} repeats pass`;
      r.appendChild(t);
    });
  });
  ds.cases.forEach((c, ci) => {
    if (ci % 5 === 0) add(svg, "text", { x: 190 + ci * (cell + gap), y: conds.length * (cell + gap) + 14, class: "axis-label" }, c.id);
  });
  m.appendChild(svg);
}

/* ---------- determinism ---------- */

function renderDeterminism() {
  const det = DATA.det;
  const holder = el("det-grids");
  holder.innerHTML = "";
  for (const key of ["delphi", "context7", "nia"]) {
    const engine = det[key];
    if (!engine) continue;
    const card = document.createElement("div");
    card.className = "det-card";
    card.innerHTML = `<h3>${esc(engine.label)}</h3>
      <div class="det-rate" style="color:${key === "delphi" ? "#2e6b34" : key === "nia" ? "#b03a2e" : "#b8860b"}">${pct(engine.pairwise_exact_context, 1)}</div>
      <p class="note" style="margin:0 0 10px">pairwise byte-identical context across ${engine.runs} runs × ${engine.cases} cases</p>`;
    const cell = 20, gap = 4;
    const svg = svgTag(engine.runs * (cell + gap) + 70, engine.cases * (cell + gap) + 26);
    engine.matrix.forEach((row, ri) => {
      add(svg, "text", { x: 40, y: ri * (cell + gap) + 15, "text-anchor": "end", class: "axis-label" }, row.case);
      row.runs.forEach((c, ci) => {
        add(svg, "rect", {
          x: 50 + ci * (cell + gap), y: ri * (cell + gap),
          width: cell, height: cell, rx: 3,
          fill: c.exact ? (key === "delphi" ? "#2e6b34" : key === "nia" ? "#1e5f5b" : "#b8860b") : "#e7ddc8",
          opacity: c.exact ? 0.85 : 1,
          stroke: c.hit ? "#1c1712" : "none",
          "stroke-width": c.hit ? 1.6 : 0,
        });
      });
    });
    add(svg, "text", { x: 50, y: engine.cases * (cell + gap) + 16, class: "axis-label" }, "runs 1→10; outlined = identifier hit");
    card.appendChild(svg);
    holder.appendChild(card);
  }
}

/* ---------- latency ---------- */

function renderLatency() {
  const lat = DATA.lat;
  const holder = el("latency-chart");
  holder.innerHTML = "";
  const rows = [
    ["delphi_retrieval", "Delphi retrieval (docs, local)", COLORS.delphi],
    ["delphi_synthesis_stage", "Delphi synthesis stage (frozen model)", COLORS.ox_soft || "#b4543f"],
    ["context7_retrieval", "Hosted C7 retrieval", COLORS.context7],
    ["nia_retrieval_synthesis", "Hosted N retrieval+synthesis", COLORS.nia],
  ];
  const width = 760, labelW = 320, rowH = 46;
  const max = Math.max(...rows.map(([k]) => lat.docs[k].p95_ms)) * 1.1;
  const svg = svgTag(width, rows.length * rowH + 40);
  const x = (v) => labelW + (v / max) * (width - labelW - 40);
  rows.forEach(([key, label, color], i) => {
    const d = lat.docs[key];
    const y = i * rowH + 22;
    add(svg, "text", { x: labelW - 12, y: y + 4, "text-anchor": "end", class: "bar-name" }, label);
    for (const v of d.values) add(svg, "circle", { cx: x(v), cy: y + (Math.random() * 10 - 5), r: 2.4, fill: color, opacity: 0.3 });
    add(svg, "line", { x1: x(d.median_ms), x2: x(d.median_ms), y1: y - 12, y2: y + 12, stroke: "#1c1712", "stroke-width": 2.4 });
    add(svg, "text", { x: x(d.median_ms) + 6, y: y - 12, class: "bar-value" }, `${(d.median_ms / 1000).toFixed(1)}s median`);
  });
  add(svg, "text", { x: labelW, y: rows.length * rowH + 26, class: "axis-label" }, "each dot = one request; docs development track, 40 cases");
  holder.appendChild(svg);
  el("latency-note").textContent =
    `End-to-end docs answer for Delphi ≈ retrieval median ${(lat.docs.delphi_retrieval.median_ms / 1000).toFixed(1)}s + synthesis median ${(lat.docs.delphi_synthesis_stage.median_ms / 1000).toFixed(1)}s, ` +
    `vs ${(lat.docs.nia_retrieval_synthesis.median_ms / 1000).toFixed(1)}s for the hosted synthesis engine. Confirmatory repository runs use the deterministic exact-scan configuration ` +
    `(median ${(lat.repo_final_delphi.median_ms / 1000).toFixed(1)}s), which is audited for reproducibility, not tuned for latency.`;
}

/* ---------- hosted status ---------- */

function renderHosted() {
  const s = DATA.overview.nia_repo_status;
  const smoke = (s.smoke || []).filter((r) => r.provenance === "fresh");
  el("hosted-status").innerHTML = `
  <div class="hosted-card">
    <p>The hosted engine's repository arm requires all <b>${s.required_pairs}</b> commit-pinned snapshots
    of the development corpus to be indexed in its account before any comparison is valid — partial
    coverage would silently skip cases and flatter whoever covered more. Current state:</p>
    <ul class="timeline">
      <li class="ok"><b>${s.visible_indexed_pairs}/${s.required_pairs}</b> snapshots already terminally indexed
        on the owned account (reused from the prior evaluation round, sharded scheme).</li>
      <li class="bad">Whole-snapshot ingestion of large repositories stalls in <span class="mono">syncing</span>
        indefinitely — observed on etcd, tokio, and transformers snapshots for &gt;24 h.</li>
      <li class="bad">A minimal probe — one <span class="mono">≤1.5 MB, ≤100-file</span> shard, the smallest unit
        the API accepts — was accepted by the sync API and then also failed to leave
        <span class="mono">syncing</span> within a 40-minute deadline
        ${smoke.length ? `(<span class="mono">${esc(smoke[0].repo)}@${esc(String(smoke[0].revision).slice(0, 10))}</span>, ${Math.round(smoke[0].elapsed_s / 60)} min)` : ""}.</li>
      <li class="bad">A 3-hour watcher then polled the probe every 10 minutes: all 18 polls returned
        <span class="mono">syncing</span> — no late completion, ~3.7 h total from sync acceptance.
        The ingestion hypothesis is closed rejected on its predeclared disconfirmer.</li>
      <li>The 36-pair fan-out never launched (fail-closed). The head-to-head runs the moment a fresh
        single-shard smoke demonstrably reaches terminal indexed state.</li>
    </ul>
    <p class="note">This is recorded as an external blocker, not a loss: no score is reported for an
    engine that cannot reach required coverage, in either direction.</p>
  </div>`;
}

/* ---------- claims ---------- */

function renderClaims() {
  const repo = DATA.repo;
  const docs = DATA.docs;
  el("claims-do").innerHTML = `
    <li>On the untouched ARB final (220 cases), Delphi beats every runnable baseline on all four
    metrics with repository-cluster 95% intervals excluding zero.</li>
    <li>On SWE-bench localization (62 cases), Delphi leads MRR decisively
    (+${fmt(repo.trackd.deltas_vs_delphi_candidate.lexical.MRR.delta, 3)} vs the strongest baseline) and ties Recall@20.</li>
    <li>On the independent final (18 cases), Delphi leads or ties every comparator; no interval shows a loss.</li>
    <li>Under matched output contracts, Delphi retrieval + a frozen synthesis stage reaches
    ${fmt(docs.arms.delphi_synthesis.case_mean, 3)} identifier-hit vs ${fmt(docs.arms.nia_synthesis.case_mean, 3)}
    for the hosted synthesis engine — parity or better, at less than half the latency.</li>
    <li>Delphi's documentation retrieval is near-deterministic (${pct(DATA.det.delphi.pairwise_exact_context, 1)}
    pairwise exact context); hosted engines are not (${pct(DATA.det.context7.pairwise_exact_context, 1)} and
    ${pct(DATA.det.nia.pairwise_exact_context, 1)}).</li>`;
  el("claims-dont").innerHTML = `
    <li><b>No universal state-of-the-art claim.</b> The hosted repository head-to-head is externally
    blocked at ${DATA.overview.nia_repo_status.visible_indexed_pairs}/${DATA.overview.nia_repo_status.required_pairs} coverage;
    the claim rule requires the complete comparable engine set.</li>
    <li><b>No statistical superiority on documentation.</b> The +${fmt(docs.paired.delphi_vs_nia.mean_delta, 3)} delta's
    interval includes zero; we claim parity-or-better only.</li>
    <li><b>No downstream utility claim — for anyone.</b> All DS-1000 deltas vs the no-retrieval control
    are unresolved at n=40, including the hosted engines'.</li>
    <li><b>No claim from the rejected candidate.</b> The file-level lexical branch failed its preregistered
    adoption gates and ships default-off; its rejection is recorded, not hidden.</li>`;
}

/* ---------- artifacts ---------- */

function renderArtifacts() {
  const names = [
    "A-final-delphi-generated-source-exact-top20-v1-{summary,details}",
    "A-final-{bm25,lexical,lexical-bm25}-generated-policy-v1",
    "arb_final_delphi_vs_{bm25,lexical,lexical-bm25}_v1.json",
    "I-final-delphi-generated-source-exact-top20-v1 + comparators",
    "independent_final_delphi_vs_*_v1.json",
    "D-final-delphi-generated-source-exact-top20-v1 + comparators",
    "trackd_final_delphi_vs_*_v1.json",
    "DOCS-dev-delphi-answer-synth-r{1..3}-{details,summary}.json",
    "DOCS-dev-control-synth-r{1..3}-{details,summary}.json",
    "DOCS-dev-context7-answer-synth-r{1..3}-{details,summary}.json",
    "DOCS-dev-answer-synthesis-analysis-v1.json",
    "DOCS-dev-nia-answer-full-details.json (recorded hosted pass)",
    "GEN-dev-{none,delphi-synthesis,nia-full,context7-guided}-gpt54mini ×3 repeats",
    "GEN-ANALYSIS-*.json (paired case-cluster bootstraps)",
    "determinism/{delphi,context7,nia}/docs-*-r{1..10}-details.json",
    "nia-accounting-repository-readiness-20260824.json",
    "nia-sharded-sources.jsonl (ingestion probe ledger)",
    "harness/build_blog_data.py (this page's only data source)",
  ];
  el("artifact-list").innerHTML = names.map((n) => `<div>${esc(n)}</div>`).join("");
}

/* ---------- rail scroll spy ---------- */

function railSpy() {
  const links = [...document.querySelectorAll("#rail a")];
  const map = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
  const observer = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          links.forEach((a) => a.classList.remove("active"));
          map.get(e.target.id)?.classList.add("active");
        }
      }
    },
    { rootMargin: "-30% 0px -60% 0px" },
  );
  document.querySelectorAll("main section").forEach((s) => observer.observe(s));
}

boot().catch((err) => {
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div style="background:#b03a2e;color:#fff;padding:12px 20px;font-family:monospace">
      Failed to load data: ${esc(err.message)} — serve this folder over HTTP and re-run build_blog_data.py.
    </div>`,
  );
  console.error(err);
});
