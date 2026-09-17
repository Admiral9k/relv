"""Search backends: Tavily + Exa. Plain HTTP, BYO keys from env.

Two arms:
  resolve   — name/URL resolution (default Tavily): "what is this app/page?"
  adjacency — semantic aspect queries (default Exa)

Search results are structured dicts:
  {"name": str, "url": str, "snippet": str, "source": "tavily|exa", "query": str}
"""

from __future__ import annotations

import os

import httpx

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _tavily_search(query: str, n: int) -> list:
    key = os.environ["TAVILY_API_KEY"]
    r = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "query": query,
            "max_results": n,
            "search_depth": "advanced",
            "include_answer": False,
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return [
        {"name": (h.get("title") or "")[:200], "url": h.get("url", ""), "snippet": (h.get("content") or "")[:1500], "source": "tavily", "query": query}
        for h in r.json().get("results", [])
    ]


def _exa_search(query: str, n: int) -> list:
    key = os.environ["EXA_API_KEY"]
    r = httpx.post(
        "https://api.exa.ai/search",
        headers={"x-api-key": key},
        json={
            "query": query,
            "numResults": n,
            "type": "neural",
            "contents": {"text": {"maxCharacters": 1500}},
        },
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for h in r.json().get("results", []):
        text = (h.get("text") or h.get("summary") or "")
        out.append(
            {
                "name": (h.get("title") or "")[:200],
                "url": h.get("url", ""),
                "snippet": text[:1500],
                "source": "exa",
                "query": query,
            }
        )
    return out


def search(query: str, n: int, backend: str) -> list:
    """Run one search on the named backend. Raises RuntimeError on missing key."""
    if backend == "tavily":
        if not os.environ.get("TAVILY_API_KEY"):
            raise RuntimeError("TAVILY_API_KEY not set")
        return _tavily_search(query, n)
    if backend == "exa":
        if not os.environ.get("EXA_API_KEY"):
            raise RuntimeError("EXA_API_KEY not set")
        return _exa_search(query, n)
    raise ValueError(f"unknown backend {backend!r}")
