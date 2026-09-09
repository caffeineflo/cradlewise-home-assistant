# Bridge image security

Reviewed: 2026-09-09. Revisit by 2026-09-16, before the next release, or when a
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

The hardened candidate removes pip and its vendored packages, plus uv and uvx,
from the final image. This removes four fixable package/advisory records across
three distinct advisories found in the previous runtime. Build tools remain
in the build stage only. The build-stage uv pin is also updated to 0.12.12;
its AMD64 and ARM64 images have no high/critical findings in the same scanner database.

The 2026-09-09 scan still reports 229 high/critical package/advisory records per architecture,
covering 57 distinct advisories in Debian packages. Seven records are critical.
Repeated records across FFmpeg binary packages are not separate vulnerabilities.
The scanner lists no fixed Debian package version for these findings. That does
not mean upstream has no fix, or that the image is vulnerability-free. Debian's
[FFmpeg tracker](https://security-tracker.debian.org/tracker/source-package/ffmpeg)
and the other source-package trackers remain the update authority.

The following is a source-path assessment, not an exploit test or a blanket
declaration that every transitive library is unreachable. Keep every finding
in the reports. Reassess whenever supported inputs, codecs, protocols, mounts,
privileges, or dependencies change.

| Source package | High/critical advisory IDs | Assessment of the current bridge path |
|---|---|---|
| FFmpeg | CVE-2026-58049, CVE-2026-64830, CVE-2026-64831, CVE-2026-64832, CVE-2026-64833, CVE-2026-64834, CVE-2026-64835, CVE-2026-66036, CVE-2026-66039, CVE-2026-66040, CVE-2026-66041, CVE-2026-70628, CVE-2026-70632, CVE-2026-75142, CVE-2026-75143, CVE-2026-75144, CVE-2026-75146 | The sink explicitly selects H.264 or raw video and PCM inputs, with RTSP output. It does not select RASC, HEVC/Vulkan, NVDEC, DTS/SPDIF, ASF, ADX, CAF/MACE, PNG/APNG, subtitle/QR/denoise paths, CFHD, MPEG-PS, RIST, Dirac, or DASH. No affected path identified in the configured sink; do not generalize this to arbitrary FFmpeg use. |
| util-linux | CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 | Mount, namespace, and privileged helper operations are not used. Non-root, dropped capabilities, and no-new-privileges constrain these local escalation paths. |
| gzip | CVE-2026-41992 | The service does not invoke gzip on uploaded archives. |
| acl | CVE-2026-54369 | No privileged path-based ACL operations in the bridge. |
| cJSON | CVE-2026-16554, CVE-2026-29036, CVE-2026-67215, CVE-2026-67216 | MQTT/HTTP JSON uses Python's parser, not cJSON. No cJSON Patch/Compare path identified. The first advisory concerns 32-bit builds; only 64-bit images are supported. Transitive library use has not been exhaustively traced. |
| expat | CVE-2026-76956, CVE-2026-76957 | No user-supplied XML endpoint. Transitive XML/error-response parsing is not proven unreachable; retain as an unresolved dependency risk. |
| glib2.0 | CVE-2026-58010, CVE-2026-58011, CVE-2026-58012, CVE-2026-58013, CVE-2026-58014, CVE-2026-58015, CVE-2026-58016 | No configured D-Bus, GVariant, GLib regex, keyfile, or GIOChannel input path. Indirect library calls have not been exhaustively traced. |
| mbedtls | CVE-2026-25835, CVE-2026-34872, CVE-2026-34873, CVE-2026-34875 | MQTT and WebRTC use OpenSSL-backed Python libraries. No Mbed TLS server, session-resumption, or FFDH export path identified. Its presence through media dependencies is not proof of complete unreachability. |
| ncurses | CVE-2025-69720 | The bridge does not invoke infocmp or accept terminal descriptions. |
| libsndfile | CVE-2026-37555 | No WAV/IMA ADPCM file ingestion; audio enters the sink as PCM. |
| sqlite3 | CVE-2026-11822, CVE-2026-11824 | The bridge does not open SQLite databases or execute FTS5 queries. |
| systemd | CVE-2026-16742 | systemd-homed is not run; the Python process is the container entry point. |
| tiff | CVE-2026-36849, CVE-2026-52490 | No TIFF input or tiffcrop invocation. Snapshots are generated as JPEG from decoded video. |
| libxml2 | CVE-2026-6653, CVE-2026-86140 | No configured XML input. Indirect library parsing is not proven unreachable; retain as an unresolved dependency risk. |
| perl | CVE-2026-13221, CVE-2026-42496, CVE-2026-42497, CVE-2026-48962, CVE-2026-57432, CVE-2026-57433, CVE-2026-8376, CVE-2026-9538 | No Perl interpreter, regex, archive extraction, or deserialization is invoked by the service. CVE-2026-8376 additionally requires a 32-bit build. |

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
