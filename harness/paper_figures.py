"""Generate every figure in the paper from recorded artifacts.

    MPLBACKEND=agg python harness/paper_figures.py

Writes PDF figures to paper/figures/. Nothing is hand-entered: every value is
read from results/*-summary.json, results/*-details.jsonl, the paired-analysis
JSON files, and the pilot analyses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "agg")
import matplotlib  # noqa: E402

matplotlib.use("agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIG = ROOT / "paper" / "figures"

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "pdf.fonttype": 42,
    }
)

DELPHI = "#8c2d19"
LADDER = ["#9ecae1", "#6baed6", "#3182bd", "#08519c"]
LEXICAL = ["#bdbdbd", "#969696", "#636363"]
CONTROL = "#7f7f7f"

SYSTEMS = [
    ("bm25", "BM25", LEXICAL[0]),
    ("lexical", "Lexical ranker", LEXICAL[1]),
    ("lexical_bm25", "Lexical+BM25 RRF", LEXICAL[2]),
    ("dense", "Dense", LADDER[0]),
    ("hybrid", "Dense+BM25 RRF", LADDER[1]),
    ("hybrid_rerank", "+ Delphi's rerankers", LADDER[2]),
    ("hybrid_rerank_expand", "+ expansion", LADDER[3]),
    ("delphi", "Delphi (frozen)", DELPHI),
]

TRACKS = {
    "independent": {
        "title": "Independent (C0, n=18)",
        "runs": {
            "delphi": "I-final-delphi-generated-source-exact-top20-v1",
            "dense": "I-final-dense-r4-v1", "hybrid": "I-final-hybrid-r4-v1",
            "hybrid_rerank": "I-final-hybrid_rerank-r4-v1", "hybrid_rerank_expand": "I-final-hybrid_rerank_expand-r4-v1",
            "bm25": "I-final-bm25-generated-policy-v1", "lexical": "I-final-lexical-generated-policy-v1",
            "lexical_bm25": "I-final-lexical_bm25-generated-policy-v1",
        },
        "pairs": {
            "dense": "independent_final_delphi_vs_dense_r4_v1.json", "hybrid": "independent_final_delphi_vs_hybrid_r4_v1.json",
            "hybrid_rerank": "independent_final_delphi_vs_hybrid_rerank_r4_v1.json",
            "hybrid_rerank_expand": "independent_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
            "bm25": "independent_final_delphi_vs_bm25_v1.json", "lexical": "independent_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "independent_final_delphi_vs_lexical_bm25_v1.json",
        },
    },
    "swebench": {
        "title": "SWE-bench r3 (C0, n=62)",
        "runs": {
            "delphi": "D-final-delphi-generated-source-exact-top20-v1",
            "dense": "D-final-dense-r4-v1", "hybrid": "D-final-hybrid-r4-v1",
            "hybrid_rerank": "D-final-hybrid_rerank-r4-v1", "hybrid_rerank_expand": "D-final-hybrid_rerank_expand-r4-v1",
            "bm25": "D-final-bm25-generated-policy-v1", "lexical": "D-final-lexical-generated-policy-v1",
            "lexical_bm25": "D-final-lexical_bm25-generated-policy-v1",
        },
        "pairs": {
            "dense": "trackd_final_delphi_vs_dense_r4_v1.json", "hybrid": "trackd_final_delphi_vs_hybrid_r4_v1.json",
            "hybrid_rerank": "trackd_final_delphi_vs_hybrid_rerank_r4_v1.json",
            "hybrid_rerank_expand": "trackd_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
            "bm25": "trackd_final_delphi_vs_bm25_v1.json", "lexical": "trackd_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "trackd_final_delphi_vs_lexicalbm25_v1.json",
        },
    },
    "expansion": {
        "title": "SWE-bench expansion (C0, n=98)",
        "runs": {
            "delphi": "D2-final-delphi-generated-source-exact-top20-v1",
            "dense": "D2-final-dense-r4-v1", "hybrid": "D2-final-hybrid-r4-v1",
            "hybrid_rerank": "D2-final-hybrid_rerank-r4-v1", "hybrid_rerank_expand": "D2-final-hybrid_rerank_expand-r4-v1",
            "bm25": "D2-final-bm25-r4-v1", "lexical": "D2-final-lexical-r4-v1", "lexical_bm25": "D2-final-lexical_bm25-r4-v1",
        },
        "pairs": {k: f"swebench_expansion_delphi_vs_{k}_r4_v1.json" for k in
                  ("dense", "hybrid", "hybrid_rerank", "hybrid_rerank_expand", "bm25", "lexical", "lexical_bm25")},
    },
    "arb": {
        "title": "ARB round-3 (C2, n=220)",
        "runs": {
            "delphi": "A-final-delphi-generated-source-exact-top20-v1",
            "dense": "A-final-dense-r4-v1", "hybrid": "A-final-hybrid-r4-v1",
            "hybrid_rerank": "A-final-hybrid_rerank-r4-v1", "hybrid_rerank_expand": "A-final-hybrid_rerank_expand-r4-v1",
            "bm25": "A-final-bm25-generated-policy-v1", "lexical": "A-final-lexical-generated-policy-v1",
            "lexical_bm25": "A-final-lexical-bm25-generated-policy-v1",
        },
        "pairs": {
            "dense": "arb_final_delphi_vs_dense_r4_v1.json", "hybrid": "arb_final_delphi_vs_hybrid_r4_v1.json",
            "hybrid_rerank": "arb_final_delphi_vs_hybrid_rerank_r4_v1.json",
            "hybrid_rerank_expand": "arb_final_delphi_vs_hybrid_rerank_expand_r4_v1.json",
            "bm25": "arb_final_delphi_vs_bm25_v1.json", "lexical": "arb_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "arb_final_delphi_vs_lexical-bm25_v1.json",
        },
    },
}
POOLED_PAIRS = {k: f"swebench_pooled160_delphi_vs_{k}_r4_v1.json" for k in
                ("dense", "hybrid", "hybrid_rerank", "hybrid_rerank_expand", "bm25", "lexical", "lexical_bm25")}
METRICS = [("MRR", "MRR"), ("Recall@5", "Recall@5"), ("Recall@20", "Recall@20"), ("BCY@8k", "BCY@8k")]


def summary(run: str) -> dict | None:
    p = RESULTS / f"{run}-summary.json"
    return json.load(p.open()) if p.exists() else None


def details(run: str) -> list[dict]:
    p = RESULTS / f"{run}-details.jsonl"
    return [json.loads(l) for l in p.open() if l.strip()] if p.exists() else []


def pair(name: str) -> dict | None:
    p = RESULTS / name
    return json.load(p.open()) if p.exists() else None


def save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", FIG / name)


# --------------------------------------------------------------------- 1
def fig_ladder_c0() -> None:
    tracks = ["independent", "swebench", "expansion"]
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.6), sharey=True)
    for ax, key in zip(axes, tracks):
        spec = TRACKS[key]
        labels, mrr, r20, colors = [], [], [], []
        for sys_key, label, color in SYSTEMS:
            s = summary(spec["runs"][sys_key])
            if s is None:
                continue
            labels.append(label)
            mrr.append(s["sample_weighted"]["MRR"])
            r20.append(s["sample_weighted"]["Recall@20"])
            colors.append(color)
        y = np.arange(len(labels))
        ax.barh(y + 0.19, mrr, height=0.36, color=colors, edgecolor="none", label="MRR")
        ax.barh(y - 0.19, r20, height=0.36, color=colors, alpha=0.45, edgecolor="none", label="Recall@20")
        for yi, v in zip(y, mrr):
            ax.text(v + 0.01, yi + 0.19, f"{v:.2f}", va="center", fontsize=6.5)
        ax.set_yticks(y)
        ax.set_yticklabels(labels)
        ax.set_xlim(0, 1.0)
        ax.set_title(spec["title"], loc="left")
        ax.grid(axis="x", color="#eeeeee", linewidth=0.5)
        ax.set_axisbelow(True)
    axes[0].legend(loc="lower right", frameon=False)
    axes[1].set_xlabel("score (dark bar: MRR; light bar: Recall@20)")
    save(fig, "ladder_c0.pdf")


# --------------------------------------------------------------------- 2
def fig_deltas_forest(metrics: list[tuple[str, str]] = METRICS, name: str = "deltas_forest.pdf", height: float = 6.2) -> None:
    panels = [
        ("Independent (C0, n=18)", TRACKS["independent"]["pairs"]),
        ("SWE-bench pooled (C0, n=160)", POOLED_PAIRS),
        ("ARB round-3 (C2, n=220)", TRACKS["arb"]["pairs"]),
    ]
    order = ["bm25", "lexical", "lexical_bm25", "dense", "hybrid", "hybrid_rerank", "hybrid_rerank_expand"]
    labels = {k: l for k, l, _ in SYSTEMS}
    colors = {k: c for k, _, c in SYSTEMS}
    fig, axes = plt.subplots(len(metrics), len(panels), figsize=(7.0, height), sharex="col", sharey=True)
    for j, (title, pairs) in enumerate(panels):
        for i, (metric, mlabel) in enumerate(metrics):
            ax = axes[i, j]
            for k_i, key in enumerate(order):
                pr = pair(pairs.get(key, "")) if pairs.get(key) else None
                if pr is None or metric not in pr["metrics"]:
                    continue
                m = pr["metrics"][metric]
                lo, hi = m["repo_cluster_bootstrap_95_ci"]
                d = m["mean_delta"]
                y = len(order) - 1 - k_i
                resolved = lo > 0 or hi < 0
                ax.plot([lo, hi], [y, y], color=colors[key], linewidth=1.4 if resolved else 1.0, alpha=1.0 if resolved else 0.7)
                ax.plot([d], [y], marker="o" if resolved else "o", markersize=3.6 if resolved else 3.0,
                        markerfacecolor=colors[key] if resolved else "white", markeredgecolor=colors[key], linestyle="none")
            ax.axvline(0, color="#444444", linewidth=0.6)
            ax.set_yticks(range(len(order)))
            ax.set_yticklabels([labels[k] for k in reversed(order)])
            ax.grid(axis="x", color="#eeeeee", linewidth=0.5)
            ax.set_axisbelow(True)
            if i == 0:
                ax.set_title(title, loc="left")
            if j == 0:
                ax.set_ylabel(mlabel)
            if i == len(metrics) - 1:
                ax.set_xlabel("Delphi $-$ system (paired)")
            if j == 2:
                ax.set_facecolor("#f7f7f7")
    fig.tight_layout(h_pad=0.4, w_pad=0.6)
    save(fig, name)


# --------------------------------------------------------------------- 11
def fig_exposure_timeline() -> None:
    """Schematic of the evaluation rounds, the sets each round scored, and their exposure class."""
    fig, ax = plt.subplots(figsize=(7.0, 3.3))
    ax.set_xlim(0, 3.85)
    ax.set_ylim(-0.02, 1)
    ax.axis("off")
    cls_color = {"C0": "#2ca25f", "C1": "#969696", "C2": "#e6550d", "": "#bdbdbd"}
    rounds = [
        ("Round 2 (July 2026)", [
            ("ARB v2 development, 75 cases", "C1"),
            ("ARB v2 held-out, 220 cases", "C1"),
            ("all 427 ARB v2 cases scored;\nheld-out aggregates gated RRF,\npath affinity, cross-encoder,\nexpansion, listwise rerank", ""),
        ]),
        ("Round 3 (Aug 23-26, 2026)", [
            ("ARB re-partition 25/75 of the\nsame pool, 220 cases", "C2"),
            ("ARB development, 75 cases", "C1"),
            ("Independent commit-to-files\nfinal, 18 cases (corpus locked)", "C0"),
            ("SWE-bench Verified, 62 cases", "C0"),
            ("DS-1000 documentation, 40 cases", "C1"),
            ("Delphi build frozen", ""),
        ]),
        ("Round 4 (Sep 9, 2026)", [
            ("SWE-bench Verified expansion,\n98 cases (fresh salt)", "C0"),
            ("matched ladder on every set", ""),
            ("matched synthesis-engine arm", ""),
            ("like-for-like determinism", ""),
            ("executable pilot,\n62 cases x 4 conditions x 2", ""),
        ]),
    ]
    W = 1.0
    xs = [0.05, 1.45, 2.85]
    centers: dict[str, tuple[float, float, float]] = {}
    for x, (title, items) in zip(xs, rounds):
        ax.text(x, 0.985, title, fontsize=8.5, fontweight="bold", va="top")
        y = 0.90
        for label, cls in items:
            n_lines = label.count("\n") + 1
            h = 0.062 * n_lines + 0.03
            color = cls_color[cls]
            ax.add_patch(plt.Rectangle((x, y - h), W, h, facecolor="white" if cls else "#f2f2f2",
                                       edgecolor=color, linewidth=1.2 if cls else 0.6, linestyle="-" if cls != "C2" else "--"))
            ax.text(x + 0.035, y - h / 2, label, fontsize=6.4, va="center", linespacing=1.15)
            if cls:
                ax.text(x + W - 0.03, y - h / 2, cls, fontsize=7, va="center", ha="right", color=color, fontweight="bold")
            centers[label] = (x, x + W, y - h / 2)
            y -= h + 0.03
    l0, r0, y0 = centers["ARB v2 held-out, 220 cases"]
    l1, r1, y1 = centers["ARB re-partition 25/75 of the\nsame pool, 220 cases"]
    ax.annotate("", xy=(l1, y1), xytext=(r0, y0), arrowprops=dict(arrowstyle="->", color="#e6550d", linewidth=1.0, linestyle="--"))
    ax.text((r0 + l1) / 2, (y0 + y1) / 2 + 0.05, "same pool,\nre-drawn", fontsize=5.8, color="#e6550d", ha="center", va="bottom", linespacing=1.1)
    l2, r2, y2 = centers["SWE-bench Verified, 62 cases"]
    l3, r3, y3 = centers["executable pilot,\n62 cases x 4 conditions x 2"]
    ax.annotate("", xy=(l3, y3), xytext=(r2, y2), arrowprops=dict(arrowstyle="->", color="#2ca25f", linewidth=1.0))
    ax.text((r2 + l3) / 2, min(y2, y3) - 0.04, "same 62\ninstances", fontsize=5.8, color="#2ca25f", ha="center", va="top", linespacing=1.1)
    from matplotlib.patches import Patch

    handles = [Patch(facecolor="white", edgecolor=cls_color["C0"], linewidth=1.2, label="C0: scored once, never seen by development"),
               Patch(facecolor="white", edgecolor=cls_color["C1"], linewidth=1.2, label="C1: development"),
               Patch(facecolor="white", edgecolor=cls_color["C2"], linewidth=1.2, linestyle="--", label="C2: re-partitioned from a scored pool")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, -0.06), ncol=3, frameon=False, fontsize=6.5)
    save(fig, "exposure_timeline.pdf")


# --------------------------------------------------------------------- 12
def fig_factorial() -> None:
    """Candidate generator x reranking head interaction plot (sets with the Delphi no-reranker cell)."""
    f = json.load((RESULTS / "factorial-r4-v1.json").open())
    sets = [k for k in ("independent", "swebench", "expansion", "arb") if "delphi_norerank" in f["sets"].get(k, {}).get("cells", {})]
    if not sets:
        return
    metrics = [("MRR", "MRR"), ("Recall@20", "Recall@20"), ("BCY@8k", "BCY@8k")]
    fig, axes = plt.subplots(len(sets), len(metrics), figsize=(7.0, 2.1 * len(sets)), squeeze=False)
    for i, key in enumerate(sets):
        cells = f["sets"][key]["cells"]
        for j, (metric, label) in enumerate(metrics):
            ax = axes[i, j]
            for cand, color, marker, name in (("conv", LADDER[3], "s", "conventional candidates"), ("delphi", DELPHI, "o", "Delphi candidates")):
                ys = [cells[f"{cand}_norerank"][metric], cells[f"{cand}_rerank"][metric]]
                ax.plot([0, 1], ys, marker=marker, markersize=4.5, color=color, linewidth=1.3, label=name)
                for x, y in zip((0, 1), ys):
                    ax.text(x + (-0.06 if x == 0 else 0.06), y, f"{y:.3f}", fontsize=6.3, color=color, ha="right" if x == 0 else "left", va="center")
            ax.set_xticks([0, 1])
            ax.set_xticklabels(["no learned\nreranking", "+ Delphi's\nrerankers"])
            ax.set_xlim(-0.35, 1.35)
            ax.set_ylim(0, 1)
            ax.set_ylabel(label)
            ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
            ax.set_axisbelow(True)
            if j == 0:
                ax.set_title(f["sets"][key]["label"], loc="left")
    axes[0, 0].legend(frameon=False, loc="lower right", fontsize=6.5)
    fig.tight_layout(w_pad=1.0, h_pad=0.8)
    save(fig, "factorial.pdf")


# --------------------------------------------------------------------- 3
def fig_component_attribution() -> None:
    steps = ["dense", "hybrid", "hybrid_rerank", "hybrid_rerank_expand", "delphi"]
    step_labels = ["Dense", "+ BM25\n(RRF)", "+ Delphi's\nrerankers", "+ Delphi's\nexpansion", "Delphi\n(frozen)"]
    styles = {
        "independent": ("Independent (C0, n=18)", "#e6550d", "o"),
        "swebench": ("SWE-bench r3 (C0, n=62)", "#3182bd", "s"),
        "expansion": ("SWE-bench expansion (C0, n=98)", "#08519c", "D"),
        "arb": ("ARB round-3 (C2, n=220)", "#969696", "^"),
    }
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.2))
    for ax, metric in zip(axes, ["MRR", "Recall@20"]):
        for key, (label, color, marker) in styles.items():
            ys = []
            for step in steps:
                s = summary(TRACKS[key]["runs"][step])
                ys.append(s["sample_weighted"][metric] if s else np.nan)
            ax.plot(range(len(steps)), ys, marker=marker, markersize=4, color=color, linewidth=1.2,
                    linestyle="--" if key == "arb" else "-", label=label)
        ax.set_xticks(range(len(steps)))
        ax.set_xticklabels(step_labels)
        ax.set_ylabel(metric)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
        ax.set_axisbelow(True)
        ax.axvspan(3.5, 4.5, color=DELPHI, alpha=0.06, linewidth=0)
    axes[0].legend(frameon=False, loc="upper left")
    save(fig, "component_attribution.pdf")


# --------------------------------------------------------------------- 4
def fig_docs_matched() -> None:
    a = json.load((RESULTS / "DOCS-dev-answer-synthesis-analysis-v3.json").open())
    arms = a["arms"]
    nia_m = a["arms_nia_retrieved_answer_synthesis"]
    rows = [
        ("Documentation engine\nretrieval + frozen synthesis", arms["context7_answer_synthesis"], "#636363"),
        ("Delphi retrieval\n+ frozen synthesis", arms["delphi_answer_synthesis"], DELPHI),
        ("Synthesis engine retrieval\n+ frozen synthesis", nia_m, "#636363"),
        ("Synthesis engine,\nnative pass (recorded)", arms["nia_full_recorded"], "#bdbdbd"),
        ("Model alone\n(no retrieval)", arms["synthesis_no_retrieval"], CONTROL),
    ]
    raw = []
    for label, run in [("Delphi k=5", "DOCS-dev-delphi-compact"), ("Delphi k=20", "DOCS-dev-delphi-compact-k20"),
                       ("Synthesis engine\n(reconstructed k=5)", "DOCS-dev-nia-retrieved-k5"),
                       ("Documentation engine\n(quality-guided)", "DOCS-dev-context7-guided-compact")]:
        p = RESULTS / f"{run}-summary.json"
        if p.exists():
            raw.append((label, json.load(p.open()).get("identifier_hit_rate")))
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.3), gridspec_kw={"width_ratios": [1.4, 1]})
    ax = axes[0]
    y = np.arange(len(rows))
    for yi, (label, arm, color) in zip(y, rows):
        ax.barh(yi, arm["case_mean_rate"], color=color, height=0.6, edgecolor="none")
        reps = arm.get("per_repeat_rates") or []
        ax.plot(reps, [yi] * len(reps), linestyle="none", marker="|", color="black", markersize=7, markeredgewidth=0.9)
        ax.text(max([arm["case_mean_rate"], *reps]) + 0.015, yi, f"{arm['case_mean_rate']:.3f}", va="center", fontsize=6.5)
    ax.axvline(arms["synthesis_no_retrieval"]["case_mean_rate"], color=CONTROL, linewidth=0.6, linestyle=":")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.8)
    ax.set_xlabel("identifier hit on synthesized answer (40 cases; ticks: repeats)")
    ax.set_title("Matched output contract", loc="left")
    ax = axes[1]
    y = np.arange(len(raw))
    ax.barh(y, [r[1] for r in raw], color=[DELPHI, DELPHI, "#636363", "#636363"][: len(raw)], height=0.6, edgecolor="none")
    for yi, (_, v) in zip(y, raw):
        ax.text(v + 0.01, yi, f"{v:.3f}", va="center", fontsize=6.5)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in raw])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.8)
    ax.set_xlabel("identifier hit on raw retrieved context")
    ax.set_title("Raw retrieval", loc="left")
    fig.tight_layout(w_pad=1.5)
    save(fig, "docs_matched.pdf")


# --------------------------------------------------------------------- 5
def fig_determinism() -> None:
    d = json.load((RESULTS / "DETERMINISM-docs-like-for-like-v1.json").open())["engines"]
    engines = [
        ("delphi_compact", "Delphi\n(raw context)", DELPHI),
        ("nia_full_synthesis", "Synthesis engine\n(cited-URL set)", "#636363"),
        ("context7_guided_compact", "Documentation engine\n(quality-guided)", "#969696"),
        ("context7_oracle_compact", "Documentation engine\n(oracle IDs)", "#bdbdbd"),
    ]
    measures = [
        ("retrieved_set_exact_rate", "retrieved set exact"),
        ("retrieved_order_exact_rate", "retrieved order exact"),
        ("context_byte_exact_rate", "context byte-exact"),
        ("identifier_hit_agreement_rate", "identifier-hit agreement"),
    ]
    fig, ax = plt.subplots(figsize=(7.0, 2.3))
    width = 0.19
    x = np.arange(len(measures))
    for i, (key, label, color) in enumerate(engines):
        vals = [d[key][m] for m, _ in measures]
        ax.bar(x + (i - 1.5) * width, vals, width=width, color=color, edgecolor="none", label=label)
        for xi, v in zip(x + (i - 1.5) * width, vals):
            ax.text(xi, v + 0.015, f"{v:.2f}", ha="center", fontsize=5.8, rotation=90 if v < 0.15 else 0)
    ax.set_xticks(x)
    ax.set_xticklabels([m for _, m in measures])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("rate over 450 run pairs")
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.22))
    ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
    ax.set_axisbelow(True)
    save(fig, "determinism.pdf")


# --------------------------------------------------------------------- 6
def fig_pilot() -> None:
    conds = [("none", "No\nseed", CONTROL), ("random", "Random\nfiles", "#969696"),
             ("delphi", "Delphi\ntop-5", DELPHI), ("hybrid_rerank_expand", "Conventional\ntop-5", LADDER[3])]
    reps = {}
    for lab in ("s50", "s50-r2"):
        p = RESULTS / "pilot" / f"analysis-{lab}.json"
        if p.exists():
            reps[lab] = json.load(p.open())
    pooled = json.load((RESULTS / "pilot" / "analysis-s50_s50-r2.json").open())
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.3), gridspec_kw={"width_ratios": [1, 1.3]})
    ax = axes[0]
    x = np.arange(len(conds))
    for i, (lab, marker) in enumerate(zip(reps, ["o", "s"])):
        vals = [reps[lab]["conditions"][c]["resolved"] for c, _, _ in conds]
        ax.plot(x, vals, linestyle="none", marker=marker, color="#333333", markersize=5, label=f"repeat {i + 1}")
    means = [pooled["conditions"][c]["resolved"] for c, _, _ in conds]
    ax.bar(x, means, width=0.55, color=[c for _, _, c in conds], alpha=0.35, edgecolor="none", label="mean of repeats")
    tops = [max(reps[lab]["conditions"][c]["resolved"] for lab in reps) for c, _, _ in conds]
    for xi, m, t in zip(x, means, tops):
        ax.text(xi, t + 1.2, f"{m:.1f}", ha="center", fontsize=6.5)
    ax.set_xticks(x)
    ax.set_xticklabels([l for _, l, _ in conds], rotation=0)
    ax.set_ylabel("verified repairs (of 62)")
    ax.set_ylim(0, 44)
    ax.legend(frameon=False, loc="upper center", fontsize=6.2, ncol=3, bbox_to_anchor=(0.5, 1.0), handletextpad=0.3, columnspacing=0.8)
    ax.set_title("Resolved instances per condition", loc="left", pad=14)
    ax = axes[1]
    pairs = [("delphi_minus_none", "Delphi $-$ no seed"), ("random_minus_none", "Random $-$ no seed"),
             ("delphi_minus_random", "Delphi $-$ random"), ("hybrid_rerank_expand_minus_none", "Conventional $-$ no seed"),
             ("hybrid_rerank_expand_minus_random", "Conventional $-$ random"), ("delphi_minus_hybrid_rerank_expand", "Delphi $-$ conventional")]
    for i, (key, label) in enumerate(pairs):
        r = pooled["pairs"][key]["resolved"]
        lo, hi = r["instance_cluster_95_ci"]
        y = len(pairs) - 1 - i
        resolved = lo > 0 or hi < 0
        ax.plot([lo, hi], [y, y], color="#333333", linewidth=1.3 if resolved else 0.9)
        ax.plot([r["mean_delta"]], [y], marker="o", markersize=4, markerfacecolor="#333333" if resolved else "white",
                markeredgecolor="#333333", linestyle="none")
        rlo, rhi = r["repository_cluster_95_ci"]
        ax.plot([rlo, rhi], [y - 0.22, y - 0.22], color="#999999", linewidth=0.8)
    ax.axvline(0, color="#444444", linewidth=0.6)
    ax.set_yticks(range(len(pairs)))
    ax.set_yticklabels([l for _, l in reversed(pairs)])
    ax.set_xlabel("difference in per-instance repair rate (pooled repeats)")
    ax.set_title("Paired differences; dark: instance-cluster CI, grey: repository-cluster CI", loc="left", fontsize=7.5)
    ax.grid(axis="x", color="#eeeeee", linewidth=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout(w_pad=1.2)
    save(fig, "pilot.pdf")


# --------------------------------------------------------------------- 7
def fig_arb_workflows() -> None:
    sd = summary(TRACKS["arb"]["runs"]["delphi"])["by_workflow"]
    sc = summary(TRACKS["arb"]["runs"]["hybrid_rerank_expand"])["by_workflow"]
    wfs = ["trace2code", "edit2ripple", "comment2context", "code2test"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.2), sharey=True)
    for ax, metric in zip(axes, ["MRR", "Recall@20"]):
        x = np.arange(len(wfs))
        ax.bar(x - 0.18, [sd[w]["metrics"][metric] for w in wfs], width=0.36, color=DELPHI, label="Delphi (frozen)")
        ax.bar(x + 0.18, [sc[w]["metrics"][metric] for w in wfs], width=0.36, color=LADDER[3], label="Conventional (+ expansion)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{w}\n(n={sd[w]['n']})" for w in wfs])
        ax.set_title(metric, loc="left")
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False, loc="upper right")
    save(fig, "arb_workflows.pdf")


# --------------------------------------------------------------------- 8
def fig_latency_quality() -> None:
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    markers = {"independent": "o", "swebench": "s", "expansion": "D", "arb": "^"}
    for key, marker in markers.items():
        spec = TRACKS[key]
        for sys_key, label, color in SYSTEMS:
            s = summary(spec["runs"][sys_key])
            if not s or not s.get("latency_ms", {}).get("median"):
                continue
            ax.plot(s["latency_ms"]["median"] / 1000, s["sample_weighted"]["MRR"], marker=marker, markersize=4.5,
                    color=color, linestyle="none", alpha=0.9 if key != "arb" else 0.45,
                    markeredgecolor="black" if sys_key == "delphi" else color, markeredgewidth=0.5)
    ax.set_xscale("log")
    ax.set_xlabel("median query latency (s, log scale)")
    ax.set_ylabel("MRR")
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], marker=m, color="#555555", linestyle="none", markersize=4.5, label=TRACKS[k]["title"].split(" (")[0])
               for k, m in markers.items()]
    handles += [Line2D([], [], marker="o", color=c, linestyle="none", markersize=4.5, label=l) for _, l, c in SYSTEMS]
    ax.legend(handles=handles, frameon=False, fontsize=5.5, loc="upper left", bbox_to_anchor=(1.0, 1.02))
    ax.grid(color="#eeeeee", linewidth=0.5)
    ax.set_axisbelow(True)
    save(fig, "latency_quality.pdf")


# --------------------------------------------------------------------- 9
def fig_per_repo_swebench() -> None:
    dd = details(TRACKS["swebench"]["runs"]["delphi"]) + details(TRACKS["expansion"]["runs"]["delphi"])
    dc = details(TRACKS["swebench"]["runs"]["hybrid_rerank_expand"]) + details(TRACKS["expansion"]["runs"]["hybrid_rerank_expand"])
    by_repo: dict[str, list[tuple[float, float]]] = {}
    cmap = {r["sample_id"]: r for r in dc}
    for r in dd:
        c = cmap.get(r["sample_id"])
        if c is None:
            continue
        by_repo.setdefault(r["repo"], []).append((r["metrics"]["MRR"], c["metrics"]["MRR"]))
    repos = sorted(by_repo, key=lambda k: -len(by_repo[k]))
    fig, ax = plt.subplots(figsize=(7.0, 2.3))
    x = np.arange(len(repos))
    d_means = [np.mean([a for a, _ in by_repo[r]]) for r in repos]
    c_means = [np.mean([b for _, b in by_repo[r]]) for r in repos]
    ax.bar(x - 0.18, d_means, width=0.36, color=DELPHI, label="Delphi (frozen)")
    ax.bar(x + 0.18, c_means, width=0.36, color=LADDER[3], label="Conventional (+ expansion)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r.split('/')[-1]}\n(n={len(by_repo[r])})" for r in repos], fontsize=6.5)
    ax.set_ylabel("MRR")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_title("SWE-bench Verified, 160 pooled C0 instances, by repository", loc="left")
    save(fig, "per_repo_swebench.pdf")


# --------------------------------------------------------------------- 10
def fig_rank_histogram() -> None:
    def first_gold_rank(row: dict) -> int | None:
        gold = set(row.get("gold_files") or [])
        for i, p in enumerate(row.get("top_files") or [], start=1):
            if p in gold:
                return i
        return None

    bins = [("1", lambda r: r == 1), ("2–5", lambda r: r is not None and 2 <= r <= 5),
            ("6–20", lambda r: r is not None and 6 <= r <= 20), ("miss", lambda r: r is None)]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.2))
    for ax, (title, keys) in zip(axes, [("SWE-bench pooled (C0, n=160)", ["swebench", "expansion"]), ("Independent (C0, n=18)", ["independent"])]):
        series = []
        for sys_key, label, color in [("delphi", "Delphi (frozen)", DELPHI), ("hybrid_rerank_expand", "Conventional (+ expansion)", LADDER[3]),
                                      ("lexical", "Lexical ranker", LEXICAL[1])]:
            rows = [r for k in keys for r in details(TRACKS[k]["runs"][sys_key])]
            ranks = [first_gold_rank(r) for r in rows]
            counts = [sum(1 for r in ranks if f(r)) / max(1, len(ranks)) for _, f in bins]
            series.append((label, color, counts))
        x = np.arange(len(bins))
        for i, (label, color, counts) in enumerate(series):
            ax.bar(x + (i - 1) * 0.26, counts, width=0.26, color=color, label=label, edgecolor="none")
        ax.set_xticks(x)
        ax.set_xticklabels([b for b, _ in bins])
        ax.set_xlabel("rank of first gold file")
        ax.set_ylabel("fraction of cases")
        ax.set_ylim(0, 0.8)
        ax.set_title(title, loc="left")
        ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False)
    save(fig, "rank_histogram.pdf")


def main() -> None:
    fig_ladder_c0()
    fig_deltas_forest()
    fig_deltas_forest([("MRR", "MRR"), ("Recall@20", "Recall@20")], "deltas_forest_compact.pdf", 3.3)
    fig_exposure_timeline()
    fig_factorial()
    fig_component_attribution()
    fig_docs_matched()
    fig_determinism()
    fig_pilot()
    fig_arb_workflows()
    fig_latency_quality()
    fig_per_repo_swebench()
    fig_rank_histogram()


if __name__ == "__main__":
    main()
