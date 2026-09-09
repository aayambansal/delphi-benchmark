"""Generate the paper's result tables directly from recorded artifacts.

Every number in paper/tables/*.tex is read from results/*-summary.json,
results/*-details.jsonl, and the paired-analysis JSON files, so the tables
cannot drift from the evidence. Re-run after adding artifacts:

    python harness/paper_tables.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = ROOT / "paper" / "tables"

LADDER = [
    ("dense", "Dense (same embedding)"),
    ("hybrid", "Dense+BM25 RRF"),
    ("hybrid_rerank", "\\quad + Delphi's rerankers"),
    ("hybrid_rerank_expand", "\\quad + expansion"),
]
LEXICAL = [
    ("lexical_bm25", "Lexical+BM25 RRF"),
    ("lexical", "Lexical ranker"),
    ("bm25", "BM25"),
]

TRACKS = {
    "independent": {
        "delphi": "I-final-delphi-generated-source-exact-top20-v1",
        "ladder": "I-final-{eng}-r4-v1",
        "lexical": {
            "lexical_bm25": "I-final-lexical_bm25-generated-policy-v1",
            "lexical": "I-final-lexical-generated-policy-v1",
            "bm25": "I-final-bm25-generated-policy-v1",
        },
        "pair_ladder": "independent_final_delphi_vs_{eng}_r4_v1.json",
        "pair_lexical": {
            "lexical_bm25": "independent_final_delphi_vs_lexical_bm25_v1.json",
            "lexical": "independent_final_delphi_vs_lexical_v1.json",
            "bm25": "independent_final_delphi_vs_bm25_v1.json",
        },
    },
    "swebench": {
        "delphi": "D-final-delphi-generated-source-exact-top20-v1",
        "ladder": "D-final-{eng}-r4-v1",
        "lexical": {
            "lexical_bm25": "D-final-lexical_bm25-generated-policy-v1",
            "lexical": "D-final-lexical-generated-policy-v1",
            "bm25": "D-final-bm25-generated-policy-v1",
        },
        "pair_ladder": "trackd_final_delphi_vs_{eng}_r4_v1.json",
        "pair_lexical": {
            "lexical_bm25": "trackd_final_delphi_vs_lexicalbm25_v1.json",
            "lexical": "trackd_final_delphi_vs_lexical_v1.json",
            "bm25": "trackd_final_delphi_vs_bm25_v1.json",
        },
    },
    "swebench_expansion": {
        "delphi": "D2-final-delphi-generated-source-exact-top20-v1",
        "ladder": "D2-final-{eng}-r4-v1",
        "lexical": {
            "lexical_bm25": "D2-final-lexical_bm25-r4-v1",
            "lexical": "D2-final-lexical-r4-v1",
            "bm25": "D2-final-bm25-r4-v1",
        },
        "pair_ladder": "swebench_expansion_delphi_vs_{eng}_r4_v1.json",
        "pair_lexical": {
            "lexical_bm25": "swebench_expansion_delphi_vs_lexical_bm25_r4_v1.json",
            "lexical": "swebench_expansion_delphi_vs_lexical_r4_v1.json",
            "bm25": "swebench_expansion_delphi_vs_bm25_r4_v1.json",
        },
    },
    "arb": {
        "delphi": "A-final-delphi-generated-source-exact-top20-v1",
        "ladder": "A-final-{eng}-r4-v1",
        "lexical": {
            "lexical_bm25": "A-final-lexical-bm25-generated-policy-v1",
            "lexical": "A-final-lexical-generated-policy-v1",
            "bm25": "A-final-bm25-generated-policy-v1",
        },
        "pair_ladder": "arb_final_delphi_vs_{eng}_r4_v1.json",
        "pair_lexical": {
            "lexical_bm25": "arb_final_delphi_vs_lexical-bm25_v1.json",
            "lexical": "arb_final_delphi_vs_lexical_v1.json",
            "bm25": "arb_final_delphi_vs_bm25_v1.json",
        },
    },
}

METRICS = [("MRR", "MRR"), ("Recall@5", "R@5"), ("Recall@20", "R@20"), ("BCY@8k", "BCY@8k")]


def summary(run_id: str) -> dict | None:
    path = RESULTS / f"{run_id}-summary.json"
    return json.load(path.open()) if path.exists() else None


def any_gold(run_id: str, k: int = 20) -> tuple[int, int] | None:
    path = RESULTS / f"{run_id}-details.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(l) for l in path.open() if l.strip()]
    hits = sum(1 for r in rows if any(g in (r.get("top_files") or [])[:k] for g in r.get("gold_files") or []))
    return hits, len(rows)


def fmt(value: float | None) -> str:
    return "---" if value is None else f"{value:.3f}"


def delta_cell(pair: dict | None, metric: str) -> str:
    if pair is None or metric not in pair.get("metrics", {}):
        return "---"
    m = pair["metrics"][metric]
    lo, hi = m["repo_cluster_bootstrap_95_ci"]
    d = m["mean_delta"]
    star = "$^{*}$" if (lo > 0 or hi < 0) else ""
    return f"${d:+.3f}${star} \\ci{{{lo:+.3f}}}{{{hi:+.3f}}}"


def system_row(label: str, run_id: str, *, best: dict[str, float] | None = None) -> str | None:
    """One system row; a metric cell is bold when it is the best value in its column."""
    s = summary(run_id)
    if s is None:
        return None
    m = s["sample_weighted"]
    ag = any_gold(run_id)
    cells = []
    for k, _ in METRICS:
        cell = fmt(m.get(k))
        if best and m.get(k) is not None and abs(m[k] - best[k]) < 1e-9:
            cell = f"\\textbf{{{cell}}}"
        cells.append(cell)
    agc = f"{ag[0]}/{ag[1]}" if ag else "---"
    lat = s.get("latency_ms", {}).get("median")
    latc = f"{lat / 1000:.1f}" if lat else "---"
    return f"{label} & " + " & ".join(cells) + f" & {agc} & {latc} \\\\"


def column_best(run_ids: list[str]) -> dict[str, float]:
    best: dict[str, float] = {}
    for run_id in run_ids:
        s = summary(run_id)
        if s is None:
            continue
        for k, _ in METRICS:
            v = s["sample_weighted"].get(k)
            if v is not None and (k not in best or v > best[k]):
                best[k] = v
    return best


LADDER_HEAD = (
    "\\begin{tabular}{lcccccc}\n\\toprule\n"
    "System & MRR $\\uparrow$ & R@5 $\\uparrow$ & R@20 $\\uparrow$ & BCY@8k $\\uparrow$ & any-gold $\\uparrow$ & latency (s) $\\downarrow$ \\\\\n\\midrule"
)
TAIL = "\\bottomrule\n\\end{tabular}"


def ladder_table(track: str) -> str:
    spec = TRACKS[track]
    lines = [LADDER_HEAD]
    best = column_best([spec["delphi"]] + [spec["ladder"].format(eng=eng) for eng, _ in LADDER]
                       + [spec["lexical"][eng] for eng, _ in LEXICAL])
    row = system_row("Delphi (frozen)", spec["delphi"], best=best)
    if row:
        lines.append(row)
    lines.append("\\midrule")
    for eng, label in LADDER:
        row = system_row(label, spec["ladder"].format(eng=eng), best=best)
        lines.append(row or f"{label} & \\multicolumn{{6}}{{l}}{{\\emph{{pending}}}} \\\\")
    lines.append("\\midrule")
    for eng, label in LEXICAL:
        row = system_row(label, spec["lexical"][eng], best=best)
        if row:
            lines.append(row)
    # paired deltas
    lines.append("\\midrule")
    lines.append("\\multicolumn{7}{l}{\\emph{Paired Delphi$-$system deltas, repository-cluster bootstrap 95\\% intervals; $^{*}$ interval excludes zero}} \\\\")
    for eng, label in LADDER:
        path = RESULTS / spec["pair_ladder"].format(eng=eng)
        pair = json.load(path.open()) if path.exists() else None
        if pair is None:
            continue
        ag = pair.get("any_gold_at_20", {})
        agc = f"{ag.get('candidate_cases', '?')} vs {ag.get('baseline_cases', '?')}"
        p = ag.get("mcnemar_exact_p")
        pc = f"$p{{=}}{p:.2g}$" if p is not None else ""
        lines.append(
            f"$\\Delta$ vs.\\ {label.replace(chr(92) + 'quad ', '')} & "
            + " & ".join(delta_cell(pair, k) for k, _ in METRICS)
            + f" & {agc} & {pc} \\\\"
        )
    for eng, label in LEXICAL:
        path = RESULTS / spec["pair_lexical"][eng]
        pair = json.load(path.open()) if path.exists() else None
        if pair is None:
            continue
        ag = pair.get("any_gold_at_20", {})
        agc = f"{ag.get('candidate_cases', '?')} vs {ag.get('baseline_cases', '?')}"
        p = ag.get("mcnemar_exact_p")
        pc = f"$p{{=}}{p:.2g}$" if p is not None else ""
        lines.append(
            f"$\\Delta$ vs.\\ {label} & "
            + " & ".join(delta_cell(pair, k) for k, _ in METRICS)
            + f" & {agc} & {pc} \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def docs_table() -> str:
    a = json.load((RESULTS / "DOCS-dev-answer-synthesis-analysis-v3.json").open())
    arms = a["arms"]
    nia_m = a.get("arms_nia_retrieved_answer_synthesis")

    def reps(v: dict | None) -> str:
        if not v or not v.get("per_repeat_rates"):
            return "---"
        return "/".join(f"{x:.3f}" for x in v["per_repeat_rates"])

    def ci(key: str) -> str:
        v = a.get(key)
        if not v:
            return "---"
        lo, hi = v["case_cluster_bootstrap_95_ci"]
        return f"${v['mean_delta']:+.3f}$ \\ci{{{lo:+.3f}}}{{{hi:+.3f}}}"

    rows = [
        ("Documentation engine retrieval + frozen synthesis", arms["context7_answer_synthesis"]["case_mean_rate"], reps(arms["context7_answer_synthesis"]), ci("context7_vs_control")),
        ("\\textbf{Delphi retrieval + frozen synthesis}", arms["delphi_answer_synthesis"]["case_mean_rate"], reps(arms["delphi_answer_synthesis"]), ci("answer_vs_control")),
        ("Synthesis engine retrieval + frozen synthesis", nia_m["case_mean_rate"] if nia_m else None, reps(nia_m), ci("nia_matched_vs_control")),
        ("Synthesis engine, native synthesis (recorded)", arms["nia_full_recorded"]["case_mean_rate"], "single pass", ci("control_vs_nia").replace("+", "\\mathrm{sign\\,flipped}") if False else "---"),
        ("Model alone (no retrieval)", arms["synthesis_no_retrieval"]["case_mean_rate"], reps(arms["synthesis_no_retrieval"]), "---"),
    ]
    lines = ["\\begin{tabular}{lccc}", "\\toprule", "Arm & Identifier hit & Per-repeat & $\\Delta$ vs.\\ control \\\\", "\\midrule"]
    for label, rate, rep, d in rows:
        lines.append(f"{label} & {fmt(rate)} & {rep} & {d} \\\\")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def docs_pairs_table() -> str:
    a = json.load((RESULTS / "DOCS-dev-answer-synthesis-analysis-v3.json").open())

    def line(label: str, key: str) -> str:
        v = a.get(key)
        if not v:
            return ""
        lo, hi = v["case_cluster_bootstrap_95_ci"]
        return f"{label} & ${v['mean_delta']:+.3f}$ & \\ci{{{lo:+.3f}}}{{{hi:+.3f}}} & {v['wins']}/{v['losses']}/{v['ties']} \\\\"

    rows = [
        line("Delphi $-$ synthesis engine (matched)", "answer_vs_nia_matched"),
        line("Delphi $-$ synthesis engine (native)", "answer_vs_nia"),
        line("Delphi $-$ documentation engine", "answer_vs_context7"),
        line("Documentation engine $-$ synthesis engine (matched)", "context7_vs_nia_matched"),
        line("Synthesis engine matched $-$ native", "nia_matched_vs_nia_native"),
    ]
    lines = ["\\begin{tabular}{lccc}", "\\toprule", "Comparison & $\\Delta$ & $95\\%$ CI & W/L/T \\\\", "\\midrule"]
    lines += [r for r in rows if r]
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def determinism_table() -> str:
    d = json.load((RESULTS / "DETERMINISM-docs-like-for-like-v1.json").open())["engines"]
    labels = {
        "delphi_compact": "Delphi (raw context, $k{=}5$)",
        "context7_guided_compact": "Documentation engine (quality-guided IDs)",
        "context7_oracle_compact": "Documentation engine (oracle IDs)",
        "nia_full_synthesis": "Synthesis engine (cited-URL set)",
    }
    lines = ["\\begin{tabular}{lccccc}", "\\toprule", "Engine & Set exact & Order exact & Set Jaccard & Byte exact & Hit agreement \\\\", "\\midrule"]
    for key, label in labels.items():
        e = d.get(key)
        if not e:
            continue
        lines.append(
            f"{label} & {e['retrieved_set_exact_rate']:.3f} & {e['retrieved_order_exact_rate']:.3f} & "
            f"{e['retrieved_set_jaccard']:.3f} & {e['context_byte_exact_rate']:.3f} & {e['identifier_hit_agreement_rate']:.3f} \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def pooled_table() -> str:
    """Delta-only table for the pooled 160-instance SWE-bench analysis."""
    labels = [
        ("dense", "Dense (same embedding)"),
        ("hybrid", "Dense+BM25 RRF"),
        ("hybrid_rerank", "+ Delphi's rerankers"),
        ("hybrid_rerank_expand", "+ expansion"),
        ("lexical_bm25", "Lexical+BM25 RRF"),
        ("lexical", "Lexical ranker"),
        ("bm25", "BM25"),
    ]
    lines = ["\\begin{tabular}{lccccc}", "\\toprule",
             "Delphi $-$ system & MRR & R@5 & R@20 & BCY@8k & any-gold ($p$) \\\\", "\\midrule"]
    for eng, label in labels:
        path = RESULTS / f"swebench_pooled160_delphi_vs_{eng}_r4_v1.json"
        if not path.exists():
            continue
        pair = json.load(path.open())
        ag = pair["any_gold_at_20"]
        lines.append(
            f"{label} & " + " & ".join(delta_cell(pair, k) for k, _ in METRICS)
            + f" & {ag['candidate_cases']} vs {ag['baseline_cases']} ($p{{=}}{ag['mcnemar_exact_p']:.2g}$) \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def pilot_table(budget: str = "s50") -> str:
    path = RESULTS / "pilot" / f"analysis-{budget}.json"
    if not path.exists():
        return "\\begin{tabular}{l}\\emph{pending}\\end{tabular}"
    a = json.load(path.open())
    repeats = len(str(a.get("budget", "")).split("+"))
    labels = {
        "none": "No seed",
        "random": "Random files (control)",
        "delphi": "Delphi top-5 (frozen)",
        "hybrid_rerank_expand": "Conventional ladder top-5",
    }
    n = a["instances_common"]
    resolved_head = f"Resolved (mean of {repeats} repeats, of {n})" if repeats > 1 else f"Resolved (of {n})"
    lines = ["\\begin{tabular}{lcccc}", "\\toprule",
             f"Condition & {resolved_head} & Rate & Mean cost (USD) & Mean steps \\\\", "\\midrule"]
    for key in ("none", "random", "delphi", "hybrid_rerank_expand"):
        c = a["conditions"].get(key)
        if not c:
            continue
        lines.append(f"{labels[key]} & {c['resolved']:.1f} & {c['resolved_rate']:.3f} & {c['mean_cost_usd']:.4f} & {c['mean_steps']:.1f} \\\\")
    lines.append("\\midrule")
    lines.append("\\multicolumn{5}{l}{\\emph{Paired differences in per-instance resolved rate: instance-cluster 95\\% CI [repository-cluster CI]; instances favouring a/b}} \\\\")
    pair_labels = {
        "delphi_minus_none": "Delphi $-$ no seed",
        "delphi_minus_random": "Delphi $-$ random",
        "delphi_minus_hybrid_rerank_expand": "Delphi $-$ conventional",
        "hybrid_rerank_expand_minus_none": "Conventional $-$ no seed",
        "hybrid_rerank_expand_minus_random": "Conventional $-$ random",
        "random_minus_none": "Random $-$ no seed",
    }
    for key, label in pair_labels.items():
        pr = a["pairs"].get(key)
        if not pr:
            continue
        r = pr["resolved"]
        lo, hi = r["instance_cluster_95_ci"]
        rlo, rhi = r["repository_cluster_95_ci"]
        star = "$^{*}$" if (lo > 0 or hi < 0) else ""
        lines.append(
            f"{label} & \\multicolumn{{4}}{{l}}{{${r['mean_delta']:+.3f}${star} \\ci{{{lo:+.3f}}}{{{hi:+.3f}}} [\\ci{{{rlo:+.3f}}}{{{rhi:+.3f}}}]; "
            f"{r['a_only']}/{r['b_only']}}} \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def _details(run_id: str) -> list[dict]:
    path = RESULTS / f"{run_id}-details.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open() if line.strip()]


def arb_workflow_table() -> str:
    """ARB round-3 partition by workflow: Delphi vs the final conventional rung."""
    sd = summary(TRACKS["arb"]["delphi"])["by_workflow"]
    sc = summary(TRACKS["arb"]["ladder"].format(eng="hybrid_rerank_expand"))["by_workflow"]
    sl = summary(TRACKS["arb"]["lexical"]["lexical"])["by_workflow"]
    lines = ["\\begin{tabular}{lrcccccc}", "\\toprule",
             "Workflow & $n$ & \\multicolumn{2}{c}{Delphi} & \\multicolumn{2}{c}{Conventional (+ expansion)} & \\multicolumn{2}{c}{Lexical ranker} \\\\",
             "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(lr){7-8}",
             " & & MRR & R@20 & MRR & R@20 & MRR & R@20 \\\\", "\\midrule"]
    for wf in ("trace2code", "edit2ripple", "comment2context", "code2test"):
        d, c, l = sd[wf]["metrics"], sc[wf]["metrics"], sl[wf]["metrics"]
        lines.append(
            f"\\texttt{{{wf}}} & {sd[wf]['n']} & {d['MRR']:.3f} & {d['Recall@20']:.3f} & {c['MRR']:.3f} & {c['Recall@20']:.3f} & {l['MRR']:.3f} & {l['Recall@20']:.3f} \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def per_repo_table() -> str:
    """Pooled 160 SWE-bench instances by repository: Delphi, conventional final rung, lexical ranker."""
    systems = {
        "delphi": [TRACKS["swebench"]["delphi"], TRACKS["swebench_expansion"]["delphi"]],
        "conv": [TRACKS["swebench"]["ladder"].format(eng="hybrid_rerank_expand"),
                 TRACKS["swebench_expansion"]["ladder"].format(eng="hybrid_rerank_expand")],
        "lex": [TRACKS["swebench"]["lexical"]["lexical"], TRACKS["swebench_expansion"]["lexical"]["lexical"]],
    }
    rows: dict[str, list[dict]] = {}
    for key, runs in systems.items():
        rows[key] = [r for run in runs for r in _details(run)]
    by_repo: dict[str, dict[str, list[dict]]] = {}
    for key, rs in rows.items():
        for r in rs:
            by_repo.setdefault(r["repo"], {}).setdefault(key, []).append(r)
    lines = ["\\begin{tabular}{lrcccccc}", "\\toprule",
             "Repository & $n$ & \\multicolumn{2}{c}{Delphi} & \\multicolumn{2}{c}{Conventional (+ expansion)} & \\multicolumn{2}{c}{Lexical ranker} \\\\",
             "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(lr){7-8}",
             " & & MRR & R@20 & MRR & R@20 & MRR & R@20 \\\\", "\\midrule"]

    def mean(rs: list[dict], metric: str) -> float:
        return sum(r["metrics"][metric] for r in rs) / max(1, len(rs))

    for repo in sorted(by_repo, key=lambda k: -len(by_repo[k].get("delphi", []))):
        g = by_repo[repo]
        cells = " & ".join(f"{mean(g.get(k, []), 'MRR'):.3f} & {mean(g.get(k, []), 'Recall@20'):.3f}" for k in ("delphi", "conv", "lex"))
        lines.append(f"\\texttt{{{repo}}} & {len(g.get('delphi', []))} & {cells} \\\\")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def latency_table() -> str:
    """Median query latency (seconds) for every system on every set."""
    order = [
        ("BM25", "lexical", "bm25"), ("Lexical ranker", "lexical", "lexical"), ("Lexical+BM25 RRF", "lexical", "lexical_bm25"),
        ("Dense", "ladder", "dense"), ("Dense+BM25 RRF", "ladder", "hybrid"), ("+ Delphi's rerankers", "ladder", "hybrid_rerank"),
        ("+ expansion", "ladder", "hybrid_rerank_expand"), ("Delphi (frozen)", "delphi", None),
    ]
    tracks = [("independent", "Independent"), ("swebench", "SWE-bench r3"), ("swebench_expansion", "SWE-bench exp."), ("arb", "ARB (C2)")]
    lines = ["\\begin{tabular}{l" + "c" * len(tracks) + "}", "\\toprule",
             "System & " + " & ".join(t for _, t in tracks) + " \\\\", "\\midrule"]
    for label, kind, eng in order:
        cells = []
        for track, _ in tracks:
            spec = TRACKS[track]
            run = spec["delphi"] if kind == "delphi" else spec["ladder"].format(eng=eng) if kind == "ladder" else spec["lexical"][eng]
            s = summary(run)
            med = (s or {}).get("latency_ms", {}).get("median")
            cells.append(f"{med / 1000:.2f}" if med else "--")
        lines.append(f"{label} & " + " & ".join(cells) + " \\\\")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def exposure_table() -> str:
    ledger = json.load((RESULTS / "exposure-ledger-v1.json").open())
    names = {
        "arb_round3_final": "ARB round-3 partition (positive workflows)",
        "arb_round3_development": "ARB round-3 development",
        "independent_commit2files_final": "Independent commit-to-files final",
        "independent_commit2files_development": "Independent commit-to-files development",
        "swebench_verified_round3": "SWE-bench Verified, round 3",
        "swebench_verified_round4_expansion": "SWE-bench Verified, round-4 expansion",
        "ds1000_documentation_development": "DS-1000 documentation subset",
    }
    lines = ["\\begin{tabular}{lrlp{5.4cm}}", "\\toprule", "Set & Cases & Class & Supports \\\\", "\\midrule"]
    for s in ledger["sets"]:
        label = names.get(s["set"], s["set"].replace("_", "\\_"))
        n = s["case_ids"] if isinstance(s["case_ids"], int) else len(s["case_ids"])
        lines.append(f"{label} & {n} & {s['exposure_class']} & {s['supports']} \\\\")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def factorial_cells_table() -> str:
    """Candidate generator x reranking head: cell means per set (results/factorial-r4-v1.json)."""
    f = json.load((RESULTS / "factorial-r4-v1.json").open())
    labels = {
        "conv_norerank": ("conventional", "none"),
        "conv_rerank": ("conventional", "Delphi's"),
        "delphi_norerank": ("Delphi", "none"),
        "delphi_rerank": ("Delphi", "Delphi's"),
        "delphi_rerank_confirmatory": ("Delphi, confirmatory index", "Delphi's"),
    }
    lines = ["\\begin{tabular}{llcccc}", "\\toprule",
             "Set / candidates & Rerankers & MRR $\\uparrow$ & R@5 $\\uparrow$ & R@20 $\\uparrow$ & BCY@8k $\\uparrow$ \\\\", "\\midrule"]
    for key in ("independent", "swebench", "expansion", "arb"):
        entry = f["sets"].get(key)
        if not entry:
            continue
        cells = entry["cells"]
        present = [c for c in ("conv_norerank", "conv_rerank", "delphi_norerank", "delphi_rerank", "delphi_rerank_confirmatory") if c in cells]
        if not present:
            continue
        best = {m: max(cells[c][m] for c in present) for m in ("MRR", "Recall@5", "Recall@20", "BCY@8k")}
        lines.append(f"\\multicolumn{{6}}{{l}}{{\\emph{{{entry['label']}}}}} \\\\")
        for c in present:
            cand, rer = labels[c]
            vals = []
            for m in ("MRR", "Recall@5", "Recall@20", "BCY@8k"):
                v = cells[c][m]
                cell = f"{v:.3f}"
                if abs(v - best[m]) < 1e-9:
                    cell = f"\\textbf{{{cell}}}"
                vals.append(cell)
            lines.append(f"\\quad {cand} & {rer} & " + " & ".join(vals) + " \\\\")
        lines.append("\\addlinespace")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def factorial_contrasts_table() -> str:
    f = json.load((RESULTS / "factorial-r4-v1.json").open())
    names = {
        "rerank_effect_conventional": "rerankers, conventional candidates",
        "rerank_effect_delphi": "rerankers, Delphi candidates",
        "candidate_effect_norerank": "Delphi $-$ conventional candidates, no rerankers",
        "candidate_effect_rerank": "Delphi $-$ conventional candidates, with rerankers",
        "candidate_effect_rerank_confirmatory": "Delphi (confirmatory index) $-$ conventional, with rerankers",
        "replication": "Delphi re-indexed $-$ confirmatory index (same configuration)",
    }

    def cell(c: dict, m: str) -> str:
        if m not in c["metrics"]:
            return "---"
        d = c["metrics"][m]["mean_delta"]
        lo, hi = c["metrics"][m]["ci95"]
        star = "$^{*}$" if (lo > 0 or hi < 0) else ""
        return f"${d:+.3f}${star} \\ci{{{lo:+.3f}}}{{{hi:+.3f}}}"

    lines = ["\\begin{tabular}{llccc}", "\\toprule",
             "Set & Contrast & $\\Delta$MRR & $\\Delta$R@20 & $\\Delta$BCY@8k \\\\", "\\midrule"]
    for key in ("independent", "swebench", "expansion", "arb"):
        entry = f["sets"].get(key)
        if not entry or not entry["contrasts"]:
            continue
        first = True
        for name in ("rerank_effect_conventional", "rerank_effect_delphi", "candidate_effect_norerank", "candidate_effect_rerank", "candidate_effect_rerank_confirmatory", "replication"):
            c = entry["contrasts"].get(name)
            if not c:
                continue
            label = entry["label"].split(" (")[0] if first else ""
            first = False
            lines.append(f"{label} & {names[name]} & {cell(c, 'MRR')} & {cell(c, 'Recall@20')} & {cell(c, 'BCY@8k')} \\\\")
        lines.append("\\addlinespace")
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def seed_interface_table() -> str:
    path = RESULTS / "pilot" / "analysis-seed-interface.json"
    if not path.exists():
        return "\\begin{tabular}{l}\\emph{pending}\\end{tabular}"
    a = json.load(path.open())
    labels = {
        "none": "No seed",
        "delphi_paths": "Delphi top-5, paths only",
        "delphi": "Delphi top-5, paths + file heads (pilot design)",
        "delphi_chunks": "Delphi top-5, paths + best-matching chunk",
    }
    n = a["instances_common"]
    lines = ["\\begin{tabular}{lcccc}", "\\toprule", f"Seed interface (one trajectory per instance, {n} instances) & Resolved & Rate & Mean cost (USD) & Mean steps \\\\", "\\midrule"]
    for key in ("none", "delphi_paths", "delphi", "delphi_chunks"):
        c = a["conditions"].get(key)
        if not c:
            continue
        lines.append(f"{labels[key]} & {c['resolved']:.0f} & {c['resolved_rate']:.3f} & {c['mean_cost_usd']:.4f} & {c['mean_steps']:.1f} \\\\")
    lines.append("\\midrule")
    lines.append("\\multicolumn{5}{l}{\\emph{Paired differences in resolved rate: instance-cluster 95\\% CI [repository-cluster CI]; instances favouring a/b}} \\\\")
    pair_labels = {
        "delphi_paths_minus_none": "Paths only $-$ no seed",
        "delphi_minus_none": "Paths + heads $-$ no seed",
        "delphi_chunks_minus_none": "Paths + chunks $-$ no seed",
        "delphi_chunks_minus_delphi": "Paths + chunks $-$ paths + heads",
        "delphi_paths_minus_delphi": "Paths only $-$ paths + heads",
    }
    for key, label in pair_labels.items():
        pr = a["pairs"].get(key)
        if not pr:
            continue
        r = pr["resolved"]
        lo, hi = r["instance_cluster_95_ci"]
        rlo, rhi = r["repository_cluster_95_ci"]
        star = "$^{*}$" if (lo > 0 or hi < 0) else ""
        lines.append(
            f"{label} & \\multicolumn{{4}}{{l}}{{${r['mean_delta']:+.3f}${star} \\ci{{{lo:+.3f}}}{{{hi:+.3f}}} [\\ci{{{rlo:+.3f}}}{{{rhi:+.3f}}}]; {r['a_only']}/{r['b_only']}}} \\\\"
        )
    lines.append(TAIL)
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "factorial_cells.tex").write_text(factorial_cells_table().rstrip("\n") + "%")
    (OUT / "factorial_contrasts.tex").write_text(factorial_contrasts_table().rstrip("\n") + "%")
    (OUT / "seed_interface.tex").write_text(seed_interface_table().rstrip("\n") + "%")
    (OUT / "pilot_s50_r2.tex").write_text(pilot_table("s50-r2").rstrip("\n") + "%")
    (OUT / "arb_workflows.tex").write_text(arb_workflow_table().rstrip("\n") + "%")
    (OUT / "per_repo_swebench.tex").write_text(per_repo_table().rstrip("\n") + "%")
    (OUT / "latency.tex").write_text(latency_table().rstrip("\n") + "%")
    (OUT / "exposure_ledger.tex").write_text(exposure_table().rstrip("\n") + "%")
    # No trailing newline: a blank line after \input inside a tabular is a
    # paragraph break, which LaTeX reports as a misplaced \noalign.
    for track in TRACKS:
        (OUT / f"{track}_ladder.tex").write_text(ladder_table(track).rstrip("\n") + "%")
    (OUT / "docs_matched.tex").write_text(docs_table().rstrip("\n") + "%")
    (OUT / "docs_pairs.tex").write_text(docs_pairs_table().rstrip("\n") + "%")
    (OUT / "determinism_like_for_like.tex").write_text(determinism_table().rstrip("\n") + "%")
    (OUT / "pilot_s50.tex").write_text(pilot_table("s50").rstrip("\n") + "%")
    (OUT / "pilot_pooled.tex").write_text(pilot_table("s50_s50-r2").rstrip("\n") + "%")
    (OUT / "swebench_pooled.tex").write_text(pooled_table().rstrip("\n") + "%")
    for path in sorted(OUT.glob("*.tex")):
        print(path.name, path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
