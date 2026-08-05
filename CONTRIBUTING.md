# Contributing

Thanks for helping improve Cradlewise support in Home Assistant.

## Development setup

Use Python 3.10 or newer and install the locked development environment:

```bash
uv sync --extra test --extra ha-test
```

Run the same core checks used by CI:

```bash
uv run --frozen --extra test python -m pytest
uv run --frozen --extra test ruff check .
uv run --frozen --extra test ruff format --check .
```

Changes to the Home Assistant integration must keep the `cradlewise_local`
domain and existing unique IDs stable. Include behavior-focused tests for new
bridge payloads, API normalization, config flow behavior, or entities.

## Reverse-engineering evidence

Protocol changes should cite the relevant decompiled class or official API
documentation in `docs/`. Do not commit APKs, decompiled output, certificates,
tokens, account credentials, `.env`, or captures containing private baby data.

## Pull requests

Keep each pull request focused. Explain the user-visible behavior, the evidence
behind protocol changes, and the checks you ran. Do not include generated or
scratch files from `fharr/`.
