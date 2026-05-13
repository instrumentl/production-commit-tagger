from types import SimpleNamespace

from create_tag import PRETTY_TYPES, CommitMessage


def _commit(message, sha="abc123", email="dev@example.com"):
    return SimpleNamespace(
        message=message,
        hexsha=sha,
        author=SimpleNamespace(email=email),
    )


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
