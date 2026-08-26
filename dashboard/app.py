"""Local benchmark dashboard: every run, per-case results, and full traces."""
from __future__ import annotations

import html
import json
import sqlite3
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "runstore.db"

app = FastAPI(title="Delphi research round 3")


def q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


STYLE = """
<style>
:root { --bg:#141210; --panel:#1e1a17; --line:#332c26; --text:#e8e0d8; --dim:#9a8f83;
        --accent:#d98e4a; --good:#7fb069; --bad:#d95d5d; --link:#e0b07f; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--text); font:14px/1.5 "SF Mono", ui-monospace, Menlo, monospace;
       margin:0; padding:24px 32px 80px; }
h1,h2,h3 { font-weight:600; letter-spacing:.01em; }
h1 { font-size:19px; margin:0 0 4px; } h1 a { color:var(--text); text-decoration:none; }
h2 { font-size:15px; color:var(--accent); margin:28px 0 10px; }
.sub { color:var(--dim); font-size:12px; margin-bottom:20px; }
table { border-collapse:collapse; width:100%; margin:8px 0 16px; font-size:13px; }
th { text-align:left; color:var(--dim); font-weight:500; padding:6px 10px; border-bottom:1px solid var(--line);
     white-space:nowrap; }
td { padding:5px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
tr:hover td { background:var(--panel); }
a { color:var(--link); text-decoration:none; } a:hover { text-decoration:underline; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.best { color:var(--good); font-weight:700; }
.badge { padding:1px 7px; border-radius:9px; font-size:11px; }
.badge.done { background:#2b3a26; color:var(--good); } .badge.running { background:#3a3226; color:var(--accent); }
.badge.error { background:#3a2626; color:var(--bad); }
.hit { color:var(--good); } .miss { color:var(--dim); }
pre { background:var(--panel); border:1px solid var(--line); padding:12px; border-radius:6px;
      overflow-x:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; }
.kv { color:var(--dim); } .kv b { color:var(--text); font-weight:500; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:10px 0; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:10px 14px; }
.card .v { font-size:20px; color:var(--accent); font-weight:700; } .card .k { font-size:11px; color:var(--dim); }
</style>
"""


def page(title: str, body: str, *, refresh: int | None = 15) -> HTMLResponse:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return HTMLResponse(
        f"<!doctype html><html><head><meta charset='utf-8'>{meta}<title>{html.escape(title)}</title>"
        f"{STYLE}</head><body><h1><a href='/'>delphi · research round 3</a></h1>"
        f"<div class='sub'>{time.strftime('%Y-%m-%d %H:%M:%S')} · local benchmark runs, traces, comparisons</div>"
        f"{body}</body></html>"
    )


def fmt(value, digits=3):
    if value is None:
        return "·"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


HEADLINE = ["MRR", "Recall@5", "Recall@20", "BCY@8k"]


def headline_metrics(metrics_json: str | None) -> dict:
    if not metrics_json:
        return {}
    metrics = json.loads(metrics_json)
    flat = metrics.get("sample_weighted") or metrics
    out = {}
    for name in HEADLINE:
        if isinstance(flat, dict) and isinstance(flat.get(name), (int, float)):
            out[name] = flat[name]
    for extra in ("latency_ms_mean", "file_f1", "success_rate", "exact_repeat_rate", "pass_rate"):
        if isinstance(metrics.get(extra), (int, float)):
            out[extra] = metrics[extra]
    if isinstance(metrics.get("latency_ms"), dict) and "mean" in metrics["latency_ms"]:
        out["latency_ms_mean"] = metrics["latency_ms"]["mean"]
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    runs = q("SELECT * FROM runs ORDER BY created_at DESC")
    tracks: dict[str, list[sqlite3.Row]] = {}
    for run in runs:
        tracks.setdefault(run["track"], []).append(run)
    body = ""
    for track, rows in tracks.items():
        body += f"<h2>{html.escape(track)}</h2><table><tr><th>run</th><th>system</th><th>split</th>"
        body += "".join(f"<th class='num'>{m}</th>" for m in HEADLINE)
        body += "<th class='num'>lat(ms)</th><th class='num'>n</th><th>status</th><th>when</th></tr>"
        # find best per metric within track (done runs only)
        best: dict[str, float] = {}
        for run in rows:
            if run["status"] != "done":
                continue
            hm = headline_metrics(run["metrics"])
            for name in HEADLINE:
                if name in hm and hm[name] > best.get(name, -1):
                    best[name] = hm[name]
        for run in rows:
            hm = headline_metrics(run["metrics"])
            cells = ""
            for name in HEADLINE:
                v = hm.get(name)
                cls = "num best" if name in best and v is not None and abs(v - best[name]) < 1e-9 else "num"
                cells += f"<td class='{cls}'>{fmt(v)}</td>"
            lat = hm.get("latency_ms_mean")
            body += (
                f"<tr><td><a href='/run/{run['run_id']}'>{html.escape(run['run_id'])}</a></td>"
                f"<td>{html.escape(run['system'])}</td><td>{html.escape(run['split'])}</td>{cells}"
                f"<td class='num'>{fmt(lat, 0)}</td><td class='num'>{run['n_cases']}</td>"
                f"<td><span class='badge {run['status']}'>{run['status']}</span></td>"
                f"<td class='kv'>{time.strftime('%m-%d %H:%M', time.localtime(run['created_at']))}</td></tr>"
            )
        body += "</table>"
    if not runs:
        body = "<p class='kv'>No runs yet.</p>"
    return page("runs", body)


