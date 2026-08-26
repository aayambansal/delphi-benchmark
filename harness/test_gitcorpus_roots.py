from __future__ import annotations

from harness import gitcorpus


def test_git_corpus_passes_its_custom_bare_root(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_ls_tree(repo, commit, bare_root):
        calls.append((repo, commit, bare_root))
        return ["src/example.py"]

    monkeypatch.setattr(gitcorpus, "_ls_tree", fake_ls_tree)

    corpus = gitcorpus.GitCorpus(bare_root=tmp_path)

    assert corpus.list_files("example/project", "abc123") == [
        "src/example.py"
    ]
    assert calls == [("example/project", "abc123", tmp_path)]


def test_bare_path_accepts_an_explicit_root(tmp_path) -> None:
    assert gitcorpus.bare_path(
        "example/project",
        root=tmp_path,
    ) == tmp_path / "example__project.git"


def test_git_corpus_reads_materialized_snapshot_without_git(
    monkeypatch,
    tmp_path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    snapshot_file = (
        snapshot_root
        / "example__project"
        / "abc123"
        / "src"
        / "example.py"
    )
    snapshot_file.parent.mkdir(parents=True)
    snapshot_file.write_text("answer = 42\n")

    def fail_if_git_runs(*args, **kwargs):
        raise AssertionError("materialized snapshot should bypass git show")

    monkeypatch.setattr(gitcorpus.subprocess, "run", fail_if_git_runs)

    corpus = gitcorpus.GitCorpus(
        bare_root=tmp_path / "bare",
        snapshot_root=snapshot_root,
    )

    assert corpus.file_text(
        "example/project",
        "abc123",
        "src/example.py",
    ) == "answer = 42\n"
