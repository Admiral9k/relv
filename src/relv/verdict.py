"""Verdict stage: profile-grounded triage. Verdict-as-data (constraint #1).

Returns the golden-schema JSON:
  grabs, aspects, adjacency_queries (verdict-local)
  models: exactly one entry — the multi-model reservation.
"""

from __future__ import annotations

import json

from .adapter import structured_complete
from .config import Config

VERDICT_SYSTEM = """\
You are the triage heart of a relevance tool called relv. The user has declared \
a profile: who they are, what they run, what they reject. You receive an \
extraction of ONE tool/article and must judge it against that profile.

Produce:
1. content_summary — 2-4 dense sentences on what the thing actually is (mechanism, not marketing).
2. grabs — what is worth taking. Each: type "product" (adopt the thing itself), \
"aspect" (steal the underlying mechanism/pattern for their own work), or "none" \
(skip — but if there are stealable patterns, say so in the why). Ground every \
"why" in the profile's named projects, constraints, or rejections. If nothing \
fits, grabs is exactly [{"type": "none", "what": "...", "why": "..."}].
3. aspects — the underlying mechanisms this thing demonstrates, phrased as \
transferable ideas ("X: mechanism, not product name").
4. adjacency_queries — 2-4 natural-language search queries shaped like ASPECTS \
("what shares my mechanism"), NOT categories ("what else is in this category"). \
Each query hunts a different aspect in a different domain.

The sludge test: reject marketing fluff, enterprise listicles, and major-brand \
press noise; a find earns its place by sharing a MECHANISM the user could port.

Reply with ONLY a JSON object:
{"content_summary": "...", "grabs": [{"type": "product|aspect|none", "what": "...", "why": "..."}], "aspects": ["..."], "adjacency_queries": ["..."]}
"""


def verdict(extraction: dict, profile: str, cfg: Config, source_desc: str) -> dict:
    """Run the verdict stage. Returns the golden-schema verdict dict."""
    user_payload = f"""# Profile (declared by the user)

{profile}

# Content to triage ({source_desc})

Title: {extraction.get('title', '')}

{extraction.get('content', '')}

Judge this content against the profile. Output the JSON."""
    v = structured_complete(VERDICT_SYSTEM, user_payload, cfg)
    for k, default in (
        ("content_summary", ""),
        ("grabs", []),
        ("aspects", []),
        ("adjacency_queries", []),
    ):
        v.setdefault(k, default)
    # Verdict-as-data: attach the models array (exactly one entry in v1).
    top_grab = next((g.get("type", "none") for g in v["grabs"] if g.get("type") != "none"), "none")
    v["models"] = [
        {
            "model": cfg.model,
            "verdict": top_grab,
            "why": "; ".join(g.get("why", "") for g in v["grabs"][:2]),
        }
    ]
    v["confidence"] = None
    return v


def render_verdict(v: dict) -> str:
    """Human-readable rendering of a verdict dict (for stdout/emit)."""
    lines = [f"Summary: {v.get('content_summary', '')}", "", "Grabs:"]
    for g in v.get("grabs", []):
        lines.append(f"  [{g.get('type', '?').upper()}] {g.get('what', '')}")
        lines.append(f"        {g.get('why', '')}")
    lines += ["", "Aspects:"]
    for a in v.get("aspects", []):
        lines.append(f"  - {a}")
    lines += ["", f"Verdict (models): {json.dumps(v.get('models', []))}"]
    return "\n".join(lines)
