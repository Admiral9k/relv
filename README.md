# relv

**Relevator** — profile-grounded triage + adjacency mining for the AI tool firehose.

You paste a URL, an app name, or text. relv checks it against *your* declared profile and answers:

1. **Direct relevance** — PRODUCT grab, ASPECT grab, or neither, each with the why.
2. **Adjacent relevance** — even when nothing's worth absorbing, extract the underlying *aspects* and search one layer out: who else uses that idea, differently, in a domain you should care about?
3. **Emit** — one flag produces an ingest-ready markdown file your agent already knows how to absorb.

The point is not another feed. The point is that the verdict lands in *your existing workflow* — your agent's ingest loop — instead of another open tab you'll never return to.

**Status: `WIP`** — building. See `docs/architecture.md` for the design constraints.

## Design constraints (hard rules)

1. **The verdict is data, not prose.** Every pipeline stage takes structured input and returns structured output (`fetch → extract → verdict → adjacency → emit`). The verdict stage returns JSON; the `models` array always holds exactly one entry in v1 — that array is the reservation that makes multi-model an additive change later, not a rebuild.
2. **One adapter file.** All model calls go through a single `complete(system_prompt, user_payload) -> raw` adapter (OpenAI-compatible + base URL). Pipeline stages talk to the adapter, never to an API. No model names, prompt strings, or response parsing in the pipeline body.

## License

MIT — see [LICENSE](LICENSE).
