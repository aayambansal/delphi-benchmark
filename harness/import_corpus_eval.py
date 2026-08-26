"""Import snapshot-parallel corpus results into the local run dashboard."""
from __future__ import annotations

from typing import Any

from harness.runstore import RunWriter


def import_corpus_results(
    *,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    engine: str,
    split: str,
    run_id: str,
    system: str,
    notes: str,
) -> str:
    writer = RunWriter(
        track="A-static-retrieval",
        system=system,
        config={"engine": engine, "split": split, "imported": True},
        split=split,
        run_id=run_id,
        notes=notes,
    )
    for row in rows:
        writer.case(
            case_id=str(row["sample_id"]),
            workflow=str(row.get("task_type") or "unknown"),
            repo=str(row.get("repo") or ""),
            revision=str(row.get("base_commit") or ""),
            ok=row.get("status") == "ok",
            latency_ms=row.get("latency_ms"),
            metrics=row.get("metrics") or {},
            ranked=row.get("top_files") or [],
            gold=row.get("gold_files") or [],
            trace={"error": row.get("error"), "imported": True},
        )
    writer.finish(summary)
    return writer.run_id
