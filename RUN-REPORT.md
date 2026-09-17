# relv v1 — run report (plain English)

Written for Devon, 2026-09-17. Companion forensic log: `process-log.md`.

## What got built

relv is a research tool that takes a thing — a web address, a bare product
name, or a pasted description — and answers one question in depth: *is this
thing worth the user's time, and if not, what should they look at instead?*

You feed it, say, "Linear" and it goes off and does the whole job a careful
human researcher would: it reads the actual page (not just the search
summary), judges it against a written profile of what the user likes and
rejects, explains its verdict in plain English, then goes hunting for
alternatives that share the *mechanism* of the original but done in a way
the user would actually accept — local, open, composable tools instead of
paid web services. Every alternative comes with a working link and a
reason.

The whole thing runs from one terminal command. Nothing is published; it's
a private tool on a private repo.

## What each test showed

**Unit tests (19).** These check the machinery without touching the
network: how it classifies your input (address vs name vs description),
how it validates that the "adjacent find" links it reports are real and
match what they claim to be, how it falls back when one search provider is
down, how it saves output. All 19 pass.

**Live end-to-end tests (2, real keys, real network).**
- Judging a real page against the profile: the answer came back in the
  agreed shape — verdict, reasoning, confidence honestly marked as
  "not given" rather than made up.
- Full pipeline on goblin.tools (fetch → judge → search for neighbors →
  validate their links → write up): completed and passed.

**Live runs of the three input styles (the transcript is in
`evidence/run-transcript-2026-09-17.txt`):**
- *Bare name* — "Linear": correctly decided Linear itself is a pass
  (hosted, per-seat, nothing to inspect) but extracted what's interesting
  about it (its triage-inbox idea) and found five genuinely fitting
  alternatives: a local-first issue tracker an agent can drive, issue
  tracking built into Git itself, a scoring writeup for triaging notes,
  an "accept loosely at the door, validate on promotion" pattern, and a
  keyboard-driven terminal task manager. It also flagged three links it
  couldn't fully verify — on purpose, visibly, rather than silently
  presenting them as solid.
- *Pasted text* — a one-line description of Goblin Tools with no link:
  it understood the description, judged the *mechanism* (breaking messy
  tasks into structured steps) as directly portable, and found real
  adjacent tools including a Unix-y single-purpose agent runner and a
  local markdown-to-knowledge-graph pipeline.

**Key-leak scan before committing.** Every file was searched for all three
API key patterns (OpenRouter, Tavily, Exa), plus the literal key values
themselves. Zero hits anywhere in the repo. Keys live only in an
environment file outside the repo, which is in .gitignore-land and was
never touched by git.

## What went wrong and how it was handled

- **First test run: 4 failures.** Two were bugs in the tests themselves;
  two were real bugs in the code — one where a setting was being read the
  wrong way, and one where the link-matcher was too strict about matching
  names to domains (it didn't understand that "Some Product" could be
  someproduct.io). All four were fixed the same turn; no test that had
  been passing broke as a result (that's the "fix-bleed" metric: 0).
- **Live runs kept failing with a weird "Illegal header value" error.**
  Root cause turned out to be embarrassing and simple: the file holding
  the API keys had Windows-style line endings, so every key carried an
  invisible carriage-return at the end and the server rejected it as a
  malformed credential. The tool retried politely (3 times, with
  56–81 second back-offs, exactly as designed) before failing cleanly —
  so the failure-handling code got a live test out of it. Fixed the file,
  all tests passed.
- **One test command hit a time limit** while capturing the live
  transcript and got cut off mid-run. Re-ran just that piece; the
  transcript contains both complete runs.

## Honest gaps

- The retry path was only tested "by accident" (the key bug exercised it
  live); no dedicated simulated-stall test exists for a provider actually
  rate-limiting or dying mid-run, and only single-backend-down has a
  unit test.
- Link validation flags suspicious finds, but it can't *repair* them
  (some "re_resolved" finds still land on an imperfect page). The
  original URL is kept so a human can check.
- The confidence field is always "null" by design — the model doesn't
  get to invent a number. That's honest, but it means the report never
  tells you *how* sure the verdict is.
- Everything was validated on exactly two live subjects (Linear,
  Goblin Tools) plus the two test subjects (goblin.tools, a fixture).
  A wider diet of inputs would shake out edge cases.
- Cost: fine (fractions of a cent per run), but no billing guard —
  nothing stops a runaway script from hammering the APIs.

## Where things stand

All code, tests, docs, evidence, and this report are committed to the
private repo on `main`. The test suite was re-run after committing and
is green. Nothing is published anywhere.
