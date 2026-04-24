# production-commit-tagger

GitHub composite action that runs after a production deployment and:

- Discovers the most recent production deployment tag (if one exists)
- Builds a conventional-commit changelog between that tag and the deploying SHA
- Creates a new annotated git tag of the form `<prefix><timestamp>.<deployment_id>`
- Exposes `tag_name`, `release_body_path`, and `commit_authors` as step outputs

## Usage

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0, fetch-tags: true }
- id: tag
  uses: instrumentl/production-commit-tagger@main
  with:
    timestamp: ${{ github.event.deployment.created_at }}
    deployment_id: ${{ github.event.deployment.id }}
    token: ${{ secrets.GITHUB_TOKEN }}  # optional; enables GitHub-user lookup for commit_authors
```

## Development

Requires [uv](https://github.com/astral-sh/uv). Version is pinned in `.tool-versions`.

```sh
uv sync                         # install runtime + dev deps into .venv
uv run ruff check               # lint
uv run ruff format              # format
uv run pyright                  # type check
uv run pytest                   # run tests
./smoke-test.sh                 # end-to-end: exercise the action against a throwaway repo
```

Pre-commit hooks are available via `pre-commit install`.

CI (`.github/workflows/ci.yml`) runs all of the above on every push and PR.
