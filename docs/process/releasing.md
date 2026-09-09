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
CI retains the tested architecture-specific image artifacts for seven days so
maintainers can run the live candidate gate before creating a release tag.

## Release checklist

1. Set the same version in:
   - the root `pyproject.toml` project and `cradlewise-client==...` requirement
   - `packages/cradlewise-client/pyproject.toml`
   - `custom_components/cradlewise/manifest.json`
   - the integration's `cradlewise-client==...` requirement
   - `.env.example`
   - the default bridge image in `examples/docker-compose.yaml`
2. Update `CHANGELOG.md` and move the release notes out of `Unreleased`.
3. Run the Python 3.10, 3.12, and 3.14 test matrix, Home Assistant runtime
   tests, Ruff, yamllint, hassfest, package builds, and both bridge image builds.
   The official HACS action must also pass against the pushed GitHub ref; local
   manifest-schema checks do not replace its repository metadata and tree
   checks. Confirm that Dependabot reports zero open alerts. The tag workflow
   enforces this before it can publish the client package or bridge image.
   Both final images must also pass the restricted-runtime, offline API startup,
   shutdown, and FFmpeg smoke tests, plus the complete-image vulnerability scan.
   Review unfixed findings against [Image Security](image-security.md). A green
   automated scan gate does not mean there are no unfixed vulnerabilities.
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
8. If the HACS default-catalog submission is still open, update its description
   to link the new release and its successful HACS/hassfest run. Don't post a
   bump comment or merge the upstream catalog branch unless a maintainer asks.

The minimum HA version is 2026.6.0 because the integration imports
`RepairsFlowResult`, added in [Home Assistant core #170263](https://github.com/home-assistant/core/pull/170263).
It is absent from 2026.5.0 and exported from 2026.6.0. Both PR and tag workflows
test that exact minimum and the current 2026.9.1 baseline, including all config,
repair, entity, and coordinator tests. Media test dependencies come from each
tested core version's manifests. Don't raise the minimum just to match a
new test-package release; recheck the API and dependency requirements first.

The privileged PyPI job only downloads and publishes the artifact produced by
the unprivileged build job. The release guard rejects a tag unless it matches
the root and client package versions, integration version and requirement,
example environment, and Compose bridge default. After PyPI shows the new
client version, confirm that a clean HACS install can resolve the integration
requirement.

Version parity is a shared prerequisite for both artifact builds. Neither
publisher runs until the client distribution and both architecture-specific
images have been built and validated. The GHCR publisher loads the tested
image artifacts instead of rebuilding them. Registry publication is not atomic
across PyPI and GHCR: a registry failure after one publish still needs maintainer
recovery, and the GitHub release waits for both publications to succeed.

### Maintainer live end-to-end gate

The live gate is intentionally maintainer-run because a public CI runner cannot
reach a private crib or Home Assistant installation. Before changing the live
component, record the target config entry ID, integration unique ID, entity IDs,
entity unique IDs, device ID, and hashes of any HomeKit AID/IID files. Back up
the installed component, `core.config_entries`, `core.entity_registry`, and the
HomeKit mapping files without printing credentials.

Run this loop against a crib that is safe to actuate:

1. Install the candidate over the existing custom component, run `ha core
   check`, restart Core, and confirm the same entry loads with the same registry
   identities.
2. Confirm fresh local and cloud provider state through redacted diagnostics.
   Verify the baby-presence and sleep entities report current state.
3. Request an authenticated Home Assistant camera proxy image and probe the
   configured reader stream. Require H.264 video at 1280x720 and AAC mono audio
   at 48 kHz when audio is enabled.
4. Toggle music and bounce on and back off. Require the reported entities to
   follow both changes, and leave both controls off after the test.
5. With the media companion configured in Automatic mode, stop only the
   companion. Require HA to fall back to cloud state and controls while the
   camera becomes unavailable. This installation uses the companion for its
   local state/control path; it does not also start a direct local MQTT client.
6. Start the companion. Require it to become healthy, Automatic mode to prefer
   local state again, the RTSP probe to pass, and the HA camera proxy to return
   a new image.
7. Reconfigure in place through Cloud only, Local only, and back to Automatic.
   Require the selected provider in each mode, confirm Local only removes stored
   email/password fields, and restore Automatic using the existing credentials.
8. Confirm the integration has no new unexpected log errors. Compare the final
   config-entry ID, unique IDs, device ID, entity count, and HomeKit AID/IID
   hashes to the baseline before tagging the release.

Do not automate invalid-password reauthentication against the live account.
Exercise that path with the Home Assistant runtime tests, then confirm the live
cloud path authenticates normally during Cloud-only and Automatic mode checks.
The runtime suite also forces local-provider failure and recovery to verify
Automatic fallback. Without a configured companion, HA uses direct local MQTT;
a live fallback test for that installation needs a separately approved
interruption of that MQTT path.

## HACS default catalog

Custom-repository installation is sufficient for the first public release.
For the default HACS catalog, wait for a full GitHub release with passing HACS
and hassfest checks, then submit the repository to `hacs/default`. Default
catalog review is a separate process and is not required for consumers to add
the public repository to HACS manually.
