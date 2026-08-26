from __future__ import annotations

import gzip
import importlib.util
import json
import multiprocessing
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _execution_module(runtime_source: str) -> Any:
    # The official evaluator defines its worker as a nested function and
    # therefore requires fork semantics. Linux uses fork by default; macOS
    # defaults to spawn, which cannot pickle that worker.
    multiprocessing.set_start_method("fork", force=True)
    spec = importlib.util.spec_from_file_location(
        "official_ds1000_execution",
        runtime_source,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load DS-1000 runtime: {runtime_source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _dataset(dataset_path: str) -> tuple[dict[str, Any], ...]:
    with gzip.open(dataset_path, "rt", encoding="utf-8") as stream:
        rows = tuple(json.loads(line) for line in stream if line.strip())
    if len(rows) != 1000:
        raise ValueError(f"expected 1000 DS-1000 rows, found {len(rows)}")
    return rows


def evaluate_completion(
    *,
    execution_source: Path,
    dataset_path: Path,
    case_id: str,
    code: str,
) -> tuple[bool, str | None]:
    rows = _dataset(str(dataset_path.resolve()))
    index = int(case_id)
    if index < 0 or index >= len(rows):
        return False, "missing_problem"
    problem = rows[index]
    if int(problem["metadata"]["problem_id"]) != index:
        return False, "problem_id_mismatch"
    test_program = (
        str(problem["code_context"])
        + "\n"
        + f"code = {code!r}\n"
        + "test_execution(code)\n"
        + (
            "test_string(code)\n"
            if "test_string(" in str(problem["code_context"])
            else "\n"
        )
    )
    try:
        execution = _execution_module(str(execution_source.resolve()))
        result = execution.check_correctness(
            test_program,
            timeout=120,
            completion_id=index,
        )
        passed = bool(result["passed"])
        return passed, None if passed else str(result.get("result") or "failed")
    except Exception as exc:
        return False, type(exc).__name__


def evaluate_completion_isolated(
    *,
    execution_python: Path | None = None,
    execution_source: Path,
    dataset_path: Path,
    case_id: str,
    code: str,
) -> tuple[bool, str | None]:
    """Evaluate in a clean interpreter, before any model-SDK threads exist."""
    project_root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            [
                str(execution_python or sys.executable),
                "-m",
                "ds1000_harness.evaluate_ds1000_one",
                "--execution-source",
                str(execution_source.resolve()),
                "--dataset",
                str(dataset_path.resolve()),
                "--case-id",
                case_id,
            ],
            input=code,
            text=True,
            capture_output=True,
            cwd=project_root,
            timeout=150,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "isolated_evaluator_timeout"
    if completed.returncode != 0:
        return False, f"isolated_evaluator_exit_{completed.returncode}"
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return False, "isolated_evaluator_invalid_output"
    return bool(payload["passed"]), payload.get("error")
