# README

This action does three things:

- Discovers the most recent production deployment (if one exists)
- Builds a changelog between the previous and new commits
- Creates a git tag corresponding to the current deployment

## Development Setup

Create a virtual environment and install dependencies using [uv](https://github.com/astral-sh/uv):

```sh
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt pytest
```

