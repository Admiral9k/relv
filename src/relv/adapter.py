"""The ONE adapter. All model calls go through complete().

Pipeline stages talk to this module, never to an API. Model names come from
config, prompt strings live here. OpenAI-compatible: base URL + model + key.

complete(system_prompt, user_payload) -> raw  (str)
structured_complete(...) -> parsed JSON      (thin wrapper; JSON parsing lives
HERE, not in the pipeline body, per docs/architecture.md constraint #2.)
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time

import httpx

from .config import Config

_TIMEOUT = httpx.Timeout(180.0, connect=30.0)


def _api_key(cfg: Config) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set in environment.")
    return key


def _parse_json(raw: str) -> dict:
    """Extract the first JSON object from a model response (handles fences/prose)."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find first {...} balanced region
    # String-aware: brace characters inside quoted JSON strings don't count
    # (a close brace in a string value must not end the object early).
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            c = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif c == "\\":
                    escaped = True
                elif c == '"':
                    in_string = False
                continue
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError(f"Adapter: no parseable JSON object in model response:\n{raw[:500]}")


def complete(system_prompt: str, user_payload: str, cfg: Config, model: str | None = None) -> str:
    """One model call. Retries with 30–90s backoff on provider stalls/failures."""
    url = cfg.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {_api_key(cfg)}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model or cfg.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0.4,
    }
    last_err = None
    for attempt in range(1, 5):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=_TIMEOUT)
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"provider status {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001 — provider stalls are expected
            last_err = e
            if attempt == 4:
                break
            delay = random.uniform(30, 90)
            print(f"[adapter] call failed (attempt {attempt}): {e}; retrying in {delay:.0f}s", file=sys.stderr, flush=True)
            time.sleep(delay)
    raise RuntimeError(f"adapter: model call failed after 4 attempts: {last_err}")


def structured_complete(
    system_prompt: str, user_payload: str, cfg: Config, model: str | None = None
) -> dict:
    """complete() + JSON parse. One retry asking the model to fix its own JSON."""
    raw = complete(system_prompt, user_payload, cfg, model=model)
    try:
        return _parse_json(raw)
    except ValueError:
        fixed = complete(
            system_prompt,
            user_payload + "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON object, no prose, no code fences.",
            cfg,
            model=model,
        )
        return _parse_json(fixed)
