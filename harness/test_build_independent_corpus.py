from __future__ import annotations

from harness.build_independent_corpus import (
    CommitRecord,
    build_sample,
    choose_records,
)


def test_build_sample_keeps_only_existing_modified_code_files() -> None:
    record = CommitRecord(
        commit="b" * 40,
        parent="a" * 40,
        message="Handle streamed responses without buffering the body",
        changes=(("M", "src/client.py"), ("M", "tests/test_client.py")),
    )

    sample = build_sample("example/project", record)

    assert sample is not None
    assert sample["base_commit"] == "a" * 40
    assert sample["query"] == {"intent": record.message}
    assert sample["gold"]["root_cause_files"] == [
        "src/client.py",
        "tests/test_client.py",
    ]


def test_build_sample_rejects_path_leakage_and_non_modified_files() -> None:
    leaking = CommitRecord(
        commit="b" * 40,
        parent="a" * 40,
        message="Fix src/client.py when a response is streamed",
        changes=(("M", "src/client.py"),),
    )
    added = CommitRecord(
        commit="c" * 40,
        parent="a" * 40,
        message="Handle streamed responses without buffering the body",
        changes=(("A", "src/streaming.py"),),
    )

    assert build_sample("example/project", leaking) is None
    assert build_sample("example/project", added) is None


def test_choose_records_is_deterministic_and_message_distinct() -> None:
    records = [
        CommitRecord(
            commit=f"{index:040x}",
            parent="a" * 40,
            message=f"Correct distinct request behavior number {index}",
            changes=(("M", f"src/module_{index}.py"),),
        )
        for index in range(8)
    ]
    records.append(
        CommitRecord(
            commit="f" * 40,
            parent="a" * 40,
            message=records[0].message,
            changes=(("M", "src/duplicate.py"),),
        )
    )

    first = choose_records("example/project", records, limit=3)
    second = choose_records("example/project", list(reversed(records)), limit=3)

    assert [record.commit for record in first] == [
        record.commit for record in second
    ]
    assert len({record.message for record in first}) == 3
