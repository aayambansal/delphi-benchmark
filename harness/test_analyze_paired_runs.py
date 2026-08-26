from __future__ import annotations

import importlib


def test_paired_analysis_counts_fractional_and_binary_changes() -> None:
    try:
        analysis_module = importlib.import_module("harness.analyze_paired_runs")
    except ModuleNotFoundError:
        analysis_module = None
    analyze = getattr(
        analysis_module,
        "analyze_pair",
        lambda *_args, **_kwargs: {},
    )
    baseline = [
        {
            "sample_id": "one",
            "repo": "owner/one",
            "task_type": "code2test",
            "top_files": ["a.py"],
            "metrics": {
                "MRR": 0.0,
                "Recall@5": 0.0,
                "Recall@20": 0.0,
                "BCY@8k": 0.0,
            },
        },
        {
            "sample_id": "two",
            "repo": "owner/two",
            "task_type": "code2test",
            "top_files": ["b.py"],
            "metrics": {
                "MRR": 0.5,
                "Recall@5": 0.5,
                "Recall@20": 0.5,
                "BCY@8k": 0.5,
            },
        },
    ]
    candidate = [
        {
            "sample_id": "one",
            "repo": "owner/one",
            "task_type": "code2test",
            "top_files": ["a.py"],
            "metrics": {
                "MRR": 1.0,
                "Recall@5": 1.0,
                "Recall@20": 1.0,
                "BCY@8k": 1.0,
            },
        },
        {
            "sample_id": "two",
            "repo": "owner/two",
            "task_type": "code2test",
            "top_files": ["c.py"],
            "metrics": {
                "MRR": 0.0,
                "Recall@5": 0.0,
                "Recall@20": 0.0,
                "BCY@8k": 0.0,
            },
        },
    ]

    result = analyze(
        baseline,
        candidate,
        baseline_run="baseline",
        candidate_run="candidate",
        bootstrap_samples=100,
        bootstrap_seed=7,
    )

    assert result["cases"] == 2
    assert result["repositories"] == 2
    assert result["metrics"]["MRR"]["mean_delta"] == 0.25
    assert result["metrics"]["MRR"]["wins"] == 1
    assert result["metrics"]["MRR"]["losses"] == 1
    assert result["any_gold_at_20"] == {
        "metric": "Recall@20",
        "baseline_cases": 1,
        "candidate_cases": 1,
        "both": 0,
        "neither": 0,
        "recovered": 1,
        "lost": 1,
        "recovered_case_ids": ["one"],
        "lost_case_ids": ["two"],
        "mcnemar_exact_p": 1.0,
    }
    assert result["ranking_agreement"] == {
        "exact_top20_rate": 0.5,
        "mean_top20_set_jaccard": 0.5,
    }
