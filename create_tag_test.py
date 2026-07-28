import pathlib
from unittest import mock

import git
import pytest

from create_tag import PRETTY_TYPES, CommitMessage, enumerate_changes


def _commit(message, sha="abc123", email="dev@example.com"):
    """A constrained stand-in for the git.Commit attributes the parser touches."""
    commit = mock.create_autospec(git.Commit, instance=True)
    commit.message = message
    commit.hexsha = sha
    commit.author = mock.create_autospec(git.Actor, instance=True)
    commit.author.email = email
    return commit


def test_parse_feat_with_scope():
    parsed = CommitMessage.parse(_commit("feat(api): add new endpoint"))
    assert parsed is not None
    assert parsed.type == "feat"
    assert parsed.scope == "(api)"
    assert parsed.description == "add new endpoint"
    assert parsed.breaking_changes == []


def test_parse_breaking_change_in_body():
    parsed = CommitMessage.parse(
        _commit("fix: handle nil case\n\nBREAKING CHANGE: response shape changed")
    )
    assert parsed is not None
    assert parsed.type == "fix"
    assert parsed.breaking_changes == ["response shape changed"]


def test_parse_non_conventional_returns_none():
    assert CommitMessage.parse(_commit("not a conventional commit")) is None


def test_pretty_types_covers_all_emitted_types():
    assert set(PRETTY_TYPES) >= {"feat", "fix", "perf"}


TAG = "v2.202604010000.1"


@pytest.fixture
def repo(tmp_path):
    """Throwaway repo: one tagged commit, then feat -> fix -> perf on top."""
    repo = git.Repo.init(tmp_path, initial_branch="main")
    with repo.config_writer() as cw:
        cw.set_value("user", "email", "test@example.com")
        cw.set_value("user", "name", "Test User")

    def commit(filename, message):
        (pathlib.Path(tmp_path) / filename).write_text(filename)
        repo.index.add([filename])
        return repo.index.commit(message)

    commit("a.txt", "chore: initial")
    repo.create_tag(TAG, message="first deploy")
    commit("b.txt", "feat(api): add new endpoint")
    commit("c.txt", "fix: handle nil case")
    commit("d.txt", "perf: speed up parser")
    return repo


def test_enumerate_changes_yields_commits_since_tag(repo):
    changes = list(enumerate_changes(repo, TAG, repo.head.commit))
    assert [c.description for c in changes] == [
        "speed up parser",
        "handle nil case",
        "add new endpoint",
    ]


def test_enumerate_changes_range_is_bounded_by_head_commit(repo):
    """Regression guard: the range must end at head_commit, not at HEAD.

    Deploying an older SHA must not pick up commits landed after it. This fails
    if the revision range is built from anything other than the head_commit
    argument.
    """
    fix_commit = repo.commit("HEAD~1")
    changes = list(enumerate_changes(repo, TAG, fix_commit))
    assert [c.description for c in changes] == ["handle nil case", "add new endpoint"]


def test_enumerate_changes_skips_non_conventional_commits(repo):
    (pathlib.Path(repo.working_tree_dir) / "e.txt").write_text("e")
    repo.index.add(["e.txt"])
    repo.index.commit("wip nonsense")
    changes = list(enumerate_changes(repo, TAG, repo.head.commit))
    assert [c.description for c in changes] == [
        "speed up parser",
        "handle nil case",
        "add new endpoint",
    ]


def test_enumerate_changes_respects_max_commits(repo):
    changes = list(enumerate_changes(repo, TAG, repo.head.commit, max_commits=2))
    assert [c.description for c in changes] == ["speed up parser", "handle nil case"]


def test_enumerate_changes_without_merge_base_yields_nothing(repo):
    """No merge base (e.g. an orphan history) is swallowed, not raised."""
    orphan = repo.git.commit_tree(repo.head.commit.tree.hexsha, m="feat: orphan")
    assert list(enumerate_changes(repo, TAG, repo.commit(orphan))) == []