@app.get("/run/{run_id}", response_class=HTMLResponse)
def run_view(run_id: str):
    runs = q("SELECT * FROM runs WHERE run_id=?", (run_id,))
    if not runs:
        return page("missing", "<p>run not found</p>", refresh=None)
    run = runs[0]
    metrics = json.loads(run["metrics"]) if run["metrics"] else {}
    cases = q("SELECT * FROM cases WHERE run_id=? ORDER BY workflow, case_id", (run_id,))
    hm = headline_metrics(run["metrics"])
    cards = "".join(
        f"<div class='card'><div class='v'>{fmt(v)}</div><div class='k'>{k}</div></div>" for k, v in hm.items()
    )
    body = f"<h2>{html.escape(run_id)} <span class='badge {run['status']}'>{run['status']}</span></h2>"
    body += f"<div class='grid'>{cards}</div>"
    body += f"<details><summary class='kv'>config</summary><pre>{html.escape(json.dumps(json.loads(run['config']), indent=2))}</pre></details>"
    if metrics.get("by_workflow"):
        body += "<h2>by workflow</h2><table><tr><th>workflow</th><th class='num'>n</th>"
        names = HEADLINE
        body += "".join(f"<th class='num'>{m}</th>" for m in names) + "</tr>"
        for wf, data in sorted(metrics["by_workflow"].items()):
            wf_metrics = data.get("metrics", {})
            body += f"<tr><td>{html.escape(wf)}</td><td class='num'>{data.get('n')}</td>"
            body += "".join(f"<td class='num'>{fmt(wf_metrics.get(m))}</td>" for m in names) + "</tr>"
        body += "</table>"
    if metrics and not cases:
        body += f"<h2>summary</h2><pre>{html.escape(json.dumps(metrics, indent=2, sort_keys=True)[:6000])}</pre>"
    if cases:
        body += f"<h2>cases ({len(cases)})</h2><table><tr><th>case</th><th>workflow</th><th>repo</th>"
        body += "<th class='num'>MRR</th><th class='num'>R@5</th><th class='num'>R@20</th><th class='num'>lat(ms)</th><th>first hit</th></tr>"
        for case in cases:
            m = json.loads(case["metrics"] or "{}")
            ranked = json.loads(case["ranked"] or "[]")
            gold = set(json.loads(case["gold"] or "[]"))
            first_hit = next((i + 1 for i, p in enumerate(ranked) if p in gold), None)
            fh = f"<span class='hit'>#{first_hit}</span>" if first_hit else "<span class='miss'>—</span>"
            body += (
                f"<tr><td><a href='/case/{run_id}/{case['case_id']}'>{html.escape(case['case_id'][:16])}</a></td>"
                f"<td>{html.escape(case['workflow'] or '')}</td><td>{html.escape((case['repo'] or '').split('/')[-1])}</td>"
                f"<td class='num'>{fmt(m.get('MRR'))}</td><td class='num'>{fmt(m.get('Recall@5'))}</td>"
                f"<td class='num'>{fmt(m.get('Recall@20'))}</td><td class='num'>{fmt(case['latency_ms'], 0)}</td>"
                f"<td>{fh}</td></tr>"
            )
        body += "</table>"
    return page(run_id, body, refresh=15 if run["status"] == "running" else None)


