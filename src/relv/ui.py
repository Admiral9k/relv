"""relv UI — pywebview shell over the same pipeline the CLI runs.

Layout (VS Code-style): three left panels (history | grabs | adjacent finds),
workspace view on the right, notes sidebar far right. Persistent run store
(SQLite) so every verdict is auto-saved, browsable, note-able.

The UI never talks to an API directly — js_api bridges to run_pipeline().
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import webview

from .config import Config, effective_backends, load_config
from .cli import _load_profile, classify_input
from .adjacency import adjacency_search, adjacency_synth, validate_find_urls
from .fetch import extract, fetch_url, resolve_name
from .verdict import verdict as verdict_stage

_STORE_NAME = "relv-history.db"


def _db(app_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(app_dir / _STORE_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input TEXT NOT NULL,
            input_kind TEXT,
            verdict_rollup TEXT,
            content_summary TEXT,
            output_json TEXT NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
    )
    return conn


class Api:
    """js_api bridge — everything the window calls, runs on a worker thread."""

    def __init__(self, app_dir: Path, cfg: Config):
        self.app_dir = app_dir
        self.cfg = cfg
        self.conn = _db(app_dir)
        self._lock = threading.Lock()
        self._progress_cb = None  # set by window load handler

    # ---- progress plumbing: window registers a JS callback ----
    def set_progress_sink(self, fn):
        self._progress_cb = fn

    def _tick(self, msg: str):
        if self._progress_cb:
            try:
                self._progress_cb(msg)
            except Exception:
                pass

    # ---- history ----
    def list_runs(self) -> str:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, input, input_kind, verdict_rollup, content_summary, created_at, notes "
                "FROM runs ORDER BY id DESC LIMIT 500"
            ).fetchall()
        return json.dumps([dict(r) for r in rows])

    def get_run(self, run_id: int) -> str:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        return json.dumps(dict(row)) if row else json.dumps(None)

    def save_note(self, run_id: int, notes: str) -> str:
        with self._lock:
            self.conn.execute("UPDATE runs SET notes=? WHERE id=?", (notes, run_id))
            self.conn.commit()
        return json.dumps({"ok": True})

    def delete_run(self, run_id: int) -> str:
        with self._lock:
            self.conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
            self.conn.commit()
        return json.dumps({"ok": True})

    # ---- the pipeline (same stages the CLI runs, with progress ticks) ----
    def run(self, text: str, depth: str | None = None, model: str | None = None) -> str:
        try:
            cfg = load_config(str(self.app_dir))
            if depth:
                cfg.depth = depth
            if model:
                cfg.model = model
            self._tick("Loading config + profile…")
            backends, notes = effective_backends(cfg)
            profile = _load_profile(cfg)
            kind = classify_input(text)
            self._tick(f"Classified input: {kind}")

            if kind == "url":
                raw = fetch_url(text.strip(), cfg, backends, notes)
            elif kind == "name":
                self._tick("Resolving name via search…")
                raw = resolve_name(text.strip(), cfg, backends["resolve"])
            else:
                raw = {"url": "", "fetched_text": text, "search_results": None}

            self._tick("Extracting content…")
            ext = extract(raw, cfg)

            self._tick("Judging against your profile… (the long part)")
            v = verdict_stage(ext, profile, cfg, f"{kind}: {text[:80]}")

            top = next((g["type"] for g in v.get("grabs", []) if g.get("type") != "none"), "none")
            self._tick(f"Verdict: {top.upper()} — searching one layer out…")

            results = adjacency_search(v["adjacency_queries"], cfg, backends["adjacency"], cfg.n_results)
            if results:
                self._tick(f"Found {len(results)} raw results — synthesizing…")
                adj = adjacency_synth(v["adjacency_queries"], results, profile, v["content_summary"], cfg)
                adj = validate_find_urls(adj, cfg, backends["resolve"])
            else:
                adj = {"finds": [], "reason": "search unavailable: all queries failed", "sludge_check": ""}
                notes.append("adjacency degraded: search unavailable (all queries failed)")
            adj["_backend"] = backends["adjacency"]
            adj["_n_raw_results"] = len(results)

            out = {
                "verdict": v,
                "adjacency": adj,
                "_meta": {
                    "input": text[:5000],
                    "input_kind": kind,
                    "source_desc": f"{kind}: {text[:120]}",
                    "model": cfg.model,
                    "synthesis_model": cfg.synthesis_model,
                    "depth": cfg.depth,
                    "backends": backends,
                    "degradation_notes": notes,
                    "flagged_urls": [f["url"] for f in adj.get("finds", []) if f.get("url_status") == "flagged"],
                    "when": datetime.now(timezone.utc).isoformat(),
                },
            }
            self._tick("Saving run…")
            run_id = self._store(out, text, kind)
            self._tick(f"Done — run #{run_id} saved.")
            out["_run_id"] = run_id
            return json.dumps({"ok": True, "run": out})
        except Exception as e:  # noqa: BLE001 — surface every failure to the window
            return json.dumps({"ok": False, "error": str(e)})

    def _store(self, out: dict, text: str, kind: str) -> int:
        v = out["verdict"]
        rollup = next((g["type"] for g in v.get("grabs", []) if g.get("type") != "none"), "none")
        cur = self.conn.execute(
            "INSERT INTO runs (input, input_kind, verdict_rollup, content_summary, output_json, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (text, kind, rollup, v.get("content_summary", "")[:300],
             json.dumps(out), datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return cur.lastrowid

    # ---- settings ----
    def get_profile(self) -> str:
        try:
            return _load_profile(self.cfg)
        except Exception:
            return ""

    def get_keys_status(self) -> str:
        import os
        return json.dumps({
            "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
            "tavily": bool(os.environ.get("TAVILY_API_KEY")),
            "exa": bool(os.environ.get("EXA_API_KEY")),
        })


def main(argv: list | None = None) -> int:
    import sys
    from .cli import write_default_config
    from .cli import _write_default_profile

    if argv is None:
        argv = sys.argv[1:]
    app_dir = Path(argv[1]) if len(argv) > 1 and argv[0] == "--dir" else Path.cwd()
    app_dir.mkdir(parents=True, exist_ok=True)

    # first-run bootstrap: init config + profile if absent
    if not (app_dir / "config.yaml").exists():
        write_default_config(str(app_dir))
        _write_default_profile(str(app_dir))

    cfg = load_config(str(app_dir))
    api = Api(app_dir, cfg)

    window = webview.create_window(
        "relv",
        url=str(Path(__file__).parent / "ui_assets" / "index.html"),
        js_api=api,
        width=1280,
        height=840,
        min_size=(760, 520),
        background_color="#220C10",
    )

    def on_loaded():
        api.set_progress_sink(lambda msg: window.evaluate_js(f"window.tick && window.tick({json.dumps(msg)})"))

    window.events.loaded += on_loaded
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
