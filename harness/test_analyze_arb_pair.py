from __future__ import annotations

from harness.analyze_arb_pair import analyze_pair


def test_analyze_pair_reports_paired_recoveries_and_losses() -> None:
    baseline = [
        {
            "case_id": "a",
            "workflow": "one",
            "repo": "repo-a",
            "metrics": {"MRR": 0.0, "Recall@20": 0.0},
        },
        {
            "case_id": "b",
            "workflow": "two",
            "repo": "repo-b",
            "metrics": {"MRR": 1.0, "Recall@20": 1.0},
        },
    ]
    candidate = [
        {
            "case_id": "a",
            "workflow": "one",
            "repo": "repo-a",
            "metrics": {"MRR": 0.5, "Recall@20": 1.0},
        },
        {
            "case_id": "b",
            "workflow": "two",
            "repo": "repo-b",
            "metrics": {"MRR": 0.0, "Recall@20": 0.0},
        },
    ]

    result = analyze_pair(
        baseline,
        candidate,
        metrics=("MRR", "Recall@20"),
        bootstrap_samples=100,
        seed=7,
    )

    assert result["cases"] == 2
    assert result["metrics"]["MRR"]["baseline_mean"] == 0.5
    assert result["metrics"]["MRR"]["candidate_mean"] == 0.25
    assert result["metrics"]["MRR"]["mean_delta"] == -0.25
    assert result["metrics"]["MRR"]["wins"] == 1
    assert result["metrics"]["MRR"]["losses"] == 1
    assert "repo_cluster_bootstrap_95_ci" in result["metrics"]["MRR"]
    assert result["any_gold_at_20"]["recovered"] == 1
    assert result["any_gold_at_20"]["lost"] == 1
    assert result["any_gold_at_20"]["mcnemar_exact_p"] == 1.0
    assert result["by_workflow"]["one"]["MRR"]["mean_delta"] == 0.5


def test_analyze_pair_accepts_a_named_binary_outcome() -> None:
    baseline = [
        {
            "case_id": "a",
            "workflow": "one",
            "repo": "repo-a",
            "metrics": {"file_f1": 0.0, "final_any_gold": 0.0},
        },
    ]
    candidate = [
        {
            "case_id": "a",
            "workflow": "one",
            "repo": "repo-a",
            "metrics": {"file_f1": 0.5, "final_any_gold": 1.0},
        },
    ]

    result = analyze_pair(
        baseline,
        candidate,
        metrics=("file_f1",),
        binary_metric="final_any_gold",
        binary_label="final_any_gold",
        bootstrap_samples=10,
    )

    assert result["final_any_gold"]["recovered"] == 1
    assert "any_gold_at_20" not in result