@app.get("/case/{run_id}/{case_id}", response_class=HTMLResponse)
def case_view(run_id: str, case_id: str):
    rows = q("SELECT * FROM cases WHERE run_id=? AND case_id=?", (run_id, case_id))
    if not rows:
        return page("missing", "<p>case not found</p>", refresh=None)
    case = rows[0]
    ranked = json.loads(case["ranked"] or "[]")
    gold = set(json.loads(case["gold"] or "[]"))
    trace = json.loads(case["trace"] or "{}")
    body = f"<h2>{html.escape(case_id)} <span class='kv'>({html.escape(run_id)})</span></h2>"
    body += f"<p class='kv'><b>{html.escape(case['repo'] or '')}</b> @ {html.escape((case['revision'] or '')[:12])} · {html.escape(case['workflow'] or '')} · {fmt(case['latency_ms'],0)} ms</p>"
    body += f"<h2>metrics</h2><pre>{html.escape(json.dumps(json.loads(case['metrics'] or '{}'), indent=2, sort_keys=True))}</pre>"
    body += "<h2>ranked files vs gold</h2><table><tr><th>#</th><th>path</th><th>gold?</th></tr>"
    for i, path in enumerate(ranked):
        mark = "<span class='hit'>HIT</span>" if path in gold else ""
        body += f"<tr><td class='num'>{i+1}</td><td>{html.escape(path)}</td><td>{mark}</td></tr>"
    missing = gold.difference(ranked)
    for path in sorted(missing):
        body += f"<tr><td class='num'>·</td><td class='miss'>{html.escape(path)}</td><td><span class='miss'>MISSED GOLD</span></td></tr>"
    body += "</table>"
    if trace:
        body += f"<h2>trace</h2><pre>{html.escape(json.dumps(trace, indent=2, sort_keys=True)[:20000])}</pre>"
    return page(case_id, body, refresh=None)


@app.get("/compare", response_class=HTMLResponse)
def compare(a: str, b: str):
    rows_a = {r["case_id"]: r for r in q("SELECT * FROM cases WHERE run_id=?", (a,))}
    rows_b = {r["case_id"]: r for r in q("SELECT * FROM cases WHERE run_id=?", (b,))}
    shared = sorted(set(rows_a) & set(rows_b))
    body = f"<h2>compare</h2><p class='kv'>A = <a href='/run/{a}'>{html.escape(a)}</a><br>B = <a href='/run/{b}'>{html.escape(b)}</a><br>{len(shared)} shared cases</p>"
    wins = losses = ties = 0
    rows_html = ""
    for cid in shared:
        ma = json.loads(rows_a[cid]["metrics"] or "{}").get("MRR", 0.0)
        mb = json.loads(rows_b[cid]["metrics"] or "{}").get("MRR", 0.0)
        if abs(ma - mb) < 1e-9:
            ties += 1
            continue
        if ma > mb:
            wins += 1
        else:
            losses += 1
        cls_a = "hit" if ma > mb else "miss"
        cls_b = "hit" if mb > ma else "miss"
        rows_html += (
            f"<tr><td><a href='/case/{a}/{cid}'>{html.escape(cid[:16])}</a></td>"
            f"<td>{html.escape(rows_a[cid]['workflow'] or '')}</td>"
            f"<td class='num {cls_a}'>{ma:.3f}</td><td class='num {cls_b}'>{mb:.3f}</td>"
            f"<td><a href='/case/{b}/{cid}'>b-trace</a></td></tr>"
        )
    body += f"<p>MRR per case: <b class='hit'>A wins {wins}</b> · <b class='miss'>B wins {losses}</b> · {ties} ties</p>"
    body += f"<table><tr><th>case</th><th>workflow</th><th class='num'>A MRR</th><th class='num'>B MRR</th><th></th></tr>{rows_html}</table>"
    return page("compare", body, refresh=None)


@app.get("/api/runs")
def api_runs():
    return JSONResponse([dict(r) for r in q("SELECT * FROM runs ORDER BY created_at DESC")])


@app.get("/api/run/{run_id}")
def api_run(run_id: str):
    runs = [dict(r) for r in q("SELECT * FROM runs WHERE run_id=?", (run_id,))]
    cases = [dict(r) for r in q("SELECT * FROM cases WHERE run_id=?", (run_id,))]
    return JSONResponse({"run": runs[0] if runs else None, "cases": cases})
