# Status

Last updated: 2026-10-22

## Plans

| Plan                      | Status      | Notes                                                                  |
| ------------------------- | ----------- | ---------------------------------------------------------------------- |
| Base template skeleton    | implemented | branch `project-base-setup`; gates green locally (see SUMMARY)          |
| Bootstrap to a real SDK   | planned     | run `scripts/bootstrap.sh`, then SPEC_VERSION + `make sync-spec`        |
| First spec sync + codegen | planned     | blocked on the spec repo publishing a `spec-v*` release                 |
| Resources beyond `health` | planned     | one file per namespace next to `resources/health.py`, sync + async      |
| First PyPI release        | planned     | needs pending trusted publisher + `pypi` environment on GitHub          |

## Team activity

- 2026-10-22 — template scaffolded: tooling, core client, streaming + errors, tests +
  conformance, docs + CI. All gates pass on Python 3.11 locally.

## Known gaps

- No `with_raw_response` / `with_streaming_response` accessors yet (in the research brief,
  deferred until a real resource needs them).
- `sync_spec.py` is untested by design (network); exercise it manually when the spec repo
  exists.
- CI matrix has not run yet — no commits are pushed.
