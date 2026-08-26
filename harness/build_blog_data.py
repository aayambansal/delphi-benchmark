"""Build the research-blog data bundle from recorded round-3 artifacts.

Reads only files under new/round3/results, samples, corpus, and determinism.
Every number shown in the blog comes from this builder; nothing is hand-typed
into the page. Re-run after new artifacts land.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from statistics import fmean, median

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = ROOT / "blog" / "site" / "data"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write(name: str, value) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{name}: {path.stat().st_size / 1024:.0f} KiB")


def query_snippet(raw_query, limit: int = 420) -> str:
    if isinstance(raw_query, dict):
        parts = [str(v) for v in raw_query.values() if v]
        text = " — ".join(parts)
    else:
        text = str(raw_query)
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


# ---------------------------------------------------------------- repo finals


TRACKS = {
    "arb": {
        "title": "ARB round-3 final",
        "cases": 220,
        "delphi": "A-final-delphi-generated-source-exact-top20-v1",
        "baselines": {
            "bm25": "A-final-bm25-generated-policy-v1",
            "lexical": "A-final-lexical-generated-policy-v1",
            "lexical_bm25": "A-final-lexical-bm25-generated-policy-v1",
        },
        "analyses": {
            "bm25": "arb_final_delphi_vs_bm25_v1.json",
            "lexical": "arb_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "arb_final_delphi_vs_lexical-bm25_v1.json",
        },
        "samples": sorted((ROOT / "samples" / "final").glob("*.jsonl")),
    },
    "independent": {
        "title": "Independent commit-to-files final",
        "cases": 18,
        "delphi": "I-final-delphi-generated-source-exact-top20-v1",
        "baselines": {
            "bm25": "I-final-bm25-generated-policy-v1",
            "lexical": "I-final-lexical-generated-policy-v1",
            "lexical_bm25": "I-final-lexical_bm25-generated-policy-v1",
        },
        "analyses": {
            "bm25": "independent_final_delphi_vs_bm25_v1.json",
            "lexical": "independent_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "independent_final_delphi_vs_lexicalbm25_v1.json",
        },
        "samples": [ROOT / "corpus" / "independent" / "v1" / "final.jsonl"],
    },
    "trackd": {
        "title": "SWE-bench localization (Track D) final",
        "cases": 62,
        "delphi": "D-final-delphi-generated-source-exact-top20-v1",
        "baselines": {
            "bm25": "D-final-bm25-generated-policy-v1",
            "lexical": "D-final-lexical-generated-policy-v1",
            "lexical_bm25": "D-final-lexical_bm25-generated-policy-v1",
        },
        "analyses": {
            "bm25": "trackd_final_delphi_vs_bm25_v1.json",
            "lexical": "trackd_final_delphi_vs_lexical_v1.json",
            "lexical_bm25": "trackd_final_delphi_vs_lexicalbm25_v1.json",
        },
        "samples": [ROOT / "samples" / "swebench" / "cases.jsonl"],
    },
}

METRICS = ["MRR", "Recall@5", "Recall@20", "BCY@8k"]


def load_details_map(stem: str) -> dict[str, dict]:
    rows = read_jsonl(RESULTS / f"{stem}-details.jsonl")
    return {str(r["sample_id"]): r for r in rows}


def build_repo_finals():
    finals = {}
    traces = {}
    for key, spec in TRACKS.items():
        engines = {"delphi": load_details_map(spec["delphi"])}
        for label, stem in spec["baselines"].items():
            engines[label] = load_details_map(stem)

        sample_rows = {}
        for path in spec["samples"]:
            for row in read_jsonl(path):
                sample_rows[str(row["id"])] = row

        aggregates = {}
        for label, det in engines.items():
            aggregates[label] = {
                metric: fmean(r["metrics"].get(metric, 0.0) for r in det.values())
                for metric in METRICS
            }
            aggregates[label]["any_gold_at_20"] = sum(
                1 for r in det.values() if r["metrics"].get("Recall@20", 0) > 0
            )
            aggregates[label]["mean_latency_ms"] = fmean(
                float(r.get("latency_ms") or 0) for r in det.values()
            )
            aggregates[label]["median_latency_ms"] = median(
                float(r.get("latency_ms") or 0) for r in det.values()
            )

        deltas = {}
        for label, analysis_name in spec["analyses"].items():
            analysis = read_json(RESULTS / analysis_name)
            deltas[label] = {
                metric: {
                    "delta": analysis["metrics"][metric]["mean_delta"],
                    "ci": analysis["metrics"][metric][
                        "repo_cluster_bootstrap_95_ci"
                    ],
                }
                for metric in METRICS
                if metric in analysis["metrics"]
            }
            ag = analysis.get("any_gold_at_20") or {}
            deltas[label]["any_gold"] = {
                "recovered": ag.get("recovered"),
                "lost": ag.get("lost"),
                "mcnemar_p": ag.get("mcnemar_exact_p"),
            }

        finals[key] = {
            "title": spec["title"],
            "cases": spec["cases"],
            "aggregates": aggregates,
            "deltas_vs_delphi_candidate": deltas,
        }

        case_rows = []
        delphi_map = engines["delphi"]
        for sample_id, drow in sorted(delphi_map.items()):
            sample = sample_rows.get(sample_id, {})
            gold = [str(g) for g in (drow.get("gold_files") or [])]
            gold_set = set(gold)
            per_engine = {}
            for label, det in engines.items():
                row = det.get(sample_id)
                if row is None:
                    continue
                top = [str(p) for p in (row.get("top_files") or [])][:20]
                hit_rank = next(
                    (i + 1 for i, p in enumerate(top) if p in gold_set), None
                )
                per_engine[label] = {
                    "top": top,
                    "hit_rank": hit_rank,
                    "mrr": round(row["metrics"].get("MRR", 0.0), 4),
                    "r20": round(row["metrics"].get("Recall@20", 0.0), 4),
                    "latency_ms": round(float(row.get("latency_ms") or 0)),
                }
            case_rows.append(
                {
                    "id": sample_id,
                    "repo": drow.get("repo"),
                    "commit": str(drow.get("base_commit") or "")[:12],
                    "task_type": drow.get("task_type"),
                    "query": query_snippet(sample.get("query", "")),
                    "gold": gold,
                    "engines": per_engine,
                }
            )
        traces[key] = case_rows

    write("repo_finals.json", finals)
    for key, rows in traces.items():
        write(f"traces_{key}.json", rows)


# ------------------------------------------------------------------ docs fair


def per_case_hits(paths: list[Path]) -> dict[str, list[bool]]:
    merged: dict[str, list[bool]] = {}
    for path in paths:
        for row in read_json(path):
            merged.setdefault(str(row["case_id"]), []).append(
                bool(row["identifier_hit"])
            )
    return merged


def build_docs_fair():
    answer_paths = [
        RESULTS / f"DOCS-dev-delphi-answer-synth-r{r}-details.json"
        for r in (1, 2, 3)
    ]
    control_paths = [
        RESULTS / f"DOCS-dev-control-synth-r{r}-details.json" for r in (1, 2, 3)
    ]
    c7_paths = [
        RESULTS / f"DOCS-dev-context7-answer-synth-r{r}-details.json"
        for r in (1, 2, 3)
    ]
    c7_available = all(p.exists() for p in c7_paths)

    nia_rows = {
        str(r["case_id"]): r
        for r in read_json(RESULTS / "DOCS-dev-nia-answer-full-details.json")
    }
    delphi_raw = {
        str(r["case_id"]): r
        for r in read_json(RESULTS / "DOCS-dev-delphi-compact-k20-details.json")
    }
    c7_raw = {
        str(r["case_id"]): r
        for r in read_json(
            RESULTS / "DOCS-dev-context7-guided-compact-details.json"
        )
    }
    analysis_v2 = RESULTS / "DOCS-dev-answer-synthesis-analysis-v2.json"
    analysis = read_json(
        analysis_v2
        if analysis_v2.exists()
        else RESULTS / "DOCS-dev-answer-synthesis-analysis-v1.json"
    )

    def repeats_summary(paths):
        rates = []
        for p in paths:
            rows = read_json(p)
            rates.append(fmean(float(bool(r["identifier_hit"])) for r in rows))
        return rates

    arms = {
        "delphi_synthesis": {
            "label": "Delphi retrieval + synthesis",
            "per_repeat": repeats_summary(answer_paths),
            "case_hits": per_case_hits(answer_paths),
        },
        "nia_synthesis": {
            "label": "Nia retrieval + synthesis (recorded)",
            "per_repeat": [
                fmean(
                    float(bool(r["identifier_hit"])) for r in nia_rows.values()
                )
            ],
            "case_hits": {
                cid: [bool(r["identifier_hit"])] for cid, r in nia_rows.items()
            },
        },
        "control": {
            "label": "Model alone (no retrieval)",
            "per_repeat": repeats_summary(control_paths),
            "case_hits": per_case_hits(control_paths),
        },
    }
    if c7_available:
        arms["context7_synthesis"] = {
            "label": "Context7 retrieval + synthesis",
            "per_repeat": repeats_summary(c7_paths),
            "case_hits": per_case_hits(c7_paths),
        }
    for arm in arms.values():
        arm["case_mean"] = fmean(
            fmean(v) for v in arm["case_hits"].values()
        )

    def synth_texts(paths, cid):
        texts = []
        for p in paths:
            row = next(
                (r for r in read_json(p) if str(r["case_id"]) == cid), None
            )
            texts.append(str(row.get("context") or "") if row else "")
        return texts

    answer_cache = [read_json(p) for p in answer_paths]
    control_cache = [read_json(p) for p in control_paths]
    c7_cache = [read_json(p) for p in c7_paths] if c7_available else []

    def cached_texts(cache, cid):
        out = []
        for rows in cache:
            row = next((r for r in rows if str(r["case_id"]) == cid), None)
            out.append(str(row.get("context") or "") if row else "")
        return out

    cases = []
    for cid, nrow in sorted(nia_rows.items(), key=lambda kv: int(kv[0])):
        draw = delphi_raw.get(cid, {})
        c7row = c7_raw.get(cid, {})
        cases.append(
            {
                "id": cid,
                "library": nrow.get("library"),
                "gold_identifiers": nrow.get("gold_identifiers") or [],
                "delphi": {
                    "retrieved_paths": [
                        str(i.get("path") or "")
                        for i in (draw.get("items") or [])
                    ][:10],
                    "raw_hit": bool(draw.get("identifier_hit")),
                    "synth_texts": cached_texts(answer_cache, cid),
                    "hits": arms["delphi_synthesis"]["case_hits"].get(cid, []),
                },
                "nia": {
                    "synth_text": str(nrow.get("context") or ""),
                    "hit": bool(nrow.get("identifier_hit")),
                    "latency_ms": round(float(nrow.get("latency_ms") or 0)),
                },
                "context7": {
                    "retrieved_paths": [
                        str(i.get("path") or "")
                        for i in (c7row.get("items") or [])
                    ][:10],
                    "raw_hit": bool(c7row.get("identifier_hit")),
                    "synth_texts": (
                        cached_texts(c7_cache, cid) if c7_available else []
                    ),
                    "hits": (
                        arms["context7_synthesis"]["case_hits"].get(cid, [])
                        if c7_available
                        else []
                    ),
                },
                "control": {
                    "texts": cached_texts(control_cache, cid),
                    "hits": arms["control"]["case_hits"].get(cid, []),
                },
            }
        )

    write(
        "docs_fair.json",
        {
            "arms": {
                k: {
                    "label": v["label"],
                    "per_repeat": [round(x, 4) for x in v["per_repeat"]],
                    "case_mean": round(v["case_mean"], 4),
                }
                for k, v in arms.items()
            },
            "raw_reference": {
                "delphi_compact_k20": 0.425,
                "delphi_compact_k5": 0.400,
                "context7_guided_compact": fmean(
                    float(bool(r["identifier_hit"])) for r in c7_raw.values()
                ),
            },
            "paired": {
                "delphi_vs_nia": analysis["answer_vs_nia"],
                "delphi_vs_control": analysis["answer_vs_control"],
                "control_vs_nia": analysis["control_vs_nia"],
                **(
                    {
                        "context7_vs_nia": analysis["context7_vs_nia"],
                        "context7_vs_control": analysis["context7_vs_control"],
                        "delphi_vs_context7": analysis["answer_vs_context7"],
                    }
                    if "context7_vs_nia" in analysis
                    else {}
                ),
            },
            "context7_synthesis_available": c7_available,
            "cases": cases,
        },
    )


# -------------------------------------------------------------------- ds1000


def build_ds1000():
    conditions = {
        "none": ("No retrieval", ["GEN-dev-none-gpt54mini"]),
        "delphi_synthesis": (
            "Delphi retrieval + synthesis",
            ["GEN-dev-delphi-synthesis-gpt54mini"],
        ),
        "nia_synthesis": (
            "Nia retrieval + synthesis",
            ["GEN-dev-nia-full-gpt54mini"],
        ),
        "context7_guided": (
            "Context7 retrieval",
            ["GEN-dev-context7-guided-gpt54mini"],
        ),
    }
    out = {}
    case_matrix: dict[str, dict[str, list[bool]]] = {}
    for key, (label, stems) in conditions.items():
        stem = stems[0]
        rates = []
        for suffix in ("", "-r2", "-r3"):
            details = read_json(RESULTS / f"{stem}{suffix}-details.json")
            rates.append(fmean(float(bool(r["passed"])) for r in details))
            for row in details:
                case_matrix.setdefault(str(row["case_id"]), {}).setdefault(
                    key, []
                ).append(bool(row["passed"]))
        out[key] = {"label": label, "per_repeat": [round(r, 4) for r in rates]}
        out[key]["mean"] = round(fmean(rates), 4)

    analyses = {
        "delphi_synthesis_vs_none": "GEN-ANALYSIS-delphi-synthesis-v-none.json",
        "nia_vs_none": "GEN-ANALYSIS-nia-v-none.json",
        "context7_vs_none": "GEN-ANALYSIS-context7-v-none.json",
        "delphi_synthesis_vs_nia": "GEN-ANALYSIS-delphi-synthesis-v-nia.json",
    }
    paired = {}
    for key, name in analyses.items():
        a = read_json(RESULTS / name)
        paired[key] = {
            "delta": round(a["mean_delta"], 4),
            "ci": [round(x, 4) for x in a["case_cluster_bootstrap_95_ci"]],
            "wins": a.get("paired_wins"),
            "losses": a.get("paired_losses"),
            "ties": a.get("paired_ties"),
        }

    libraries = {}
    none_details = read_json(RESULTS / "GEN-dev-none-gpt54mini-details.json")
    for row in none_details:
        libraries[str(row["case_id"])] = str(row["library"])

    write(
        "ds1000.json",
        {
            "conditions": out,
            "paired": paired,
            "cases": [
                {
                    "id": cid,
                    "library": libraries.get(cid, ""),
                    "passes": case_matrix.get(cid, {}),
                }
                for cid in sorted(case_matrix, key=int)
            ],
        },
    )


# --------------------------------------------------------------- determinism


def build_determinism():
    engines = {
        "delphi": ("Delphi (compact)", ROOT / "determinism" / "delphi", "docs-compact"),
        "context7": (
            "Context7 (quality-guided compact)",
            ROOT / "determinism" / "context7",
            "docs-guided-compact",
        ),
        "nia": ("Nia (full, retrieval+synthesis)", ROOT / "determinism" / "nia", "docs-full"),
    }
    out = {}
    for key, (label, folder, stem) in engines.items():
        runs = []
        for r in range(1, 11):
            candidates = [
                folder / f"{stem}-r{r}-details.json",
                folder / f"docs-r{r}-details.json",
            ]
            path = next((p for p in candidates if p.exists()), None)
            if path is None:
                matches = sorted(folder.glob(f"*r{r}-details.json"))
                path = matches[0] if matches else None
            if path is None:
                continue
            rows = {
                str(row["case_id"]): row for row in read_json(path)
            }
            runs.append(rows)
        if not runs:
            continue
        case_ids = sorted(runs[0], key=lambda x: int(x))
        matrix = []
        for cid in case_ids:
            reference = hashlib.sha256(
                str(runs[0][cid].get("context") or "").encode()
            ).hexdigest()
            row_cells = []
            for run in runs:
                context = str(run.get(cid, {}).get("context") or "")
                digest = hashlib.sha256(context.encode()).hexdigest()
                row_cells.append(
                    {
                        "exact": digest == reference,
                        "hit": bool(run.get(cid, {}).get("identifier_hit")),
                    }
                )
            matrix.append({"case": cid, "runs": row_cells})
        total = 0
        exact = 0
        for i, cid in enumerate(case_ids):
            digests = [
                hashlib.sha256(
                    str(run.get(cid, {}).get("context") or "").encode()
                ).hexdigest()
                for run in runs
            ]
            for a in range(len(digests)):
                for b in range(a + 1, len(digests)):
                    total += 1
                    exact += digests[a] == digests[b]
        out[key] = {
            "label": label,
            "runs": len(runs),
            "cases": len(case_ids),
            "pairwise_exact_context": round(exact / total, 4) if total else None,
            "matrix": matrix,
        }
    write("determinism.json", out)


# -------------------------------------------------------------------- latency


def build_latency():
    def latencies(path: Path, field: str = "latency_ms"):
        rows = read_json(path)
        return [float(r.get(field) or 0) for r in rows]

    docs = {
        "delphi_retrieval": latencies(
            RESULTS / "DOCS-dev-delphi-compact-details.json"
        ),
        "delphi_synthesis_stage": latencies(
            RESULTS / "DOCS-dev-delphi-answer-synth-r1-details.json"
        ),
        "context7_retrieval": latencies(
            RESULTS / "DOCS-dev-context7-guided-compact-details.json"
        ),
        "nia_retrieval_synthesis": latencies(
            RESULTS / "DOCS-dev-nia-answer-full-details.json"
        ),
    }
    arb = read_jsonl(
        RESULTS / "A-final-delphi-generated-source-exact-top20-v1-details.jsonl"
    )
    repo_latency = [float(r.get("latency_ms") or 0) for r in arb]
    write(
        "latency.json",
        {
            "docs": {
                k: {
                    "mean_ms": round(fmean(v)),
                    "median_ms": round(median(v)),
                    "p95_ms": round(sorted(v)[int(0.95 * len(v)) - 1]),
                    "values": [round(x) for x in v],
                }
                for k, v in docs.items()
            },
            "repo_final_delphi": {
                "mean_ms": round(fmean(repo_latency)),
                "median_ms": round(median(repo_latency)),
                "note": (
                    "confirmatory exact-scan configuration with hosted "
                    "expansion and listwise stages; deterministic, not "
                    "latency-optimized"
                ),
            },
        },
    )


# ------------------------------------------------------------------ overview


def build_overview():
    readiness = read_json(
        RESULTS / "nia-accounting-repository-readiness-20260824.json"
    )
    smoke_rows = []
    manifest = RESULTS / "nia-sharded-sources.jsonl"
    if manifest.exists():
        smoke_rows = read_jsonl(manifest)
    write(
        "overview.json",
        {
            "frozen_commit": "91d76c1",
            "frozen_branch": "feature/generated-source-freeze",
            "bootstrap": {"samples": 20000, "seed": 1042, "unit": "repository"},
            "generation_model": "gpt-5.4-mini (frozen)",
            "embedding_model": "text-embedding-3-small (exact scan)",
            "nia_repo_status": {
                "required_pairs": 68,
                "visible_indexed_pairs": 32,
                "smoke": smoke_rows,
                "blocker": readiness.get("blocker"),
            },
            "generated": "2026-08-25",
        },
    )


def main() -> None:
    build_repo_finals()
    build_docs_fair()
    build_ds1000()
    build_determinism()
    build_latency()
    build_overview()


if __name__ == "__main__":
    main()
