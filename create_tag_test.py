import pathlib
from unittest import mock

import git
import github
import github.Commit
import github.NamedUser
import github.Repository
import pytest

from create_tag import PRETTY_TYPES, CommitMessage, enumerate_changes, github_logins


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


def _gh_repo(sha_to_login):
    """Repository stub whose get_commit maps a SHA to a GitHub login (None = ghost)."""
    gh_repo = mock.create_autospec(github.Repository.Repository, instance=True)

    def get_commit(sha):
        gh_commit = mock.create_autospec(github.Commit.Commit, instance=True)
        login = sha_to_login[sha]
        if login is None:
            gh_commit.author = None
        else:
            gh_commit.author = mock.create_autospec(github.NamedUser.NamedUser, instance=True)
            gh_commit.author.login = login
        return gh_commit

    gh_repo.get_commit.side_effect = get_commit
    return gh_repo


def test_github_logins_preserves_commit_order():
    """Order is the output contract -- #11 wanted commit order, a set gave hash order."""
    author_to_sha = {
        "zoe@example.com": "sha1",
        "adam@example.com": "sha2",
        "mia@example.com": "sha3",
    }
    gh_repo = _gh_repo({"sha1": "zoe-gh", "sha2": "adam-gh", "sha3": "mia-gh"})
    assert github_logins(gh_repo, author_to_sha) == ["zoe-gh", "adam-gh", "mia-gh"]


def test_github_logins_dedupes_keeping_first_position():
    author_to_sha = {
        "zoe@work.com": "sha1",
        "adam@example.com": "sha2",
        "zoe@personal.com": "sha3",
    }
    gh_repo = _gh_repo({"sha1": "zoe-gh", "sha2": "adam-gh", "sha3": "zoe-gh"})
    assert github_logins(gh_repo, author_to_sha) == ["zoe-gh", "adam-gh"]


def test_github_logins_skips_lookup_failures_without_losing_the_rest():
    author_to_sha = {"a@example.com": "sha1", "b@example.com": "sha2", "c@example.com": "sha3"}
    resolvable = _gh_repo({"sha1": "a-gh", "sha3": "c-gh"})

    def get_commit(sha):
        if sha == "sha2":
            raise github.GithubException(404, "Not Found", None)
        return resolvable.get_commit(sha)

    gh_repo = mock.create_autospec(github.Repository.Repository, instance=True)
    gh_repo.get_commit.side_effect = get_commit
    assert github_logins(gh_repo, author_to_sha) == ["a-gh", "c-gh"]


def test_github_logins_skips_commits_with_no_github_author():
    """Unlinked email -> gh_commit.author is None; must not emit an entry."""
    author_to_sha = {"a@example.com": "sha1", "ghost@example.com": "sha2"}
    gh_repo = _gh_repo({"sha1": "a-gh", "sha2": None})
    assert github_logins(gh_repo, author_to_sha) == ["a-gh"]
