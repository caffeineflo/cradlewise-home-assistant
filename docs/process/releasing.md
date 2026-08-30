# Release Process

The Home Assistant integration and `cradlewise-client` use the same release
version. A release is intentionally manual because publishing the client to
PyPI, making the GHCR package public, and creating the GitHub release are
external actions that require an explicit maintainer decision.

## One-time setup

1. Make `caffeineflo/cradlewise-home-assistant` public and keep GitHub Issues
   enabled.
   Confirm that GitHub's REST API reports a non-empty description, at least one
   repository topic, `archived: false`, and the root license as SPDX `MIT`.
2. Create a PyPI Trusted Publisher for project `cradlewise-client`:
   - Owner: `caffeineflo`
   - Repository: `cradlewise-home-assistant`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. Create a protected GitHub Actions environment named `pypi` and require
   approval before deployment.
4. In the `cradlewise-local-bridge` package settings:
   - Grant `caffeineflo/cradlewise-home-assistant` write access under
     "Manage Actions access".
   - Change the package visibility to public.
   - Connect the package to `caffeineflo/cradlewise-home-assistant` instead of
     an archived or renamed source repository.

No PyPI token or GHCR credential is stored in GitHub. The release workflow
receives a short-lived PyPI OIDC publishing identity only after the environment
is approved, and GitHub provides the tag workflow a repository-scoped package
token. Ordinary pull request and `main` CI builds the bridge image without
publishing it.

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
6. Push the `vX.Y.Z` tag. The release workflow must pass its unprivileged test,
   validation, and build jobs before the protected `pypi` environment is
   approved.
7. Approve the `pypi` deployment after reviewing the built distribution. The
   workflow publishes the client, publishes the versioned bridge image, and
   creates the full GitHub release only after both publications succeed.

The privileged PyPI job only downloads and publishes the artifact produced by
the unprivileged build job. The release guard rejects a tag unless it matches
the client package version, integration version, and pinned integration
requirement. After PyPI shows the new client version, confirm that a clean HACS
install can resolve the integration requirement.

## HACS default catalog

Custom-repository installation is sufficient for the first public release.
For the default HACS catalog, wait for a full GitHub release with passing HACS
and hassfest checks, then submit the repository to `hacs/default`. Default
catalog review is a separate process and is not required for consumers to add
the public repository to HACS manually.
