from pathlib import Path

from harness import provision_delphi_local


class _Response:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "success": True,
            "repo_id": "repo-1",
            "files_indexed": 2,
            "chunks_created": 3,
        }


class _Http:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    def post(self, _url: str, **kwargs) -> _Response:
        self.requests.append(kwargs["json"])
        return _Response()


def test_force_reindex_is_sent_on_the_first_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "owner__repo" / "abc"
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(
        provision_delphi_local,
        "materialize_snapshot",
        lambda *_args, **_kwargs: snapshot,
    )
    http = _Http()

    result = provision_delphi_local.provision_one(
        http,
        "http://delphi",
        "key",
        "owner/repo",
        "abc",
        snapshot_root=tmp_path,
        container_root=tmp_path,
        force_reindex=True,
    )

    assert result["status"] == "indexed"
    assert http.requests == [
        {
            "path": (tmp_path / "owner__repo" / "abc").as_posix(),
            "name": "ARB owner/repo@abc",
            "quality_mode": "agent",
            "include_tests": True,
            "include_docs": True,
            "include_examples": True,
            "force_reindex": True,
        }
    ]


def test_default_first_attempt_does_not_force_reindex(
    monkeypatch,
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "owner__repo" / "abc"
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(
        provision_delphi_local,
        "materialize_snapshot",
        lambda *_args, **_kwargs: snapshot,
    )
    http = _Http()

    provision_delphi_local.provision_one(
        http,
        "http://delphi",
        "key",
        "owner/repo",
        "abc",
        snapshot_root=tmp_path,
        container_root=tmp_path,
    )

    assert "force_reindex" not in http.requests[0]
