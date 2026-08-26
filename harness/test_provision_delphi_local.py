from __future__ import annotations

from harness import provision_delphi_local


def test_indexed_record_requires_searchable_files_and_chunks() -> None:
    base = {
        "repo": "example/project",
        "revision": "a" * 40,
        "status": "indexed",
    }

    assert provision_delphi_local.is_valid_indexed_record(
        {
            **base,
            "metadata": {"files_indexed": 3, "chunks_created": 7},
        }
    )
    assert not provision_delphi_local.is_valid_indexed_record(
        {
            **base,
            "metadata": {"files_indexed": 3, "chunks_created": 0},
        }
    )
    assert not provision_delphi_local.is_valid_indexed_record(base)


def test_provision_one_uses_custom_corpus_roots(monkeypatch, tmp_path) -> None:
    bare_root = tmp_path / "bare"
    snapshot_root = tmp_path / "snapshots"
    materialized = snapshot_root / "example__project" / ("a" * 40)
    materialized.mkdir(parents=True)
    calls = []

    def fake_materialize(repo, commit, **kwargs):
        calls.append((repo, commit, kwargs))
        return materialized

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "repo_id": "source-id",
                "chunks_created": 3,
                "files_indexed": 1,
            }

    class Http:
        def post(self, url, **kwargs):
            assert url == "http://delphi/v1/repositories/index/local"
            assert kwargs["json"]["path"] == (
                "/bench/corpus/example__project/" + "a" * 40
            )
            return Response()

    monkeypatch.setattr(
        provision_delphi_local,
        "materialize_snapshot",
        fake_materialize,
    )

    result = provision_delphi_local.provision_one(
        Http(),
        "http://delphi",
        "key",
        "example/project",
        "a" * 40,
        bare_root=bare_root,
        snapshot_root=snapshot_root,
        container_root=provision_delphi_local.CONTAINER_ROOT,
    )

    assert result["status"] == "indexed"
    assert calls == [
        (
            "example/project",
            "a" * 40,
            {
                "bare_root": bare_root,
                "snapshot_root": snapshot_root,
            },
        )
    ]


def test_provision_one_force_reindexes_zero_chunk_source(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    materialized = snapshot_root / "example__project" / ("b" * 40)
    materialized.mkdir(parents=True)
    monkeypatch.setattr(
        provision_delphi_local,
        "materialize_snapshot",
        lambda *_args, **_kwargs: materialized,
    )
    requests = []

    class Response:
        status_code = 200

        def __init__(self, chunks_created: int) -> None:
            self.chunks_created = chunks_created

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "repo_id": "source-id",
                "chunks_created": self.chunks_created,
                "files_indexed": 12,
            }

    class Http:
        def post(self, _url, **kwargs):
            requests.append(kwargs["json"])
            return Response(0 if len(requests) == 1 else 5)

    result = provision_delphi_local.provision_one(
        Http(),
        "http://delphi",
        "key",
        "example/project",
        "b" * 40,
        snapshot_root=snapshot_root,
    )

    assert result["status"] == "indexed"
    assert result["metadata"]["chunks_created"] == 5
    assert [request.get("force_reindex", False) for request in requests] == [
        False,
        True,
    ]


def test_provision_one_fails_closed_when_forced_reindex_stays_empty(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    materialized = snapshot_root / "example__project" / ("c" * 40)
    materialized.mkdir(parents=True)
    monkeypatch.setattr(
        provision_delphi_local,
        "materialize_snapshot",
        lambda *_args, **_kwargs: materialized,
    )
    requests = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "repo_id": "source-id",
                "chunks_created": 0,
                "files_indexed": 12,
            }

    class Http:
        def post(self, _url, **kwargs):
            requests.append(kwargs["json"])
            return Response()

    result = provision_delphi_local.provision_one(
        Http(),
        "http://delphi",
        "key",
        "example/project",
        "c" * 40,
        snapshot_root=snapshot_root,
    )

    assert result["status"] == "failed"
    assert "no_searchable_chunks_after_force_reindex" in result["error"]
    assert [request.get("force_reindex", False) for request in requests] == [
        False,
        True,
    ]
