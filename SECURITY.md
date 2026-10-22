# Security Policy

## Reporting a vulnerability

Email **security@ligaments.ai** with a description and steps to reproduce. Please do not open a
public issue, pull request or discussion for a security report. We acknowledge reports within 2
business days and tell you when a fix ships; we credit reporters who want to be credited.

## Supported versions

Only the latest minor release on PyPI receives security fixes. Pin `ligaxai~=X.Y` and update
promptly. Pre-releases (`.devN`) are for testing and receive none.

## What this library does with your credentials

- The API key is read from `api_key=` or `LIGAX_API_KEY` and sent **only** as an
  `Authorization: Bearer` header to the configured base URL, over HTTPS by default. The client
  refuses to start without a key, or with one that contains whitespace or control characters.
- The key is never written to logs: `LIGAX_LOG=debug` redacts `Authorization` values and any
  LigaX key, client token or webhook secret before a record reaches a handler. It does not appear
  in the client's or an exception's `repr`.
- Redirects are not followed, and an id can never turn a request into a different endpoint.
- Webhook verification (`ligaxai.webhooks.verify`) is constant-time via the reference
  `standardwebhooks` implementation and rejects timestamps outside the tolerance window to
  prevent replay.
- Keep the key on the server. The FastAPI helpers exist so browsers call *your* backend, never
  the API directly: `run_stream_route` and `client_token_route` need the signed-in user from your
  session (or an explicit `allow_anonymous=True`), refuse cross-site requests, and never pass
  refusals about your own key on to the browser.

## Supply chain

- Dependencies are bounded in `pyproject.toml` and locked in `uv.lock`; CI fails if the lockfile
  is stale.
- Releases are built in CI and published with PyPI trusted publishing (OIDC) and PEP 740
  attestations — no long-lived PyPI token exists. The job that publishes runs no project code: it
  only uploads the files the build job produced.
- Workflow actions are pinned to commit SHAs.
