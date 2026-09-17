# relv architecture

## What relv is

A profile-grounded relevance triage + adjacency miner for the tool/article firehose.

- **Input:** a URL, an app name, or pasted text.
- **Against:** the user's *declared* `profile.md` — who they are, what they run, what they reject. Authored, not surveilled.
- **Output:** a verdict (PRODUCT grab / ASPECT grab / neither + why), a set of 3–5 adjacent finds (same underlying aspect, different domain/angle, relevant to the profile), and optionally an ingest-ready markdown file.

## v1 scope (locked 2026-09-17)

- CLI only: `relv <url|name|text> [--emit-md]`
- Python, packaged with `uv` / `pyproject.toml`
- BYO keys, no embedded anything:
  - Model endpoint: any OpenAI-compatible API via OpenRouter (config: base URL + model + key)
  - Search backend: Tavily default, Exa supported (adjacency arm may default to Exa pending spike head-to-head)
- Ships: default `profile.md`, a generator prompt (paste into your agent to author your own profile), `examples/golden/` fixtures
- Single model verdict; output schema reserves the multi-model pop-out

## Pipeline

```
fetch → extract → verdict → adjacency → emit
```

Each stage: structured in → structured out. All model calls go through one adapter.

## Hard design constraints

**Violating either of these turns the eventual multi-model version into a ground-up rebuild. They are not style preferences.**

1. **The verdict is data, not prose.** The verdict stage returns JSON:

```json
{
  "grabs": [{"type": "product|aspect|none", "what": "...", "why": "..."}],
  "models": [{"model": "<id>", "verdict": "product|aspect|none", "why": "..."}],
  "confidence": null
}
```

In v1 the `models` array holds exactly one entry. Multi-model later = run the same call N times, append entries, add a merge step. The array is the only reservation needed and costs nothing today.

2. **One adapter file.** `complete(system_prompt, user_payload) -> raw`, OpenAI-compatible + base URL. Pipeline stages talk to the adapter, never to an API. No API endpoints/keys/response-parsing outside adapter.py; prompts live in their stage modules.

## Deferred (do not build in v1)

- Browser extension / floating overlay
- Multi-model panel mode (incl. cross-model reasoning — that changes pipeline topology; even then, stages survive, a stage gets inserted)
- Living/adaptive profile (feedback drift machine)
- Confidence scoring (dropped — humans decide; model disagreement is the future answer, not a synthetic number)

## Attribution

Concept origin: Devon Steele, 2026-09-16. Concept capture: `_wiki/concepts/relevator-concept.md` (private).
