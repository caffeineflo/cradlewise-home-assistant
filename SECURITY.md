# Security Policy

## Supported versions

Security fixes are applied to the latest published release and the `main`
branch.

## Reporting a vulnerability

Report vulnerabilities through GitHub's private security advisory feature.
Do not open a public issue for exposed credentials, authentication bypasses,
private video access, or certificate material.

Include the affected version, deployment shape, reproduction steps, and impact.
Remove baby images, video, account credentials, API tokens, device certificates,
and private hostnames from logs before attaching them.

If a secret may have been exposed, rotate it immediately. This includes the
bridge bearer token, RTSP credentials, Cradlewise account password, official
Data API token, and device certificate material.
