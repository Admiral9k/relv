"""relv CLI: relv <url|app-name|text> [--emit-md] [--depth] [--model] [--json]

Pipeline: fetch → extract → verdict → adjacency → emit.
Every stage structured-in, structured-out; all model calls via the adapter.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config as cfgmod
from .adjacency import adjacency_search, adjacency_synth, render_adjacency, validate_find_urls
from .config import Config, effective_backends, load_config, write_default_config
from .emit import build_output, emit_md, render_stdout
from .fetch import extract, fetch_url, resolve_name
from .verdict import verdict

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_DEFAULT_PROFILE = Path(__file__).parent / "default_profile.md"


def classify_input(text: str) -> str:
    if _URL_RE.match(text.strip()):
        return "url"
    if len(text) > 400 or "\n" in text:
        return "text"
    return "name"


def run_pipeline(text: str, cfg: Config, emit: bool, out_json: bool) -> int:
    kind = classify_input(text)
    backends, notes = effective_backends(cfg)
    profile = _load_profile(cfg)

    # --- fetch ---
    if kind == "url":
        raw = fetch_url(text.strip(), cfg, backends, notes)
        source_desc = f"url: {text.strip()}"
    elif kind == "name":
        raw = resolve_name(text.strip(), cfg, backends["resolve"])
        source_desc = f"bare name: {text.strip()!r} (resolved via {backends['resolve']})"
    else:
        raw = {"url": "", "fetched_text": text, "search_results": None}
        source_desc = "pasted text"

    # --- extract ---
    ext = extract(raw, cfg)

    # --- verdict ---
    v = verdict(ext, profile, cfg, source_desc)

    # --- adjacency ---
    results = adjacency_search(v["adjacency_queries"], cfg, backends["adjacency"], cfg.n_results)
    if results:
        adj = adjacency_synth(v["adjacency_queries"], results, profile, v["content_summary"], cfg)
        adj = validate_find_urls(adj, cfg, backends["resolve"])
    else:
        # all queries failed/returned nothing — degrade, don't crash the run
        if v["adjacency_queries"]:
            adj = {"finds": [], "reason": "search unavailable: all queries failed", "sludge_check": ""}
            notes.append("adjacency degraded: search unavailable (all queries failed)")
        else:
            adj = {"finds": [], "reason": "adjacency unavailable: verdict produced no queries", "sludge_check": ""}
            notes.append("adjacency degraded: verdict produced no adjacency queries")
    adj["_backend"] = backends["adjacency"]
    adj["_n_raw_results"] = len(results)

    # --- emit ---
    flagged = [f["url"] for f in adj.get("finds", []) if f.get("url_status") == "flagged"]
    meta = {
        "input": text[:5000],
        "input_kind": kind,
        "source_desc": source_desc,
        "model": cfg.model,
        "synthesis_model": cfg.synthesis_model,
        "depth": cfg.depth,
        "backends": backends,
        "degradation_notes": notes,
        "flagged_urls": flagged,
        "profile_path": cfg.profile_path,
        "when": datetime.now(timezone.utc).isoformat(),
    }
    out = build_output(v, adj, meta)
    md_path = emit_md(out, cfg.emit_dir) if emit else None

    if out_json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(render_stdout(out))
    if notes:
        print("\n".join(notes), file=sys.stderr)
    if md_path:
        print(f"\nemitted: {md_path}")
    return 0


def _write_default_profile(dir_path: str) -> None:
    """Write a default profile.md into dir_path if absent (used by `relv init`)."""
    p = Path(dir_path) / "profile.md"
    if not p.exists():
        p.write_text(_DEFAULT_PROFILE.read_text(encoding="utf-8"), encoding="utf-8")


def _load_profile(cfg: Config) -> str:
    p = Path(cfg.profile_path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    print(
        "relv: no profile.md found; using bundled default — run `relv init` and edit profile.md",
        file=sys.stderr,
    )
    return _DEFAULT_PROFILE.read_text(encoding="utf-8")


def main(argv: list | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]  # console-script entry points call main() bare
    if argv and argv[0] == "ui":
        # launch the pywebview UI (relv[ui] extra); defer import so the CLI
        # package works without pywebview installed
        try:
            from .ui import main as ui_main
        except ImportError:
            print("relv: UI not installed — run: uv tool install --with relv[ui] relv  (or pip install relv[ui])")
            return 1
        return ui_main(argv[1:])
    if argv and argv[0] == "init":
        write_default_config(str(Path.cwd()))
        _write_default_profile(str(Path.cwd()))
        print("wrote config.yaml (edit model/depth/backends; keys come from env)")
        print("wrote profile.md — edit profile.md; it is YOU the tool grounds against")
        return 0

    ap = argparse.ArgumentParser(prog="relv", description="Relevator — profile-grounded relevance triage + adjacency mining")
    ap.add_argument("input", help="a URL, an app name, or pasted text")
    ap.add_argument("--emit-md", action="store_true", help="write an ingest-ready markdown file")
    ap.add_argument("--json", action="store_true", help="print the full structured output as JSON")
    ap.add_argument("--depth", choices=["picky", "standard", "broad"], help="override depth from config")
    ap.add_argument("--model", help="override model from config")
    ap.add_argument("--config-dir", help="directory containing config.yaml / profile.md")
    args = ap.parse_args(argv)

    if not args.input:
        ap.print_help()
        return 1

    cfg = load_config(args.config_dir)
    if args.depth:
        cfg.depth = args.depth
    if args.model:
        cfg.model = args.model
    try:
        return run_pipeline(args.input, cfg, emit=args.emit_md, out_json=args.json)
    except RuntimeError as e:
        print(f"relv: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
