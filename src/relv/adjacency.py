"""Adjacency stage + find-URL validation (the spike weakness v1 must fix).

adjacency_search: run the aspect-shaped queries on the configured backend.
adjacency_synth:   one synthesis call per query-set: raw results -> 3-5 finds.
validate_find_urls: check each find's URL plausibly matches its name; for
  mismatches, re-resolve the product's own URL via the resolve backend and
  swap it in; otherwise flag. Mismatches are NEVER silently dropped.
"""

from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

from .adapter import structured_complete
from .config import Config
from .search import search

SYNTH_SYSTEM = """\
You are the adjacency stage of a relevance tool. The user has a declared profile \
and has just triaged one tool/article. You receive aspect-shaped search results \
(queries hunt the MECHANISM, not the category). Select the 3-5 BEST adjacent \
finds: things that share an underlying mechanism with the triaged content but \
come from a DIFFERENT domain or angle, and are relevant to the profile.

Rules:
- Use ONLY the search results provided for URLs — never invent a URL.
- Discard marketing listicles, press-release noise, and major-brand blog spam \
(sludge). Show your filtering work in sludge_check.
- Each find: name, url, what_it_is, different_angle (which mechanism it shares \
and how its angle differs), why_relevant_to_profile (grounded in the profile's \
named projects/constraints).

Reply with ONLY a JSON object:
{"finds": [{"name": "...", "url": "...", "what_it_is": "...", "different_angle": "...", "why_relevant_to_profile": "..."}], "sludge_check": "..."}
"""

_NOISE_DOMAINS = ("businessinsider.com", "prnewswire.com", "globenewswire.com", "techcrunch.com", "venturebeat.com")


def adjacency_search(queries: list, cfg: Config, backend: str, n_results: int) -> list:
    """Run each aspect query; return deduped raw results (url-unique, keeps first).

    Returns [] when every query fails — the caller (cli) degrades gracefully
    instead of crashing the run after the verdict (the paid part) succeeded.
    """
    all_res = []
    seen = set()
    for q in queries:
        try:
            for r in search(q, n_results, backend):
                if r["url"] not in seen:
                    seen.add(r["url"])
                    all_res.append(r)
        except RuntimeError as e:
            print(f"[adjacency] query {q!r} failed: {e}", file=sys.stderr, flush=True)
    if not all_res:
        print("[adjacency] all search queries failed or returned nothing — degrading", file=sys.stderr, flush=True)
    return all_res


def adjacency_synth(queries: list, results: list, profile: str, summary: str, cfg: Config) -> dict:
    """Synthesize raw results into 3-5 profile-grounded finds."""
    payload = f"""# Profile (declared by the user)

{profile}

# Triage summary of the original content

{summary}

# Aspect-shaped search queries run
{json_list(queries)}

# Search results (use ONLY these URLs)
"""
    for r in results[:40]:
        payload += f"--- {r['name']} ({r['url']}) [query: {r['query']}]\n{r['snippet'][:600]}\n\n"
    out = structured_complete(SYNTH_SYSTEM, payload, cfg, model=cfg.synthesis_model)
    out.setdefault("finds", [])
    out.setdefault("sludge_check", "")
    return out


def json_list(items: list) -> str:
    import json

    return json.dumps(items)


def _tokenize(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _plausible(name: str, domain: str) -> bool:
    """Does this domain plausibly belong to this product name?

    Handles squished domains (fieldsnotesai.com ~ 'FieldNote AI'): checks
    token overlap, and prefix/suffix containment against the domain with
    separators removed.
    """
    name_tokens = {t for t in _tokenize(name) if len(t) > 3}
    d = domain.replace(".", " ").replace("-", " ")
    domain_tokens = _tokenize(d)
    if name_tokens & domain_tokens:
        return True
    squished = domain.replace("-", "").replace(".", "")
    for t in name_tokens:
        if t in squished or t[:5] in squished:
            return True
    return False


def validate_find_urls(findings: dict, cfg: Config, resolve_backend: str) -> dict:
    """Validate each find's URL plausibly matches its name.

    A find's URL is 'plausible' if its domain contains or shares a significant
    token with the find name (e.g. 'FieldNote AI' -> fieldsnotesai.com). For
    implausible URLs (news/article domains), re-resolve via the resolve backend;
    if a better URL is found, swap and mark url_status='re_resolved'; if not,
    keep the original and mark url_status='flagged'. Known press domains are
    always treated as implausible.
    """
    for f in findings.get("finds", []):
        status = _check_one(f, cfg, resolve_backend)
        f["url_status"] = status
    return findings


def _check_one(find: dict, cfg: Config, resolve_backend: str) -> str:
    url = (find.get("url") or "").strip()
    name = (find.get("name") or "").strip()
    if not url:
        return "flagged"
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    if any(domain.endswith(d) for d in _NOISE_DOMAINS):
        return _re_resolve(find, domain, cfg, resolve_backend)
    if _plausible(name, domain):
        return "ok"
    return _re_resolve(find, domain, cfg, resolve_backend)


def _re_resolve(find: dict, bad_domain: str, cfg: Config, resolve_backend: str) -> str:
    name = find.get("name", "")
    try:
        results = search(f'"{name}" official site', 3, resolve_backend)
    except RuntimeError:
        return "flagged"
    for r in results:
        d = urlparse(r["url"]).netloc.lower().removeprefix("www.")
        if any(d.endswith(x) for x in _NOISE_DOMAINS):
            continue
        if _plausible(name, d):
            find["original_url"] = find.get("url", "")
            find["url"] = r["url"]
            return "re_resolved"
    return "flagged"


def render_adjacency(adj: dict) -> str:
    lines = [f"sludge_check: {adj.get('sludge_check', '')}", "", "Adjacent finds:"]
    for f in adj.get("finds", []):
        lines.append(f"  - {f.get('name')} — {f.get('url')}  [{f.get('url_status', 'ok')}]")
        lines.append(f"    what: {f.get('what_it_is', '')}")
        lines.append(f"    angle: {f.get('different_angle', '')}")
        lines.append(f"    why: {f.get('why_relevant_to_profile', '')}")
    return "\n".join(lines)
