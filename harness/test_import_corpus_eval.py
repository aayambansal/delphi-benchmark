from __future__ import annotations

import json
import sqlite3

from harness import runstore


def test_import_corpus_results_populates_dashboard_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runstore, "DB_PATH", tmp_path / "runstore.db")

    from harness.import_corpus_eval import import_corpus_results

    rows = [{
        "sample_id": "case-1",
        "task_type": "code2test",
        "repo": "owner/repo",
        "base_commit": "abc123",
        "gold_files": ["tests/test_core.py"],
        "top_files": ["src/core.py", "tests/test_core.py"],
        "status": "ok",
        "error": None,
        "latency_ms": 12.5,
        "metrics": {"MRR": 0.5, "Recall@5": 1.0, "Recall@20": 1.0, "BCY@8k": 0.25},
    }]
    summary = {"n": 1, "sample_weighted": {"MRR": 0.5}}

    import_corpus_results(
        rows=rows,
        summary=summary,
        engine="lexical",
        split="development",
        run_id="A-dev-lexical",
        system="arb-lexical",
        notes="local canonical-git run",
    )

    conn = sqlite3.connect(runstore.DB_PATH)
    run = conn.execute(
        "SELECT status, n_cases, metrics FROM runs WHERE run_id='A-dev-lexical'"
    ).fetchone()
    case = conn.execute(
        "SELECT ok, ranked, gold, trace FROM cases "
        "WHERE run_id='A-dev-lexical' AND case_id='case-1'"
    ).fetchone()

    assert run[:2] == ("done", 1)
    assert json.loads(run[2]) == summary
    assert case[0] == 1
    assert json.loads(case[1]) == ["src/core.py", "tests/test_core.py"]
    assert json.loads(case[2]) == ["tests/test_core.py"]
    assert json.loads(case[3]) == {"error": None, "imported": True}
