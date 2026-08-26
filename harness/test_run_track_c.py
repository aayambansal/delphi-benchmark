from __future__ import annotations

from harness.run_track_c import agent_run_status


def test_agent_run_status_requires_every_expected_case() -> None:
    assert agent_run_status(expected_cases=40, completed_cases=40) == "done"
    assert agent_run_status(expected_cases=40, completed_cases=39) == "failed"
    assert agent_run_status(expected_cases=0, completed_cases=0) == "failed"
