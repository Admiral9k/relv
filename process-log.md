# relv v1 process log

Build: 2026-09-17, VPS Hermes (E+). Forensics for the verifier; plain-English
companion is RUN-REPORT.md.

## Turn-by-turn

### Turn 1 — scaffold (build)
- Read repo state: `docs/architecture.md`, `examples/golden/` (4 fixtures +
  SPIKE-REPORT), README, .gitignore. Working tree clean at spike commit d7c19fe.
- Keys located in `~/.bashrc` (env-only per brief); uv 0.12.9 present.
- Wrote: `pyproject.toml` (uv/hatchling, `relv` script), `src/relv/` package:
  `config.py`, `adapter.py`, `search.py`, `fetch.py`, `verdict.py`,
  `adjacency.py`, `emit.py`, `cli.py`, `default_profile.md`,
  `profile-generator-prompt.md`; `tests/test_relv.py`.
- Design decisions logged: depth knobs (picky=2 queries/6 results + strong-tier
  synthesis, standard=3/12, broad=4/20); adapter retries 4× with 30–90s jitter
  on 429/5xx; graceful single-backend degradation with user-facing notes;
  find-URL validation statuses ok/re_resolved/flagged with original_url kept.
- Test run 1: 15 pass, 2 skip (live), 4 FAIL:
  - 2× missing `monkeypatch` arg in test signatures (test bugs)
  - `Config.backends` read as class attr — dataclass field w/ default_factory
    has no class attribute (real bug in load_config)
  - re_resolve test: URL matcher too strict for squished domains
    (someproduct.io vs "Some Product") — real bug in v1's own DoD feature
- Fix 1: moved `init` handling before argparse; `_DEFAULT_BACKENDS` module
  constant; monkeypatch args; rewrote `_plausible()` matcher (token overlap +
  squished-domain containment). Also: a write_file/patch mangling corrupted
  config.py line 47 — caught by the linter before any test run, fixed
  immediately. (fix-bleed count: 0 — no previously-passing test broke.)
- Test run 2 (post-fix): **19 pass, 2 skip**. Unit layer green.
- README rewritten to DoD spec (install, usage, constraints, config, doctrine,
  URL-validation, tests). .gitignore extended (goal-brief.md, relv-emissions/).

### Turn 2 — live integration (build)
- `set -a; source ~/.bashrc` needed — keys are in .bashrc, not inherited by
  pytest otherwise (the earlier "2 skipped" in a sourced shell was because the
  first attempt ran without set -a... actually it ran via `source ~/.bashrc`
  without set -a; export lines do export on source — real cause: keys ARE in
  .bashrc but `source` in the tool's non-interactive shell skipped them? No:
  `source ~/.bashrc` + echo showed empty. Diagnosis: .bashrc's interactive
  guard at the top? Verified NOT the case — grep showed the export lines at
  the tail. `set -a` before source fixed it. Note: the guard `.bashrc` early-
  return for non-interactive shells was NOT present, so the earlier failure
  remains unexplained; `set -a; source` works and is what `relv` docs should
  tell users.)
- Live verdict-schema test: PASS (golden-schema verdict, one-entry models
  array, confidence null, 2+ adjacency queries).
- Live end-to-end URL test: running (goblin.tools through full pipeline).

## Metrics so far
(see Final metrics below — superseded at wrap-up)

## Final metrics (session 3, wrap-up)
- Turns/sessions: 3 total — (1) scaffold+unit fixes, (2) live integration
  + three input styles, (3) this wrap-up (metrics, key scan, commit, push,
  post-push test rerun).
- Fix-turns: 0 dedicated (all fixes folded into the turn that found them).
- Fix-bleed events (a fix broke a previously-passing test): 0 across all
  3 sessions.
- Scope branches: 0.
- Stalls: 1 accidental live exercise — the CRLF key bug (below) drove the
  adapter's retry path for real: 3 retries with 56–81s backoff before a
  clean failure, exactly as designed. No dedicated simulated-stall test
  (known gap, noted in RUN-REPORT).
- CRLF bug story: live runs failed with "Illegal header value" — ~/.bashrc
  had Windows CRLF line endings, so every exported key carried a trailing
  carriage-return. Rewriting the file with LF endings fixed all live runs.
  Cost: several dead turns diagnosing; payoff: retry/degradation path got a
  live test it otherwise lacked.
- Tests: 19 unit pass + 2 live E2E pass; suite green offline (live tests
  skip without keys).

## Usage notes
- Keys: `set -a; source ~/.bashrc; set +a` before live runs.
- Live tests auto-skip without keys; suite is green offline (CI-friendly).
- Cost: each run ≈ 2 model calls (extract, verdict) + 1 synthesis call +
  3–4 searches. At flash pricing this is fractions of a cent.
