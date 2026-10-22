# Status

Last updated: 2026-10-22

## Plans

| Plan                      | Status      | Notes                                                                  |
| ------------------------- | ----------- | ---------------------------------------------------------------------- |
| Base template skeleton    | implemented | branch `project-base-setup`; gates green locally (see SUMMARY)          |
| Bootstrap to a real SDK   | implemented | `ligaxai` / `LigaX` / `LIGAX_*`                                         |
| Spec pin + codegen        | implemented | `public-api-spec-v0.1.0` copied from the platform repo; drift-checked   |
| Agent API v0.1 resources  | implemented | branch `feat/agent-api-v0.1` (local, unpushed); gates green             |
| First PyPI release        | planned     | needs pending trusted publisher + `pypi` environment on GitHub          |

## Team activity

- 2026-10-22 — Agent API v0.1 on `feat/agent-api-v0.1`: runs (create/wait/stream/get/
  events/follow_events/cancel/resolve_interrupt), conversations, profiles, keys, usage;
  `RunStream` + UTF-16 `TextAssembler`; `run_stream_route`; 163 tests, 96 % coverage.

- 2026-10-22 — template scaffolded: tooling, core client, streaming + errors, tests +
  conformance, docs + CI. All gates pass on Python 3.11 locally.

## Known gaps

- Not yet exercised against a live platform: every test is mocked. First live check:
  `keys.self()`, then `runs.wait` and `runs.stream` against the dev platform.
- `sync_spec.py` still expects a GitHub release of a spec repo; v0.1.0 was copied by hand
  from `ligax-enterprise/docs/public-api/spec/openapi.json`.
- Enum fields (`run.status`, `profile.type`, …) are `Literal`s: a value the server adds
  later fails validation until the spec and SDK are bumped.
- 409 is still retried by the shared policy; none of the API's 409s are transient.

- No `with_raw_response` / `with_streaming_response` accessors yet (in the research brief,
  deferred until a real resource needs them).
- `sync_spec.py` is untested by design (network); exercise it manually when the spec repo
  exists.
- CI matrix has not run yet — no commits are pushed.
