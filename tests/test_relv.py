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

import httpx
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


# ---------- v1.1 fix 1: profile trap (init writes profile, fallback warns) ----------

def test_init_writes_config_and_profile(tmp_path, monkeypatch):
    import relv.cli as climod

    monkeypatch.chdir(tmp_path)
    rc = climod.main(["init"])
    assert rc == 0
    assert (tmp_path / "config.yaml").exists()
    assert (tmp_path / "profile.md").exists()
    default = (Path(climod.__file__).parent / "default_profile.md").read_text(encoding="utf-8")
    assert (tmp_path / "profile.md").read_text(encoding="utf-8") == default


def test_init_is_idempotent(tmp_path, monkeypatch):
    import relv.cli as climod

    monkeypatch.chdir(tmp_path)
    climod.main(["init"])
    (tmp_path / "profile.md").write_text("# My edited profile\n")
    climod.main(["init"])
    assert (tmp_path / "profile.md").read_text() == "# My edited profile\n"  # not clobbered


def test_load_profile_fallback_warns_on_stderr(cfg, capsys):
    import relv.cli as climod

    assert not Path(cfg.profile_path).exists()
    profile = climod._load_profile(cfg)
    err = capsys.readouterr().err
    assert "no profile.md found" in err and "bundled default" in err and "relv init" in err
    assert profile  # non-empty default content returned


def test_load_profile_no_warning_when_present(cfg, capsys):
    import relv.cli as climod

    Path(cfg.profile_path).write_text("# My profile\n")
    profile = climod._load_profile(cfg)
    assert profile == "# My profile\n"
    assert capsys.readouterr().err == ""


# ---------- v1.1 fix 2: depth -> n_queries mapping (dead knob now wired) ----------

def test_depth_to_n_queries_mapping():
    # documented mapping: picky 2, standard 3, broad 5
    for depth, n in (("picky", 2), ("standard", 3), ("broad", 5)):
        c = Config(depth=depth)
        assert c.n_queries == n, f"{depth} should map to {n} queries"


def test_verdict_prompt_carries_n_queries(cfg):
    import inspect
    from relv import verdict as verdictmod

    src = inspect.getsource(verdictmod.verdict)
    assert "cfg.n_queries" in src  # prompt instruction is generated from config
    # depth changes the instruction the model actually receives
    c2 = Config(depth="picky")
    assert c2.n_queries != cfg.n_queries


# ---------- v1.1 fix 3: all-adjacency-queries-fail degrades gracefully ----------

def test_adjacency_search_returns_empty_not_raise(monkeypatch):
    def boom(q, n, b):
        raise RuntimeError("backend down")

    monkeypatch.setattr(adjacency, "search", boom)
    res = adjacency.adjacency_search(["q1", "q2"], Config(), "exa", 10)
    assert res == []  # no exception, empty results


def test_pipeline_degrades_when_all_queries_fail(cfg, monkeypatch, tmp_path, capsys):
    """Full pipeline path: verdict succeeds, search all fails -> output with
    empty finds + degradation note, rc 0, no exception."""
    import relv.cli as climod

    Path(cfg.profile_path).write_text("# P\nA terminal-first builder.\n")
    cfg.emit_dir = str(tmp_path / "emis")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")  # effective_backends needs one key present

    monkeypatch.setattr(adjacency, "search", lambda q, n, b: (_ for _ in ()).throw(RuntimeError("backend down")))
    # resolve_name (bare-name inputs) imports search inside fetch.py — patch that binding
    # too, or a name-kind input fires a REAL Tavily call under the fake key.
    import relv.fetch as fetchmod
    monkeypatch.setattr(fetchmod, "search", lambda q, n, b: (_ for _ in ()).throw(RuntimeError("backend down")))
    # each stage holds its own `from .adapter import structured_complete` binding at
    # import time — patch every stage's binding or extract()/verdict() fire real calls.
    import relv.verdict as verdictmod
    fake_model = lambda s, u, c, model=None: {
        "content_summary": "s", "grabs": [{"type": "aspect", "what": "w", "why": "y"}],
        "aspects": ["a"], "adjacency_queries": ["q1", "q2"],
    }
    monkeypatch.setattr(verdictmod, "structured_complete", fake_model)
    monkeypatch.setattr(fetchmod, "structured_complete", lambda s, u, c, model=None: {
        "title": "t", "content": "c", "search_results": None,
    })
    monkeypatch.setattr(adjacency, "structured_complete", fake_model)
    rc = climod.run_pipeline("Jev by Typesafe\npasted text kind so classify_input routes to text and no resolve_name search fires", cfg, emit=False, out_json=True)
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["adjacency"]["finds"] == []
    assert out["adjacency"]["reason"] == "search unavailable: all queries failed"
    assert "all queries failed" in " ".join(out["_meta"]["degradation_notes"])


# ---------- v1.1 fix 4: fetch fallback + social notice write degradation notes ----------

def test_fetch_url_notes_tavily_fallback(monkeypatch):
    import relv.fetch as fetchmod

    monkeypatch.setattr(fetchmod.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("nope")))
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-x")
    monkeypatch.setattr(fetchmod, "_tavily_extract", lambda url: "x" * 500)
    notes = []
    out = fetchmod.fetch_url("https://thin.example.com", None, {"resolve": "tavily"}, notes)
    assert len(out["fetched_text"]) >= 300
    assert any("direct fetch failed" in n and "tavily" in n for n in notes)


def test_fetch_url_social_notice(monkeypatch):
    import relv.fetch as fetchmod

    class R:
        status_code = 200
        headers = {"content-type": "text/html"}
        text = "<html><body>" + "y" * 500 + "</body></html>"

    monkeypatch.setattr(fetchmod.httpx, "get", lambda *a, **k: R())
    notes = []
    fetchmod.fetch_url("https://x.com/someone/status/123", None, None, notes)
    assert any("X.com requires auth" in n for n in notes)


# ---------- v1.1 fix 6: prose-wrapped JSON with braces in strings ----------

def test_parse_json_prose_wrapped_brace_in_string():
    assert adapter._parse_json('Here: {"a": "literal } brace"} done')["a"] == "literal } brace"


def test_parse_json_prose_wrapped_escaped_quote_brace():
    raw = 'Sure thing:\n{"a": "escaped \\" quote } then real", "b": 2} ok'
    assert adapter._parse_json(raw)["a"].startswith("escaped")


def test_parse_json_fenced_brace_in_string():
    raw = '```json\n{"a": "close } brace", "b": {"c": "d } e"}}\n```'
    out = adapter._parse_json(raw)
    assert out["a"] == "close } brace" and out["b"]["c"] == "d } e"


# ---------- v1.1 fix 7: hard constraint — models array has exactly one entry ----------

def test_verdict_models_array_exactly_one_entry():
    """Keyless: every golden fixture 005-009 verdict has exactly one models entry."""
    golden = sorted(Path(__file__).parents[1].glob("examples/golden/00[5-9]*.json"))
    assert len(golden) == 5
    for p in golden:
        v = json.loads(p.read_text())["verdict"]
        assert len(v["models"]) == 1, f"{p.name}: models must hold exactly one entry in v1"
        assert set(v["models"][0]) == {"model", "verdict", "why"}


# ---------- v1.1 misc: full input capture capped at 5000 ----------

def test_meta_input_capped_at_5000():
    import inspect
    import relv.cli as climod

    src = inspect.getsource(climod.run_pipeline)
    assert "text[:5000]" in src and "text[:300]" not in src


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
