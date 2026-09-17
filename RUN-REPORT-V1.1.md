# RUN REPORT — relv v1.1 fix session (2026-09-17)

**Where built:** VPS mini-run session `20260917_171909_0c62d5` (33-turn budget) wrote all seven fixes; hit the turn ceiling as an honest partial — code complete, unverified, uncommitted. The local middleman session completed verification, fixed two test-layer bugs, fixed one fix-bleed found in verification, ran the live evidence, and committed/pushed (`b3b94cb` fixtures → `862b111` v1.1).

## The seven launch-gating items — final status

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Profile-trap (init writes profile.md; fallback warns) | **DONE** | cli.py `_write_default_profile` + init output; `_load_profile` stderr warning; 4 unit tests |
| 2 | Dead depth knob (n_queries wired, depth→query-count mapping) | **DONE** | config.py `DEPTH_QUERIES` picky:2/standard:3/broad:5; verdict.py `{N_QUERIES}` token-replace; 2 tests |
| 3 | All-queries-fail → graceful degradation (REVISED item — see correction below) | **DONE** | adjacency.py returns [] + stderr notice; cli emits empty finds + reason + degradation_note; full-pipeline unit test (all stage bindings patched, zero real calls) |
| 4 | Degradation transparency (fetch fallbacks announced; X.com notice) | **DONE** | fetch.py takes cfg/backends/notes, logs Tavily-extract fallback; **live X-URL run verified**: degradation_notes = ["X.com requires auth; resolved via search — paste text for best results"] |
| 5 | Doc-vs-code prompt ruling (fix the DOC) | **DONE** | docs/architecture.md constraint #2 reworded: prompts live in stage modules |
| 6 | JSON parser brace bug (string-aware scanner) | **DONE** | adapter.py in_string/escape tracking; prose-wrapped + fenced tests with braces in strings |
| 7 | Hard-constraint test (exactly one models entry) | **DONE** | Keyless test parses goldens 005-009, asserts `len(models) == 1` |

Plus the small in-scope item: `_meta.input` cap raised 300 → 5000 chars (existing fixtures untouched, per brief).

## Correction to the original plan (recorded during the session)

Gate #3 was originally "long-form article → zero finds." That premise was wrong: a prior session's diagnostic script read top-level JSON keys instead of `d["adjacency"]` and reported zero finds that never existed. The on-disk artifact always showed 46 raw / 5 finds; three fresh article runs (exa/standard, tavily-degraded, picky/exa) all produced 5 finds. The surviving real bug — confirmed by the battery's run-1 hard error — was the RuntimeError crash when ALL adjacency queries fail transiently, killing the run after the paid verdict stage succeeded. Both audits' article "confirmations" were audits against misstated evidence; their query-shape mechanism analysis is an unvalidated hypothesis. The v1.1 plan note has been corrected. Dropped from gating: constrained query-writer, fallback re-search.

## Tests

- Baseline before fixes: 19 passed, 2 skipped.
- Final: **36 passed, 0 failed** (2 live-key tests ran live with real keys and passed).
- The degrade-path test needed three corrections in local verification (see fix-bleed below).

## Fix-bleed (logged, not hidden)

1. `[adjacency]` diagnostic prints went to **stdout** in the VPS code — corrupting `--json` output exactly in the degrade path the fix created. Fixed locally: routed to stderr. (The same class of bug as v1's X-URL silence: diagnostics must never sit in the data lane.)
2. The degrade-path unit test patched `relv.adapter.structured_complete`, but each stage holds its own import-time binding — the test was silently making REAL model/Tavily calls under a fake key. Fixed: patch each stage's binding (verdict/fetch/adjacency) + `relv.fetch.search`. Lesson: with per-stage imports, patch the binding the stage actually uses.

## Live evidence (all on 2026-09-17, keys from relv.env)

- `evidence/v11-spot-run.json` — fixture 006 input, healthy path: 5 finds, 3 queries (new depth wiring), exactly 1 models entry.
- `evidence/v11-xurl-run.json` — gate #4 live verification: X-URL resolved, fallback ANNOUNCED in degradation_notes, full verdict + 5 finds.
- `evidence/article-recharacterization-2026-09-17/` — three article re-runs (exa/standard, tavily-degraded, picky/exa), all 5 finds — the empirical basis for the gate #3 correction.

## Honest gaps / caveats

- The X.com notice fires for any x.com/twitter.com input that survives fetch — it does NOT fire when the whole run fails before then. Acceptable: the note's job is to improve the next run ("paste text"), and a failed run already tells the user it failed.
- The degrade path's `reason` is a fixed string; no per-query failure detail is exposed beyond stderr. Fine for v1.1; a v1.2 candidate if real-world backends flake often.
- v1.1 was verified on Windows locally; the VPS box has the same code but the suite was only run there pre-completion (33 passed, 1 failed at the time — that failure is the test-bug fixed above).

## Post-audit round (2026-09-17, after both-family spot-audit)

Both audits (llc GLM via Bot Chat + DeepSeek-v4 subagent) converged on the X-notice MAJOR; fixed in `4485fcc` (notice gated on `not direct_ok`, lie-pinning test replaced with two truthful-path tests). Second round, committed `e9a68fa`: emit_md + render_stdout now carry the degrade reason / degradation notes / flagged URLs (a degraded run no longer looks clean in emitted markdown); empty-adjacency-queries gets its own truthful message + test; `_tavily_available` docstring honest about scope. Final: **41 tests passed**, audit verdicts **publishable-with-fixes** with all blockers resolved. Fable's adapter `r.text` note is pre-existing (parked as v1.2 #11). Process note: the llc Bot Chat audit committed its own fix (`4485fcc`) despite a read-only brief — content verified correct and kept; constraint violation recorded for the llc lane.

## Fast-follow (v1.2 lane, untouched per brief)

init as argparse subcommand; YAML error handling; key guards; error sanitization; Exa-default-adjacency onboarding note; test-gap fills; xAI backend for X-URLs; `--emit-dir`; tagged releases. Plus new: per-skill usage logs (dreaming-loop candidate from the skillbox review, parked).
