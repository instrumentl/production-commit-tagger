import datetime
import importlib.machinery
import importlib.util
import os
from unittest import mock

# Import create-tag as a module (it has no .py extension)
_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "create-tag")
_loader = importlib.machinery.SourceFileLoader("create_tag", _path)
spec = importlib.util.spec_from_loader("create_tag", _loader)
create_tag = importlib.util.module_from_spec(spec)

# Prevent main() from running at import time by patching argparse
with mock.patch("argparse.ArgumentParser.parse_args",
                side_effect=SystemExit(0)):
    try:
        spec.loader.exec_module(create_tag)
    except SystemExit:
        pass

CommitMessage = create_tag.CommitMessage


# -- Helpers for building fake git objects --

def _fake_commit(message, author_email="dev@example.com"):
    commit = mock.MagicMock()
    commit.message = message
    commit.author.email = author_email
    return commit


def _fake_tag(name, date_ts):
    tag = mock.MagicMock()
    tag.name = name
    tag.object.tagged_date = date_ts
    return tag


# ---- CommitMessage.parse tests ----

class TestCommitMessageParse:
    def test_feat(self):
        commit = _fake_commit("feat: add new button")
        result = CommitMessage.parse(commit)
        assert result.type == "feat"
        assert result.scope is None
        assert result.description == "add new button"
        assert result.author == "dev@example.com"
        assert result.breaking_changes == []

    def test_fix_with_scope(self):
        commit = _fake_commit("fix(api): handle null response")
        result = CommitMessage.parse(commit)
        assert result.type == "fix"
        assert result.scope == "(api)"
        assert result.description == "handle null response"

    def test_chore(self):
        commit = _fake_commit("chore: bump dependencies")
        result = CommitMessage.parse(commit)
        assert result.type == "chore"
        assert result.description == "bump dependencies"

    def test_breaking_change_in_body(self):
        commit = _fake_commit(
            "feat: revamp auth\n\nBREAKING CHANGE: old tokens no longer valid"
        )
        result = CommitMessage.parse(commit)
        assert result.type == "feat"
        assert result.breaking_changes == ["old tokens no longer valid"]

    def test_multiple_breaking_changes(self):
        commit = _fake_commit(
            "feat: big change\n\n"
            "BREAKING CHANGE: removed endpoint X\n"
            "BREAKING CHANGE: changed response format"
        )
        result = CommitMessage.parse(commit)
        assert result.breaking_changes == [
            "removed endpoint X",
            "changed response format",
        ]

    def test_breaking_changes_plural_keyword(self):
        commit = _fake_commit(
            "feat: thing\n\nBREAKING CHANGES: plural form works too"
        )
        result = CommitMessage.parse(commit)
        assert result.breaking_changes == ["plural form works too"]

    def test_non_conventional_commit_returns_none(self):
        commit = _fake_commit("just a random message")
        assert CommitMessage.parse(commit) is None

    def test_merge_commit_returns_none(self):
        commit = _fake_commit("Merge branch 'main' into feature")
        assert CommitMessage.parse(commit) is None

    def test_empty_body(self):
        commit = _fake_commit("fix: typo\n")
        result = CommitMessage.parse(commit)
        assert result.type == "fix"
        assert result.breaking_changes == []

    def test_preserves_author_email(self):
        commit = _fake_commit("fix: thing", author_email="alice@corp.com")
        result = CommitMessage.parse(commit)
        assert result.author == "alice@corp.com"


# ---- get_existing_tags tests ----

class TestGetExistingTags:
    def test_filters_by_prefix(self):
        utc = datetime.timezone.utc
        ts = int(datetime.datetime(2024, 1, 1, tzinfo=utc).timestamp())
        repo = mock.MagicMock()
        repo.tags = [
            _fake_tag("v2.20240101T000000.1", ts),
            _fake_tag("v1.old", ts),
            _fake_tag("v2.20240102T000000.2", ts + 86400),
        ]
        results = list(create_tag.get_existing_tags(repo, "v2."))
        assert len(results) == 2
        names = [tag.name for tag, _ in results]
        assert "v2.20240101T000000.1" in names
        assert "v2.20240102T000000.2" in names

    def test_empty_tags(self):
        repo = mock.MagicMock()
        repo.tags = []
        assert list(create_tag.get_existing_tags(repo, "v2.")) == []

    def test_uses_committed_date_fallback(self):
        utc = datetime.timezone.utc
        ts = int(
            datetime.datetime(2024, 6, 15, tzinfo=utc).timestamp()
        )
        tag = mock.MagicMock()
        tag.name = "v2.test"
        # Simulate a lightweight tag (no tagged_date)
        del tag.object.tagged_date
        tag.object.committed_date = ts
        repo = mock.MagicMock()
        repo.tags = [tag]
        results = list(create_tag.get_existing_tags(repo, "v2."))
        assert len(results) == 1
        expected = datetime.datetime(2024, 6, 15, tzinfo=utc)
        assert results[0][1] == expected


# ---- enumerate_changes tests ----

