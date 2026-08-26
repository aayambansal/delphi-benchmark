from __future__ import annotations

import importlib


def test_index_audit_rejects_missing_chunk_embeddings() -> None:
    try:
        audit_module = importlib.import_module("harness.audit_delphi_index")
    except ModuleNotFoundError:
        audit_module = None
    build_audit = getattr(
        audit_module,
        "build_index_audit",
        lambda *_args, **_kwargs: {"complete": True},
    )
    required = {
        ("owner/one", "aaa"),
        ("owner/two", "bbb"),
    }
    manifest_rows = [
        {
            "repo": "owner/one",
            "revision": "aaa",
            "source_id": "source-one",
            "status": "indexed",
            "metadata": {"files_indexed": 3, "chunks_created": 5},
        },
        {
            "repo": "owner/two",
            "revision": "bbb",
            "source_id": "source-two",
            "status": "indexed",
            "metadata": {"files_indexed": 4, "chunks_created": 7},
        },
    ]
    database_rows = {
        "source-one": {"files": 3, "chunks": 5, "embeddings": 5},
        "source-two": {"files": 4, "chunks": 7, "embeddings": 6},
    }

    audit = build_audit(required, manifest_rows, database_rows)

    assert audit["complete"] is False
    assert audit["required_snapshot_pairs"] == 2
    assert audit["valid_snapshot_pairs"] == 2
    assert audit["missing_snapshot_pairs"] == []
    assert audit["extra_snapshot_pairs"] == []
    assert audit["database"] == {
        "repositories": 2,
        "files": 7,
        "chunks": 12,
        "embeddings": 11,
        "missing_source_ids": [],
        "zero_file_source_ids": [],
        "zero_chunk_source_ids": [],
        "chunk_embedding_mismatch_source_ids": ["source-two"],
    }
