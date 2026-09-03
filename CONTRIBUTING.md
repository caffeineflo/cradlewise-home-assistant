# Contributing

Thanks for helping improve Cradlewise support in Home Assistant.
By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Use Python 3.10 or newer and install the locked development environment:

```bash
uv sync --extra test --extra ha-test
```

Run the same core checks used by CI:

```bash
uv run --locked --extra test python -m pytest
uv run --locked --extra test ruff check .
uv run --locked --extra test ruff format --check .
```

Changes to the Home Assistant integration must keep the `cradlewise`
domain and existing unique IDs stable. Include behavior-focused tests for new
bridge payloads, API normalization, config flow behavior, or entities.

## Reverse-engineering evidence

Protocol changes should cite the relevant decompiled class or official API
documentation in `docs/`. Base reverse-engineering evidence only on APKs
lawfully obtained from an installation you're authorized to use, not a
third-party APK mirror. Do not commit APKs, decompiled output, certificates,
tokens, account credentials, `.env`, or captures containing private baby data.

## Pull requests

Keep each pull request focused. Explain the user-visible behavior, the evidence
behind protocol changes, and the checks you ran. Do not include generated or
scratch files from `fharr/`.
