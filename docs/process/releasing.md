# Release Process

The Home Assistant integration and `cradlewise-client` use the same release
version. A release is intentionally manual because publishing the client to
PyPI and making the HACS repository public are external, irreversible actions.

## One-time setup

1. Make `caffeineflo/cradlewise-local` public and keep GitHub Issues enabled.
   Confirm that GitHub's REST API reports a non-empty description, at least one
   repository topic, `archived: false`, and the root license as SPDX `MIT`.
2. Create a PyPI Trusted Publisher for project `cradlewise-client`:
   - Owner: `caffeineflo`
   - Repository: `cradlewise-local`
   - Workflow: `tests.yml`
   - Environment: `pypi`
3. Create a protected GitHub Actions environment named `pypi` and require
   approval before deployment.

No PyPI token is stored in GitHub. The release workflow receives a short-lived
OIDC publishing identity only after the environment is approved.

## Release checklist

1. Set the same version in:
   - `packages/cradlewise-client/pyproject.toml`
   - `custom_components/cradlewise/manifest.json`
   - the integration's `cradlewise-client==...` requirement
2. Update `CHANGELOG.md` and move the release notes out of `Unreleased`.
3. Run the Python 3.10, 3.12, and 3.14 test matrix, Home Assistant runtime
   tests, Ruff, yamllint, hassfest, package builds, and the bridge image build.
   The official HACS action must also pass against the pushed GitHub ref; local
   manifest-schema checks do not replace its repository metadata and tree
   checks.
4. Install the release candidate on Home Assistant and verify Automatic,
   Local only, Cloud only, reauthentication, reconfiguration, unload/reload,
   and optional media behavior.
5. Merge to `main` only after CI passes.
6. Push the `vX.Y.Z` tag. The tag CI must pass before the protected `pypi`
   environment is approved.
7. After PyPI contains the client package and tag CI is green, create the full
   GitHub release from that tag.

The tag triggers the client publish job only after the test, lint, Home
Assistant, and validation jobs pass. Its tag guard rejects a tag that does not
match the client package version. After PyPI shows the new client version,
confirm that a clean HACS install can resolve the integration requirement.

## HACS default catalog

Custom-repository installation is sufficient for the first public release.
For the default HACS catalog, wait for a full GitHub release with passing HACS
and hassfest checks, then submit the repository to `hacs/default`. Default
catalog review is a separate process and is not required for consumers to add
the public repository to HACS manually.