class TestEnumerateChanges:
    def test_yields_parsed_commits(self):
        repo = mock.MagicMock()
        repo.git.merge_base.return_value = "abc123"

        commits = [
            _fake_commit("feat: first feature"),
            _fake_commit("fix: a bugfix"),
            _fake_commit("not a conventional commit"),
        ]
        repo.iter_commits.return_value = iter(commits)

        tag = mock.MagicMock()
        commit_obj = mock.MagicMock()
        commit_obj.hexsha = "def456"

        results = list(create_tag.enumerate_changes(repo, tag, commit_obj))
        assert len(results) == 2
        assert results[0].type == "feat"
        assert results[1].type == "fix"

    def test_returns_none_when_no_merge_base(self):
        import git as gitmodule

        repo = mock.MagicMock()
        repo.git.merge_base.side_effect = (
            gitmodule.exc.GitCommandError("merge-base", 1)
        )

        tag = mock.MagicMock()
        commit_obj = mock.MagicMock()

        result = list(create_tag.enumerate_changes(
            repo, tag, commit_obj
        ))
        assert result == []

    def test_respects_max_commits(self):
        repo = mock.MagicMock()
        repo.git.merge_base.return_value = "abc123"

        commits = [_fake_commit(f"feat: feature {i}") for i in range(100)]
        repo.iter_commits.return_value = iter(commits)

        tag = mock.MagicMock()
        commit_obj = mock.MagicMock()
        commit_obj.hexsha = "def456"

        results = list(create_tag.enumerate_changes(
            repo, tag, commit_obj, max_commits=5
        ))
        assert len(results) == 5


# ---- main() integration tests ----

class TestMain:
    def _run_main(self, tmp_path, extra_args=None, env_overrides=None):
        """Run main() with a fake git repo and capture output."""
        utc = datetime.timezone.utc
        ts = int(datetime.datetime(
            2024, 3, 15, 12, 0, 0, tzinfo=utc
        ).timestamp())

        fake_commit = mock.MagicMock()
        fake_commit.hexsha = "aabbccdd" * 5
        fake_commit.author.email = "dev@example.com"

        fake_tag = mock.MagicMock()
        fake_tag.name = "v2.20240314T120000.100"
        fake_tag.object.tagged_date = ts - 86400

        fake_repo = mock.MagicMock()
        fake_repo.commit.return_value = fake_commit
        fake_repo.tags = [fake_tag]
        fake_repo.git.merge_base.return_value = "000000"
        fake_repo.iter_commits.return_value = iter([
            _fake_commit("feat: cool feature"),
            _fake_commit("fix(ui): broken layout"),
        ])

        argv = [
            "create-tag",
            "--checkout-dir", str(tmp_path),
            "--prefix", "v2.",
            "--sha", "aabbccdd" * 5,
            "--repository", "org/repo",
            "--pretend",
            "2024-03-15T12:00:00",
            "42",
        ]
        if extra_args:
            argv.extend(extra_args)

        env = {
            "GITHUB_ACTOR": "testuser",
            "GITHUB_OUTPUT": "",
        }
        if env_overrides:
            env.update(env_overrides)

        with mock.patch("git.Repo", return_value=fake_repo), \
             mock.patch.dict(os.environ, env, clear=False), \
             mock.patch("sys.argv", argv):
            # Capture stdout
            from io import StringIO
            captured = StringIO()
            with mock.patch("sys.stdout", captured):
                create_tag.main()
            return captured.getvalue(), fake_repo

    def test_tag_name_format(self, tmp_path):
        output, _ = self._run_main(tmp_path)
        assert "tag_name=v2.20240315T120000.42" in output

    def test_pretend_does_not_create_tag(self, tmp_path):
        _, repo = self._run_main(tmp_path)
        repo.create_tag.assert_not_called()

    def test_release_notes_file_written(self, tmp_path):
        self._run_main(tmp_path)
        notes_file = tmp_path / "release_notes-v2.20240315T120000.42.txt"
        assert notes_file.exists()
        content = notes_file.read_text()
        assert "aabbccdd" in content
        assert "@testuser" in content

    def test_release_notes_contain_changes(self, tmp_path):
        self._run_main(tmp_path)
        notes_file = tmp_path / "release_notes-v2.20240315T120000.42.txt"
        content = notes_file.read_text()
        assert "cool feature" in content
        assert "broken layout" in content

    def test_output_contains_release_body_path(self, tmp_path):
        output, _ = self._run_main(tmp_path)
        expected = "release_body_path=release_notes-v2.20240315T120000.42.txt"
        assert expected in output

    def test_github_output_written(self, tmp_path):
        github_output_file = tmp_path / "github_output.txt"
        self._run_main(tmp_path, env_overrides={
            "GITHUB_OUTPUT": str(github_output_file),
        })
        assert github_output_file.exists()
        content = github_output_file.read_text()
        assert "tag_name=" in content

    def test_no_token_skips_github_api(self, tmp_path):
        with mock.patch("github.Auth.Token") as mock_auth:
            self._run_main(tmp_path)
            mock_auth.assert_not_called()

    def test_verbose_flag(self, tmp_path):
        # Should not raise
        self._run_main(tmp_path, extra_args=["-v"])
