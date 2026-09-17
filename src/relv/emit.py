"""Emit stage: render the pipeline output — JSON verdict + adjacency, and
optional ingest-ready markdown (--emit-md).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def build_output(verdict: dict, adjacency: dict, meta: dict) -> dict:
    """Assemble the final structured output."""
    return {
        "verdict": verdict,
        "adjacency": adjacency,
        "_meta": meta,
    }


def slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "relv").lower()).strip("-")
    return s[:60] or "relv"


def emit_md(out: dict, emit_dir: str) -> str:
    """Write an ingest-ready markdown file. Returns its path."""
    v = out["verdict"]
    adj = out["adjacency"]
    meta = out.get("_meta", {})
    top = v.get("content_summary", "")[:80] or meta.get("input", "relv")
    lines = [
        f"# relv triage: {meta.get('input', '')}",
        "",
        f"- **Verdict:** {[g['type'] for g in v.get('grabs', [])] or 'none'}"
        f" (model: {meta.get('model', '')}, depth: {meta.get('depth', '')},"
        f" backends: {meta.get('backends', '')})",
        f"- **When:** {meta.get('when', '')}",
        f"- **Source:** {meta.get('source_desc', '')}",
        "",
        "## Summary",
        "",
        v.get("content_summary", ""),
        "",
        "## Grabs",
        "",
    ]
    for g in v.get("grabs", []):
        lines += [f"- **[{g.get('type', '?').upper()}] {g.get('what', '')}**", f"  - {g.get('why', '')}", ""]
    lines += ["## Aspects", ""]
    lines += [f"- {a}" for a in v.get("aspects", [])]
    lines += ["", "## Adjacent finds", "", f"_sludge check: {adj.get('sludge_check', '')}_", ""]
    for f in adj.get("finds", []):
        lines += [
            f"### {f.get('name', '')}",
            "",
            f"<{f.get('url', '')}>",
            "",
            f"- **What:** {f.get('what_it_is', '')}",
            f"- **Different angle:** {f.get('different_angle', '')}",
            f"- **Why relevant:** {f.get('why_relevant_to_profile', '')}",
            "",
        ]
    d = Path(emit_dir)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = d / f"{stamp}-{slugify(top)}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def render_stdout(out: dict) -> str:
    """Full human-readable rendering for terminal use."""
    v, adj, meta = out["verdict"], out["adjacency"], out.get("_meta", {})
    lines = ["=" * 60, f"relv — {meta.get('input', '')}", "=" * 60, ""]
    lines += [v.get("content_summary", ""), "", "GRABS:"]
    for g in v.get("grabs", []):
        lines += [f"  [{g.get('type', '?').upper()}] {g.get('what', '')}", f"      {g.get('why', '')}", ""]
    lines += ["ASPECTS:"] + [f"  - {a}" for a in v.get("aspects", [])] + [""]
    lines += ["ADJACENT FINDS:", f"  sludge_check: {adj.get('sludge_check', '')}"]
    for f in adj.get("finds", []):
        lines += [
            f"  - {f.get('name')}  <{f.get('url')}>  [{f.get('url_status', 'ok')}]",
            f"      what:  {f.get('what_it_is', '')}",
            f"      angle: {f.get('different_angle', '')}",
            f"      why:   {f.get('why_relevant_to_profile', '')}",
        ]
    if meta.get("degradation_notes"):
        lines += ["", "NOTES: " + "; ".join(meta["degradation_notes"])]
    if meta.get("flagged_urls"):
        lines += ["FLAGGED FIND URLS (name/url mismatch, unresolved):"] + [f"  - {u}" for u in meta["flagged_urls"]]
    lines += ["", "verdict-as-data (models): " + json.dumps(v.get("models", []))]
    return "\n".join(lines)
