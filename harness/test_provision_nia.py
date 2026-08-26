from __future__ import annotations

import pytest

from harness.provision_nia import source_identifier, source_status_outcome


def test_source_identifier_is_namespaced_per_account():
    assert source_identifier("arb3-new", "owner/repo", "ABC123") == (
        "/arb3-new/owner/repo/ABC123"
    )


@pytest.mark.parametrize("namespace", ["", "/", "../other", "arb3/new"])
def test_source_identifier_rejects_unsafe_namespaces(namespace):
    with pytest.raises(ValueError):
        source_identifier(namespace, "owner/repo", "abc123")


@pytest.mark.parametrize("status", ["indexed", "completed"])
def test_nia_success_statuses_are_normalized(status):
    assert source_status_outcome(status) == "indexed"


@pytest.mark.parametrize("status", ["failed", "error", "cancelled"])
def test_nia_failure_statuses_are_normalized(status):
    assert source_status_outcome(status) == "failed"


def test_nia_processing_status_remains_pending():
    assert source_status_outcome("processing") is None
