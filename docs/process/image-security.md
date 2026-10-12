# Bridge image security

Reviewed: 2026-10-11. Revisit by 2026-10-18, before the next release, or when a
scanner reports a new fixable high/critical finding, whichever comes first.

This applies to the optional bridge container, not Home Assistant's own image
or a consumer's MediaMTX installation.

## What the gates check

Pull requests and releases build `linux/amd64` and `linux/arm64` on native
GitHub runners. Each final image is tested as UID 10001 with no external
network, a read-only root filesystem, dropped capabilities, no-new-privileges,
and a PID limit. Checks cover CLI entry points, native imports, RSA certificate
creation, offline API startup, unhealthy media while disconnected, SIGTERM
shutdown, and synthetic H.264/AAC encoding and decoding.

Trivy scans OS and application dependencies in each final image. The complete
JSON report includes all severities and unfixed findings; it is retained for
30 days as an Actions artifact. A separate gate fails on any high/critical
finding for which the scanner lists a fixed version. Scanner failures also
fail the job. There is no advisory ignore list.

The `Published image security` workflow repeats the scan weekly and on manual
dispatch against both architectures of the latest full GitHub release. It
does not rebuild or deploy the image. Maintainers must enable notifications
for failed Actions runs and review these reports; this is not an alerting
backend installed on consumers' systems.

Both artifact builds and version checks must pass before either release
publisher runs. GHCR receives the same images that were tested, not a new build.
These checks complement Dependabot; they do not replace it.
Runtime package installation bypasses the build cache so new Debian packages
can be picked up. Updating packages inherited from the pinned Python base may
also require a base-image digest update.

## Current findings

The 0.2.10 candidate refreshes the pinned Python base, updates the locked PyJWT
and urllib3 dependencies to 2.15.1 and 2.8.0, and uses uv 0.13.0 in the build
stage only. Build tools remain excluded from the final runtime.

The [2026-10-11 candidate scan](https://github.com/caffeineflo/cradlewise-home-assistant/actions/runs/38187746457)
reports no Python package findings and no fixable high/critical findings on
either architecture. The complete reports still contain 216 high/critical
package/advisory records per architecture, covering 50 distinct advisories in
Debian packages. One record is critical. Each report also contains 297 medium,
186 low, and 24 unknown-severity records.

Repeated records across FFmpeg binary packages are not separate vulnerabilities.
The scanner lists no fixed Debian package version for the remaining high/critical
findings. That does not mean upstream has no fix, or that the image is
vulnerability-free. Debian's
[FFmpeg tracker](https://security-tracker.debian.org/tracker/source-package/ffmpeg)
and the other source-package trackers remain the update authority.

The following is a source-path assessment, not an exploit test or a blanket
declaration that every transitive library is unreachable. Keep every finding
in the reports. Reassess whenever supported inputs, codecs, protocols, mounts,
privileges, or dependencies change.

| Source package | High/critical advisory IDs | Assessment of the current bridge path |
|---|---|---|
| FFmpeg | CVE-2026-58049, CVE-2026-64830, CVE-2026-64832, CVE-2026-64833, CVE-2026-64834, CVE-2026-64835, CVE-2026-66036, CVE-2026-66039, CVE-2026-66040, CVE-2026-66041, CVE-2026-70628, CVE-2026-70632, CVE-2026-75142, CVE-2026-75143, CVE-2026-75144, CVE-2026-75146 | The sink explicitly selects H.264 or raw video and PCM inputs, with RTSP output. It does not select RASC, HEVC/Vulkan, NVDEC, DTS/SPDIF, ASF, ADX, CAF/MACE, PNG/APNG, subtitle/QR/denoise paths, CFHD, MPEG-PS, RIST, Dirac, or DASH. No affected path identified in the configured sink; do not generalize this to arbitrary FFmpeg use. |
| util-linux | CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | Mount, namespace, and privileged helper operations are not used. Non-root, dropped capabilities, and no-new-privileges constrain these local escalation paths. |
| acl | CVE-2026-54369 | No privileged path-based ACL operations in the bridge. |
| cJSON | CVE-2026-16554, CVE-2026-29036, CVE-2026-67215, CVE-2026-67216, CVE-2026-87933 | MQTT/HTTP JSON uses Python's parser, not cJSON. No cJSON Patch/Compare path identified. The first advisory concerns 32-bit builds; only 64-bit images are supported. Transitive library use has not been exhaustively traced. |
| expat | CVE-2026-66046, CVE-2026-76956, CVE-2026-76957, CVE-2026-77214, CVE-2026-93990 | No user-supplied XML endpoint. Transitive XML/error-response parsing is not proven unreachable; retain as an unresolved dependency risk. |
| gnutls28 | CVE-2026-88647, CVE-2026-88648 | MQTT and WebRTC use OpenSSL-backed Python libraries. Indirect media-library TLS paths have not been fully traced; retain as an unresolved dependency risk. |
| ncurses | CVE-2025-69720 | The bridge does not invoke infocmp or accept terminal descriptions. |
| libsndfile | CVE-2026-37555 | No WAV/IMA ADPCM file ingestion; audio enters the sink as PCM. |
| systemd | CVE-2026-16742 | systemd-homed is not run; the Python process is the container entry point. |
| tiff | CVE-2026-36849, CVE-2026-52490 | No TIFF input or tiffcrop invocation. Snapshots are generated as JPEG from decoded video. |
| libxml2 | CVE-2026-6653, CVE-2026-74860, CVE-2026-86138, CVE-2026-86139, CVE-2026-86140, CVE-2026-86142, CVE-2026-86143, CVE-2026-86144 | No configured XML input. Indirect library parsing is not proven unreachable; retain as an unresolved dependency risk. |
| perl | CVE-2026-9538 | No Perl interpreter, regex, archive extraction, or deserialization is invoked by the service. |
| librsvg | CVE-2026-96889 | The service does not accept SVG input. Indirect media-library use has not been fully traced; retain as an unresolved dependency risk. |
| libx11 | CVE-2026-88806 | The service does not open an X display. Indirect media-library use has not been fully traced; retain as an unresolved dependency risk. |
| libxrender | CVE-2026-88807 | The service does not open an X display. Indirect media-library use has not been fully traced; retain as an unresolved dependency risk. |

## Follow-up and limits

- Apply supported Debian/base-image security updates as they become available,
  then rerun both image builds and scans. Do not switch distributions or replace
  FFmpeg without testing the real media paths.
- Review the complete reports before release, including medium/low findings.
  Unknown reachability stays unknown; a lack of a packaged fix is not a waiver.
- Retain the restricted deployment settings in the example Compose file. Do not
  give the bridge host devices, privileged mode, or unneeded filesystem access.
- Scanner databases and package detection are incomplete. In particular,
  bundled native libraries in wheels need upstream review as well; a clean
  Python package result does not establish that every embedded library is safe.
- A newly released Debian security fix requires rebuilding and publishing the
  bridge. Existing containers do not update their packages automatically.
