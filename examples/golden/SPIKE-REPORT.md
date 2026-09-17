# Spike 001: relv prompt quality — cheap vs strong (001a/001b)

**Question:** Does the verdict+adjacency prompt produce genuinely relevant, profile-grounded, non-sludge output — and at which intelligence tier?
**Date:** 2026-09-16/17 · 10 runs (4 inputs × 2 models + input d × 2 profiles) · throwaway harness `relv-spike/spike.py`

## Verdict: VALIDATED — both tiers clear the bar; cheap tier confirmed as v1 default

### Head-to-head: glm-5.3-flash (001a) vs glm-5.3 (001b)

| Dimension | 001a flash (cheap) | 001b strong |
|---|---|---|
| JSON compliance | 10/10 clean parses | 10/10 clean parses |
| Sludge resistance | Good — sludge_checks name real discards (rejected Copy.ai as "marketing-first lead-gen" on profile's stated rejections) | Excellent — pickiest judge in the field |
| Verdict discipline | Leans generous: 3 product-grabs in 8 runs | Leans strict: called Cursor AND Jev "none" for the product itself, stole patterns instead |
| Grounding in profile | Strong on all runs | Strong on all runs |
| Adjacency finds | 4–5 per run, distinct angles, few sludge URLs | 3–4 per run, tighter, more WeldDesk-specific ports |
| Latency | Fast | 1.5–2× slower per call |
| Cost | ~1/15 input price | premium but still cheap in absolute terms |

**Delta finding:** the tiers differ in *strictness*, not competence. Flash says "adopt"; strong says "skip the product, steal the pattern." Neither is wrong — but for a triage tool whose whole value is honest filtering, **the strong tier's strictness is closer to the product's spirit**, while flash's output is fully usable at 1/15 the price. v1 default = **flash**, with the config slot making the strong tier a one-line upgrade users can choose. Document both behaviors in the README as a feature, not a bug: "flash leans adopt, strong leans skip — pick your triage temperament."

### Backend head-to-head: Tavily vs Exa (adjacency arm)

| Dimension | Tavily | Exa |
|---|---|---|
| Raw result relevance to semantic "same aspect, different domain" queries | Often noisy; more press-release/marketing-list results | Noticeably better on semantic queries; more real products |
| After synthesis (both were synthesized by the same model) | Comparable find quality — the synthesis stage carried weak results | Slightly sharper, more product-shaped finds; both produced standout finds |
| Standout finds | Honeywell voice maintenance, Checklist Navigator (surgical), Elucidare | FieldNote AI, Epoch (MCP estimation tools), Inspekta |

**Backend verdict: Exa for the adjacency arm, Tavily for name-resolution/lookup.** Exa's neural search wins exactly where the product's novel feature lives (semantic "different angle" queries); Tavily is fine for the boring lookups and keeps free-tier headroom. Config supports both; defaults: adjacency=Exa, resolve=Tavily.

### Mechanism validation (input d, dual profile) — THE finding

Same input (goblin.tools), same model (glm-5.3), only the profile changed:

- **Default profile:** aspect-grabs framed for a generic agent-stack user (Compiler pattern, one-task-at-a-time UI).
- **Devon profile:** the SAME aspects emerged but grounded in named projects — and the strong tier issued the run's only **PRODUCT grab**: "Goblin Tools free web version — as an immediate daily tool for his son," with competitive-research reasoning (Warner's real usage = live roadmap signal for EMRALD). Adjacency finds went generic → FieldNote AI (WeldDesk companion-first port), Checklist Navigator (surgical checklists → CWI WPS-step adherence), Elucidare (EMRALD inbound-tone feature).

**The profile demonstrably steers both verdicts and adjacency.** Same content, same model, different declared lean → visibly different output quality and relevance. Profile-grounding is not decorative; it is the mechanism.

### What worked
- Verdict-as-data schema held across all 10 runs (zero prose-bleed escapes)
- sludge_check field is a keeper — it forces the model to show its filtering work
- "Use only the search results provided for URLs" prevented invented URLs in every run
- Aspect extraction is genuinely good at both tiers — the "different angle" instruction produces non-obvious domain ports (welding inspection → surgical checklists is a real insight)

### What didn't / surprises
- Exa fetch of some URLs returned thin content; Tavily resolve filled gaps — supports the two-backend default split
- Strong tier is 1.5–2× slower; at CLI scale that's fine, but batch/UI mode may want flash
- Flash gave Jev a product-grab the strong tier rejected — for borderline "free/cheap utility" items the tiers genuinely disagree (worth exposing model choice to users)

### Recommendation for the real build
- v1 default model: `z-ai/glm-5.3-flash`; README documents the strictness delta and the one-line switch
- Search defaults: resolve=Tavily, adjacency=Exa
- Golden examples: selected from these outputs (see `examples/golden/`)
- Prompts frozen as v1 starting point (they earned it); future prompt work goes through the repo's test suite, not vibes

## Golden examples selected (quality bar for the VPS run)

1. `d-goblin-tools` — Devon profile, glm-5.3 — the mechanism-validation showcase (product grab + WeldDesk/EMRALD-ported adjacency)
2. `c-app-name` — default profile, glm-5.3 — the name-only input path + the strictest triage (Jev: skip product, steal patterns)
3. `a-landing-page` — default profile, glm-5.3-flash — cheap-tier quality bar + marketing-page input type
4. `b-article-text` — default profile, glm-5.3-flash — raw-text input path, product grab (the vault clipper)
