"""Case-level exposure ledger for every evaluation set in the archive.

Reviewers asked what information from earlier rounds was available while the
frozen system was being developed, and which cases can therefore support a
confirmatory claim. This script writes the answer down per case rather than
per split, so the paper's labels can be checked mechanically.

Exposure classes:

  C0  never scored by any system before its single confirmatory run, and
      drawn from a pool no development decision could see
  C1  development: scored repeatedly during round 3 and used to guide changes
  C2  re-partitioned from a pool whose cases were all scored in round 2
      (July 2026); round-2 held-out aggregates gated which retrieval
      components shipped, and round-2 per-workflow aggregates motivated one
      round-3 product fix; per-case round-2 outputs are not retained here,
      so per-case tuning cannot be ruled in or out from the archive alone

The ledger is derived only from the sample manifests and the recorded
journals; it does not compute any metric.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SETS = [
    {
        "set": "arb_round3_final",
        "files": [f"samples/final/{w}.jsonl" for w in ("v2_trace2code", "v2_code2test", "v2_comment2context", "v2_edit2ripple")],
        "positive_only": True,
        "exposure_class": "C2",
        "evidence": [
            "protocol.md: 'All 427 ARB v2 cases were scored by the July 2026 round-2 process, and round-2 final results influenced which Delphi configuration shipped.'",
            "round2-provenance/NEGATIVE-RESULTS.md: 'Every candidate change here was confirmed on the held-out split before shipping, and four did not survive it'; query expansion, listwise reranking, the cross-encoder blend, RRF, and path-affinity were selected on round-2 held-out numbers.",
            "paper (round-3 draft), quoted-path demotion: motivated by July per-workflow any-gold@20 (92% trace2code vs 48% comment2context), computed over all 427 cases.",
            "Round 3 queried these 220 cases once, from frozen code, after freeze (results/A-final-delphi-generated-source-exact-top20-v1-*).",
        ],
        "supports": "development/validation evidence; not a confirmatory test of the frozen stack",
    },
    {
        "set": "arb_round3_development",
        "files": [f"samples/development/{w}.jsonl" for w in ("v2_trace2code", "v2_code2test", "v2_comment2context", "v2_edit2ripple")],
        "positive_only": True,
        "exposure_class": "C1",
        "evidence": ["Used for every round-3 candidate decision (exact scan, expansion ablation, File-Okapi gate, disabled controls)."],
        "supports": "development",
    },
    {
        "set": "independent_commit2files_final",
        "files": ["corpus/independent/v1/final.jsonl"],
        "positive_only": False,
        "exposure_class": "C0",
        "evidence": [
            "Corpus built in round 3 from repositories disjoint from ARB (harness/build_independent_corpus.py); final split locked before any scoring (corpus/independent/v1/LOCK.json).",
            "Scored once by the frozen stack (results/I-final-delphi-generated-source-exact-top20-v1-*) and by comparators.",
            "Caveat shared by every set: the foundation models inside the stack (embeddings, gpt-4o, gpt-4o-mini) may have seen these public repositories during training; the ledger controls author exposure, not model contamination.",
            "Post-hoc explanatory use (2026-09-09): the corpus was re-indexed into a fresh database for the candidate x reranker factorial (I-factorial-delphi-full-v1 replication, I-ablation-delphi-norerank-v1, I-final-hybrid_expand-r4-v1). Confirmatory numbers remain those of the original index.",
        ],
        "supports": "confirmatory",
    },
    {
        "set": "independent_commit2files_development",
        "files": ["corpus/independent/v1/development.jsonl"],
        "positive_only": False,
        "exposure_class": "C1",
        "evidence": ["Used for File-Okapi gates, disabled-branch controls, and the generated-source gold-path preflight."],
        "supports": "development",
    },
    {
        "set": "swebench_verified_round3",
        "files": ["samples/swebench/cases.jsonl"],
        "positive_only": False,
        "exposure_class": "C0",
        "evidence": [
            "Drawn deterministically (harness/prep_swebench.py, salt delphi-round3-swebench-v1); leakage audit 0/62 patch markers; scored once from frozen code (results/D-final-delphi-generated-source-exact-top20-v1-*).",
            "Same model-contamination caveat as every set.",
            "Post-hoc explanatory use (2026-09-09): D-final-hybrid_expand-r4-v1 factorial cell; executable-pilot seed-interface check (delphi_paths-s50, delphi_chunks-s50) on the same 62 instances, one trajectory each, not preregistered.",
        ],
        "supports": "confirmatory",
    },
    {
        "set": "swebench_verified_round4_expansion",
        "files": ["samples/swebench/cases-r4-expansion-v3.jsonl"],
        "positive_only": False,
        "exposure_class": "C0",
        "evidence": [
            "Drawn 2026-09-09 (harness/prep_swebench_expansion.py, salt delphi-round4-swebench-expansion-v1) from the 438 Verified instances never used in any round; excludes round-3 instance ids and base commits (100 drawn).",
            "Two engine-agnostic preprocessing rules applied before any scoring (samples/swebench/cases-r4-expansion-manifest.json): a gold file must exist at the base commit (one file created by the patch removed from astropy__astropy-13398's gold set; no case dropped), and ARB's query_has_leakage excludes instances whose issue text carries patch or fix-commit markers (django__django-16256, scikit-learn__scikit-learn-14710). 98 cases remain.",
            "Scored once per system on 2026-09-09 from the frozen commit after the index audit (results/native-delphi-swebench-r4-expansion-index-audit-v2.json) and gold-searchability preflight; no system was re-run.",
            "Post-hoc explanatory use (2026-09-09, after the confirmatory runs): candidate x reranker factorial cells D2-ablation-delphi-norerank-v1 and D2-final-hybrid_expand-r4-v1 (results/factorial-r4-v1.json). No configuration was chosen on them; the set becomes C1 for any future change they inform.",
        ],
        "supports": "confirmatory",
    },
    {
        "set": "swebench_verified_round4_fresh_branch_ablation",
        "files": ["samples/swebench/cases-r5-fresh.jsonl"],
        "positive_only": False,
        "exposure_class": "C0",
        "evidence": [
            "Drawn 2026-09-09 (harness/prep_swebench_expansion.py, salt delphi-round4-swebench-fresh-branch-ablation-v1, n=60) from the 338 Verified instances never used in any round; excludes every round-3 and round-4 instance id and base commit (samples/swebench/cases-r5-fresh-manifest.json).",
            "The two engine-agnostic preprocessing rules (gold file must exist at the base commit; ARB query_has_leakage) were applied before any scoring; 0 files affected, 0 cases excluded.",
            "Purpose fixed before scoring: branch-level ablation of the frozen build's candidate generator (rerankers off) plus one confirmatory pass of the frozen configuration and the matched ladder; every configuration scored once.",
        ],
        "supports": "confirmatory (third SWE-bench draw); branch ablation",
    },
    {
        "set": "ds1000_documentation_development",
        "files": ["samples-ds1000/development.jsonl"],
        "positive_only": False,
        "id_field": "metadata.problem_id",
        "exposure_class": "C1",
        "evidence": ["40-case development subset used for all documentation-track and synthesis-arm comparisons; no documentation final exists."],
        "supports": "development",
    },
]


def read_ids(path: Path, *, positive_only: bool, id_field: str = "id") -> list[str]:
    ids: list[str] = []
    for line in path.open():
        if not line.strip():
            continue
        row = json.loads(line)
        if positive_only and (row.get("gold") or {}).get("no_gold") is True:
            continue
        value = row
        for part in id_field.split("."):
            value = (value or {}).get(part)
        ids.append(str(value))
    return ids


def main() -> None:
    ledger = {"schema": "exposure_ledger_v1", "generated_from": "sample manifests + context journals", "sets": []}
    lines = [
        "# Exposure ledger",
        "",
        "Generated by `harness/build_exposure_ledger.py` from the sample manifests and the",
        "recorded journals. Classes: C0 never scored before a single confirmatory run;",
        "C1 development; C2 re-partitioned from a pool scored in round 2 whose aggregate",
        "results gated shipped components.",
        "",
        "| Set | Cases | Class | Supports |",
        "|---|---:|---|---|",
    ]
    for spec in SETS:
        ids: list[str] = []
        for rel in spec["files"]:
            path = ROOT / rel
            if path.exists():
                ids.extend(read_ids(path, positive_only=spec["positive_only"], id_field=spec.get("id_field", "id")))
        entry = {
            "set": spec["set"],
            "files": spec["files"],
            "cases": len(ids),
            "exposure_class": spec["exposure_class"],
            "supports": spec["supports"],
            "evidence": spec["evidence"],
            "case_ids": ids,
        }
        ledger["sets"].append(entry)
        lines.append(f"| `{spec['set']}` | {len(ids)} | {spec['exposure_class']} | {spec['supports']} |")
    lines += ["", "## Evidence per set", ""]
    for entry in ledger["sets"]:
        lines.append(f"### `{entry['set']}` ({entry['cases']} cases, {entry['exposure_class']})")
        lines.append("")
        for item in entry["evidence"]:
            lines.append(f"- {item}")
        lines.append("")
    lines += [
        "## Which decisions saw which cases",
        "",
        "| Decision | Informed by |",
        "|---|---|",
        "| Query-time embedding alignment, RRF fusion, path-affinity branch, cross-encoder blend (k=30, alpha 0.4), hypothetical-document expansion, listwise reranking | Round-2 development (75) and round-2 held-out (220) over the ARB v2 pool that round 3 re-partitioned |",
        "| Quoted-path demotion | July per-workflow any-gold@20 over all 427 ARB v2 cases |",
        "| Exact vector scan, single-flight, persistent stage cache, total SQL ordering | Round-3 ARB development (75) and 8-query determinism probes |",
        "| Agent-mode generated-source indexing | Gold-path preflight over independent development (48) and ARB development (75) |",
        "| File-Okapi rejection | Independent development (48) and ARB development (75) |",
        "",
        "Round-2 per-case outputs are not retained in this archive; the round-2 journals",
        "record aggregate development/held-out numbers only.",
    ]
    (ROOT / "results" / "exposure-ledger-v1.json").write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    (ROOT / "context" / "EXPOSURE_LEDGER.md").write_text("\n".join(lines) + "\n")
    for entry in ledger["sets"]:
        print(f"{entry['set']:40s} {entry['cases']:4d} {entry['exposure_class']}")


if __name__ == "__main__":
    main()
