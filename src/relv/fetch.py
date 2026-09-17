"""fetch + extract stages.

fetch(url)        -> {"url", "fetched_text"}  (structured in/out)
extract(text)     -> {"title", "content"}     (model call via adapter)

Input classification (url vs bare name vs pasted text) happens in cli.py —
this module owns only the fetch/extract mechanics.
"""

from __future__ import annotations

import re

import httpx

from .adapter import structured_complete
from .config import Config
from .search import search

_FETCH_TIMEOUT = httpx.Timeout(45.0, connect=15.0)

EXTRACT_SYSTEM = """\
You are the extraction stage of a relevance-triage pipeline. You receive raw \
web text (or search results) about one tool/article and must produce a clean, \
faithful extraction: what the thing IS, what it does, for whom, key mechanics. \
No evaluation, no opinions — that is the verdict stage's job. Reply with ONLY \
a JSON object:

{"title": "...", "content": "2-4 dense paragraphs summarizing what this is, its mechanism, and its notable features"}
"""


_SOCIAL_URL_RE = re.compile(r"^https?://(www\.)?(x\.com|twitter\.com)/", re.IGNORECASE)


def fetch_url(url: str, cfg: Config | None = None, backends: dict | None = None, notes: list | None = None) -> dict:
    """Fetch a URL's readable text. Falls back to Tavily extract when direct
    fetch is thin — same backend-key logic as the rest of the pipeline.

    Appends a degradation note to `notes` (if given) for every fallback and for
    social-platform inputs that needed search resolution.
    """
    notes = notes if notes is not None else []
    direct_ok = False
    text = ""
    try:
        r = httpx.get(url, follow_redirects=True, timeout=_FETCH_TIMEOUT, headers={"User-Agent": "Mozilla/5.0 (relv/0.1)"})
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "html" in ctype:
            text = _html_to_text(r.text)
        elif r.status_code == 200 and "text" in ctype:
            text = r.text
        direct_ok = len(text.strip()) >= 100
    except Exception:
        text = ""
    if len(text.strip()) < 300 and _tavily_available(backends):
        try:
            t = _tavily_extract(url)
            if t.strip():
                if not direct_ok:
                    notes.append("direct fetch failed; resolved via tavily extract")
                text = t
        except Exception:
            pass
    if len(text.strip()) < 100:
        raise RuntimeError(f"fetch: could not retrieve usable text from {url}")
    if _SOCIAL_URL_RE.match(url):
        notes.append(
            "X.com requires auth; resolved via search — paste text for best results"
        )
    return {"url": url, "fetched_text": text[:20000]}


def _tavily_available(backends: dict | None = None) -> bool:
    """Tavily extract fallback honors the same key logic as the search stages:
    only used when the tavily key is present (same env check as config.available_backends).
    """
    import os

    return bool(os.environ.get("TAVILY_API_KEY"))


def _tavily_extract(url: str) -> str:
    import os

    r = httpx.post(
        "https://api.tavily.com/extract",
        headers={"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"},
        json={"urls": [url]},
        timeout=_FETCH_TIMEOUT,
    )
    r.raise_for_status()
    res = r.json().get("results", [])
    return res[0].get("raw_content", "") if res else ""


_TAG_RE = re.compile(r"<(script|style|nav|header|footer|aside|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _html_to_text(html: str) -> str:
    html = _TAG_RE.sub(" ", html)
    html = _COMMENT_RE.sub(" ", html)
    text = _TAG_STRIP_RE.sub(" ", html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def resolve_name(name: str, cfg: Config, backend: str, n: int = 5) -> dict:
    """Bare app-name input: search for it, then return the top result set."""
    results = search(f"{name} app tool what is it", n, backend)
    if not results:
        raise RuntimeError(f"resolve: no search results for {name!r}")
    return {"url": "", "fetched_text": "", "search_results": results, "query": f"{name} app tool what is it"}


def extract(raw: dict, cfg: Config) -> dict:
    """Extract stage: model call over fetched text OR search results."""
    if raw.get("search_results"):
        payload = "Search results about a tool (bare-name input). Extract what the tool is.\n\n"
        for r in raw["search_results"][:8]:
            payload += f"--- {r['name']} ({r['url']})\n{r['snippet']}\n\n"
    else:
        payload = f"Raw web text from {raw['url']}:\n\n{raw['fetched_text']}"
    out = structured_complete(EXTRACT_SYSTEM, payload, cfg)
    out.setdefault("title", "")
    out.setdefault("content", "")
    return out
