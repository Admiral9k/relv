# Profile generator prompt

Paste this whole prompt into your AI agent, fill in the bracketed parts (or
let the agent interview you), and save the result as `profile.md` next to your
relv `config.yaml`. relv's verdicts are only as good as the profile they are
grounded against — a sharp profile produces sharp verdicts.

---

I want you to write my personal relevance profile for a triage tool. Interview
me with a few short questions if you need to, then produce the profile.

The profile must have these sections, in this order:

```
# Profile

## Who I am
2-4 sentences: what I do, how I work, what my attention budget is like.

## What I run
Bullet list of the concrete systems, projects, tools, and workflows I
actually operate day to day. Name them — named projects give the triage model
hooks to ground verdicts in. (e.g. "a welding-industry inspection app called
X", "an Obsidian markdown vault with an ingest queue", "local agents for
research").

## What I value
Bullets: patterns I consistently reach for — small tools over platforms,
self-hosting, BYO-key, mechanisms over products, etc.

## What I reject
Bullets: categories of noise I never want recommended — marketing SaaS,
listicles, subscription sprawl, vendor lock-in. Be opinionated; rejections do
as much work as preferences in triage.
```

Rules:
- Write in first person ("I run...", "I reject...").
- Concrete and named over abstract. "My ADHD-support app for my son" grounds
  verdicts; "productivity tools" does not.
- Keep it under ~300 words. The profile is read on every triage call.
- Do not invent projects or preferences I didn't state or imply.

---

Tips for a good profile:

- Named projects > categories. The triage model grounds each verdict's "why"
  in what you actually run — give it names to grab.
- Rejections are half the tool. Anything you list under "What I reject" gets
  used as an explicit sludge filter on search results.
- Revisit the profile when your stack changes; it is authored, not surveilled.
