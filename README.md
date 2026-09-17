# relv

**Relevator** — profile-grounded triage + adjacency mining for the AI tool firehose.

You paste a URL, an app name, or text. relv checks it against *your* declared profile and answers:

1. **Direct relevance** — PRODUCT grab, ASPECT grab, or neither, each with the why.
2. **Adjacent relevance** — even when nothing's worth absorbing, extract the underlying *aspects* and search one layer out: who else uses that mechanism, differently, in a domain you should care about?
3. **Emit** — `--emit-md` produces an ingest-ready markdown file your agent already knows how to absorb.

The point is not another feed. The point is that the verdict lands in *your existing workflow* — your agent's ingest loop — instead of another open tab you'll never return to.

## Install (uv)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```
git clone <this-private-repo> && cd relv
uv sync
uv run relv --help
```

## Usage

```
# triage a URL
uv run relv https://goblin.tools --emit-md

# triage a bare app name (search-backend path)
uv run relv "Jev by Typesafe"

# triage pasted text (quote it)
uv run relv "A new tool that does X ..." --emit-md

# full structured output as JSON
uv run relv https://example.com --json

# depth / model overrides
uv run relv https://example.com --depth picky
uv run relv https://example.com --model z-ai/glm-5.3
```

Setup: copy the default profile and edit it (or use the generator prompt below), optionally add a `config.yaml`:

```
cp src/relv/default_profile.md profile.md   # then edit to declare who YOU are
uv run relv init                            # writes a default config.yaml
```

Keys come from the environment (never from files in the repo):

```
export OPENROUTER_API_KEY=...   # model endpoint (or any OpenAI-compatible provider via config.yaml base_url)
export TAVILY_API_KEY=...       # search: resolve arm
export EXA_API_KEY=...          # search: adjacency arm
```

## The profile is the mechanism

relv's verdicts are only as sharp as the profile they're grounded against. The default `profile.md` ships as a starting point; `profile-generator-prompt.md` is a paste-into-your-agent prompt that interviews you and authors your own. Named projects > categories — the model grounds each verdict's "why" in what you actually run.

## Config knobs

`config.yaml` (see `relv init`):

- **`model:`** — your triage temperament. Default `z-ai/glm-5.3-flash` **leans adopt**; `z-ai/glm-5.3` **leans skip — steals patterns instead of recommending products**. Neither is wrong; pick the strictness you want. Any OpenAI-compatible model id works.
- **`depth: picky|standard|broad`** — standard = spike-validated defaults (3 aspect-queries, ~12 results/backend). picky synthesizes adjacency with the strong tier, runs fewer/sharper queries, costs more. broad runs more of everything. Default: standard.
- **`backends.resolve` / `backends.adjacency`** — Tavily (default for name/URL resolution) and Exa (default for adjacency — its neural search wins exactly where the product's novel feature lives: semantic "same mechanism, different domain" queries). **If only one key is present, relv degrades to single-backend and says so in the output** — designed behavior, not an error.

## Design constraints (hard rules)

1. **The verdict is data, not prose.** Every pipeline stage takes structured input and returns structured output (`fetch → extract → verdict → adjacency → emit`). The verdict stage returns JSON; the `models` array always holds exactly one entry in v1 — that array is the reservation that makes multi-model an additive change later, not a rebuild.
2. **One adapter file.** All model calls go through a single `complete(system_prompt, user_payload) -> raw` adapter (OpenAI-compatible + base URL). Pipeline stages talk to the adapter, never to an API. No model names, prompt strings, or response parsing in the pipeline body.

See `docs/architecture.md` for the full spec.

## Adjacency doctrine: mechanisms, not categories

The adjacency queries are deliberately **aspect-shaped, not category-shaped**: "what shares my mechanism," not "what's in my category." This surfaces obscure and small tools over enterprise listicles, and the per-find `sludge_check` reasoning filters major-brand press noise. relv finds what shares your MECHANISM, not what shares your CATEGORY. (A category mode is a parked v2 idea.)

The per-find JSON reasoning (`why`, `different_angle`, `sludge_check`) is product output, not debug — it's always visible in `--json` and in the emitted markdown.

## Find-URL validation

v1 fixes a known spike weakness: finds could attach the *article page* URL instead of the product's own URL. Before emitting, relv validates each find's URL against its name; mismatches are re-resolved via the resolve backend and marked `url_status: re_resolved`, or flagged honestly (`url_status: flagged`) when no better URL exists. Flagged finds are listed in the output — never silently dropped.

## Tests

```
uv run pytest tests/ -q     # unit layer: no keys, no network
# with keys exported: also runs 2 live integration tests (skipped otherwise)
```

`examples/golden/` contains the spike-validated quality bar this build is measured against.

## License

MIT — see [LICENSE](LICENSE).
