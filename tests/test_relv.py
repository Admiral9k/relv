"""relv test suite.

Two layers:
- unit tests (no network, no keys): config, adapter JSON parsing, URL
  validation logic, emit rendering, input classification.
- integration tests (live keys + network): the real pipeline. Skipped
  automatically when keys are missing, so the suite always passes offline.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from relv import adjacency, adapter, config, emit  # noqa: E402
from relv.cli import classify_input  # noqa: E402
from relv.config import Config, effective_backends, load_config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.profile_path = str(tmp_path / "profile.md")
    c.config_dir = str(tmp_path)
    return c


# ---------- config ----------

def test_default_config_values(cfg):
    assert cfg.model == "z-ai/glm-5.3-flash"
    assert cfg.depth == "standard"
    assert cfg.n_queries == 3 and cfg.n_results == 12


def test_depth_picky_synthesizes_with_strong(cfg):
    cfg.depth = "picky"
    assert cfg.synthesis_model == "z-ai/glm-5.3"
    cfg.depth = "standard"
    assert cfg.synthesis_model == "z-ai/glm-5.3-flash"


def test_load_config_roundtrip(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("model: foo/bar\ndepth: broad\n")
    monkeypatch.chdir(tmp_path)
    c = load_config(str(tmp_path))
    assert c.model == "foo/bar" and c.depth == "broad" and c.n_results == 20


def test_load_config_rejects_bad_depth(tmp_path):
    (tmp_path / "config.yaml").write_text("depth: yolo\n")
    with pytest.raises(ValueError):
        load_config(str(tmp_path))


def test_effective_backends_degrades(cfg, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    eff, notes = effective_backends(cfg)
    assert eff["adjacency"] == "tavily"  # degraded exa -> tavily
    assert any("degraded" in n for n in notes)


def test_effective_backends_no_keys(cfg, monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        effective_backends(cfg)


# ---------- adapter JSON parsing (no network) ----------

def test_parse_json_plain():
    assert adapter._parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert adapter._parse_json('```json\n{"a": [1,2]}\n```') == {"a": [1, 2]}


def test_parse_json_prose_wrapped():
    assert adapter._parse_json('Here you go:\n{"a": {"b": "c"}} hope that helps') == {"a": {"b": "c"}}


def test_parse_json_nested_braces_in_strings():
    assert adapter._parse_json('{"a": "literal } brace"}')["a"] == "literal } brace"


def test_parse_json_failure():
    with pytest.raises(ValueError):
        adapter._parse_json("no json here at all")


# ---------- adjacency URL validation (no network) ----------

def test_url_validation_ok_match():
    f = {"name": "FieldNote AI", "url": "https://www.fieldsnotesai.com/"}
    assert adjacency._check_one(dict(f), Config(), "tavily") == "ok"


def test_url_validation_noise_domain_flagged(monkeypatch):
    # press-domain URL, and the re-resolve search finds nothing better
    monkeypatch.setattr(adjacency, "search", lambda q, n, b: [])
    f = {"name": "Some Product", "url": "https://markets.businessinsider.com/news/x"}
    assert adjacency._check_one(f, Config(), "tavily") == "flagged"


def test_url_validation_re_resolves(monkeypatch):
    monkeypatch.setattr(
        adjacency,
        "search",
        lambda q, n, b: [{"name": "Some Product", "url": "https://someproduct.io/", "snippet": ""}],
    )
    f = {"name": "Some Product", "url": "https://techcrunch.com/2026/some-product-launches"}
    assert adjacency._check_one(f, Config(), "tavily") == "re_resolved"
    assert f["url"] == "https://someproduct.io/"
    assert f["original_url"].startswith("https://techcrunch.com")


def test_validate_find_urls_adds_status(monkeypatch):
    monkeypatch.setattr(adjacency, "_check_one", lambda f, c, b: "ok")
    out = adjacency.validate_find_urls({"finds": [{"name": "x", "url": "https://y.io"}]}, Config(), "tavily")
    assert out["finds"][0]["url_status"] == "ok"


def test_adjacency_search_dedupes(monkeypatch):
    import relv.search as searchmod

    fake = [
        {"name": "a", "url": "https://x.io/1", "snippet": "", "source": "exa", "query": "q1"},
        {"name": "b", "url": "https://x.io/1", "snippet": "", "source": "exa", "query": "q2"},
        {"name": "c", "url": "https://x.io/2", "snippet": "", "source": "exa", "query": "q2"},
    ]
    it = iter(fake)

    def fake_search(q, n, b):
        return [r for r in fake if r["query"] == q]

    monkeypatch.setattr(adjacency, "search", fake_search)
    res = adjacency.adjacency_search(["q1", "q2"], Config(), "exa", 10)
    assert len(res) == 2 and {r["url"] for r in res} == {"https://x.io/1", "https://x.io/2"}


# ---------- emit ----------

def test_emit_md_writes_ingest_file(tmp_path):
    out = emit.build_output(
        {"content_summary": "A test tool", "grabs": [{"type": "aspect", "what": "w", "why": "y"}],
         "aspects": ["a1"], "models": [{"model": "m", "verdict": "aspect", "why": "y"}], "confidence": None,
         "adjacency_queries": []},
        {"finds": [{"name": "F", "url": "https://f.io", "what_it_is": "x", "different_angle": "d",
                    "why_relevant_to_profile": "w", "url_status": "ok"}], "sludge_check": "clean"},
        {"input": "https://example.com", "model": "m", "depth": "standard", "backends": {"resolve": "tavily"}},
    )
    p = emit.emit_md(out, str(tmp_path / "emit"))
    text = Path(p).read_text()
    assert "relv triage" in text and "## Grabs" in text and "## Adjacent finds" in text and "<https://f.io>" in text


def test_render_stdout_mentions_degradation_and_flags():
    out = emit.build_output({"content_summary": "s", "grabs": [], "aspects": [], "models": [], "confidence": None,
                             "adjacency_queries": []},
                            {"finds": [], "sludge_check": ""},
                            {"input": "x", "degradation_notes": ["degraded to tavily"], "flagged_urls": ["https://bad.io"]})
    s = emit.render_stdout(out)
    assert "degraded to tavily" in s and "https://bad.io" in s


# ---------- input classification ----------

def test_classify_input():
    assert classify_input("https://goblin.tools") == "url"
    assert classify_input("http://x.io") == "url"
    assert classify_input("Jev by Typesafe") == "name"
    assert classify_input("word " * 200) == "text"
    assert classify_input("line one\nline two") == "text"


# ---------- integration (live keys required; auto-skip) ----------

LIVE = bool(os.environ.get("OPENROUTER_API_KEY")) and (
    os.environ.get("TAVILY_API_KEY") or os.environ.get("EXA_API_KEY")
)

needs_live = pytest.mark.skipif(not LIVE, reason="live keys not set — integration test skipped")


@pytest.fixture
def live_cfg(tmp_path):
    (tmp_path / "profile.md").write_text(
        "# Profile\n\n## Who I am\nA terminal-first builder running local AI agents and an ingest pipeline.\n"
        "## What I run\n- Local AI agents for research and coding\n- Multi-model routing\n- Obsidian vault with ingest queue\n"
        "## What I value\n- Small single-purpose tools; open source; markdown\n"
        "## What I reject\n- Marketing SaaS; listicles; per-seat subscriptions\n"
    )
    c = load_config(None)
    c.profile_path = str(tmp_path / "profile.md")
    return c


@needs_live
def test_verdict_schema_matches_architecture(live_cfg):
    """HARD constraint: verdict returns JSON with the one-entry models array."""
    from relv.verdict import verdict

    ext = {"title": "Goblin Tools", "content": "Goblin Tools is a free web app of eight single-purpose AI micro-tools for neurodivergent users: Magic ToDo, Formalizer, Judge, Taskmaster, Professor, Consultant, Compiler, Chef. One tool, one button, one job."}
    v = verdict(ext, Path(live_cfg.profile_path).read_text(), live_cfg, "test fixture")
    assert set(v["models"][0]) == {"model", "verdict", "why"}
    assert v["models"][0]["model"] == live_cfg.model
    assert v["models"][0]["verdict"] in ("product", "aspect", "none")
    assert v["confidence"] is None
    assert v["grabs"] and v["aspects"] and len(v["adjacency_queries"]) >= 2


@needs_live
def test_pipeline_url_end_to_end(live_cfg, tmp_path):
    """DoD #1: real URL runs end-to-end and emits markdown."""
    from relv.cli import run_pipeline

    live_cfg.emit_dir = str(tmp_path / "emis")
    rc = run_pipeline("https://goblin.tools", live_cfg, emit=True, out_json=False)
    assert rc == 0
    mds = list((tmp_path / "emis").glob("*.md"))
    assert len(mds) == 1 and "## Adjacent finds" in mds[0].read_text()
