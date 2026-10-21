# Security Policy

## Reporting a vulnerability

Email **security@example.com** (replace with the project's contact when bootstrapping) with a
description and reproduction steps. Do not open a public issue for security reports. We aim
to acknowledge within 2 business days.

## Supported versions

Only the latest minor release on PyPI receives security fixes. Pin `ligaxai~=X.Y`
and update promptly.

## What this library does with your credentials

- The API key is read from `api_key=` or `LIGA_X_API_KEY` and sent **only** as an
  `Authorization: Bearer` header to the configured base URL, over HTTPS by default.
- The key is never written to logs: `LIGA_X_LOG=debug` redacts `Authorization`
  before a record reaches any handler.
- Webhook verification (`ligaxai.webhooks.verify`) is constant-time via the
  reference `standardwebhooks` implementation and rejects timestamps outside the tolerance
  window to prevent replay.
- Keep the key on the server. The FastAPI helper exists so browsers call *your* backend,
  never the API directly.

## Supply chain

- Dependencies are pinned in `uv.lock`; CI fails if the lockfile is stale.
- Releases are built in CI and published with PyPI trusted publishing (OIDC) and PEP 740
  attestations — no long-lived PyPI token exists.
