"""Configuration loading: config.yaml + environment.

The only place model names, base URLs, and backend choices are read.
Pipeline stages receive a Config object, never env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_YAML = """\
# relv configuration
# Keys are BYO and read from the environment (never committed):
#   OPENROUTER_API_KEY  — model endpoint (OpenRouter or any OpenAI-compatible provider)
#   TAVILY_API_KEY      — search backend (default for resolve)
#   EXA_API_KEY         — search backend (default for adjacency)

model: z-ai/glm-5.3-flash   # triage temperament: flash leans adopt;
                            # z-ai/glm-5.3 leans skip — steals patterns instead of
                            # recommending products. Any OpenAI-compatible id works.
depth: standard              # picky | standard | broad

base_url: https://openrouter.ai/api/v1

backends:
  resolve: tavily            # name/URL resolution backend
  adjacency: exa             # semantic aspect-query backend

emit_dir: relv-emissions     # where --emit-md writes files
"""

DEPTH_QUERIES = {"picky": 2, "standard": 3, "broad": 4}
DEPTH_RESULTS = {"picky": 6, "standard": 12, "broad": 20}
# picky synthesizes with the strong model regardless of `model:` setting
PICKY_SYNTH_MODEL = "z-ai/glm-5.3"


@dataclass
class Config:
    model: str = "z-ai/glm-5.3-flash"
    depth: str = "standard"
    base_url: str = "https://openrouter.ai/api/v1"
    backends: dict = field(default_factory=lambda: {"resolve": "tavily", "adjacency": "exa"})
    emit_dir: str = "relv-emissions"
    profile_path: str = "profile.md"
    config_dir: str = ""  # where config.yaml/profile.md were found

    @property
    def n_queries(self) -> int:
        return DEPTH_QUERIES[self.depth]

    @property
    def n_results(self) -> int:
        return DEPTH_RESULTS[self.depth]

    @property
    def synthesis_model(self) -> str:
        """Model used for adjacency synthesis — picky uses the strong tier."""
        return PICKY_SYNTH_MODEL if self.depth == "picky" else self.model


def _find_config_dir() -> str:
    """First directory containing config.yaml or profile.md, checked in order."""
    for d in (os.getcwd(), str(Path.home() / ".config" / "relv")):
        if (Path(d) / "config.yaml").exists() or (Path(d) / "profile.md").exists():
            return d
    return os.getcwd()


_DEFAULT_BACKENDS = {"resolve": "tavily", "adjacency": "exa"}


def load_config(config_dir: str | None = None) -> Config:
    """Load config.yaml from config_dir (auto-discovered if None), overlay env vars."""
    cdir = config_dir or _find_config_dir()
    data: dict = {}
    cfg_file = Path(cdir) / "config.yaml"
    if cfg_file.exists():
        data = yaml.safe_load(cfg_file.read_text()) or {}
    cfg = Config(
        model=data.get("model", Config.model),
        depth=data.get("depth", Config.depth),
        base_url=data.get("base_url", Config.base_url),
        backends={**_DEFAULT_BACKENDS, **(data.get("backends") or {})},
        emit_dir=data.get("emit_dir", Config.emit_dir),
        profile_path=str(Path(cdir) / "profile.md"),
        config_dir=cdir,
    )
    if cfg.depth not in DEPTH_QUERIES:
        raise ValueError(f"depth must be one of {list(DEPTH_QUERIES)}, got {cfg.depth!r}")
    return cfg


def write_default_config(dir_path: str) -> None:
    """Write a default config.yaml into dir_path if absent (used by `relv init`)."""
    p = Path(dir_path) / "config.yaml"
    if not p.exists():
        p.write_text(DEFAULT_CONFIG_YAML)


def available_backends(cfg: Config) -> dict:
    """Which search backends have keys present. Degrade gracefully + say so."""
    return {
        "tavily": bool(os.environ.get("TAVILY_API_KEY")),
        "exa": bool(os.environ.get("EXA_API_KEY")),
    }


def effective_backends(cfg: Config) -> tuple[dict, list]:
    """Resolve configured backends against available keys.

    Returns (effective: {resolve, adjacency}, notes: [str, ...]) — notes describe
    any single-backend degradation and are surfaced in the output.
    """
    avail = available_backends(cfg)
    notes = []
    eff = dict(cfg.backends)
    if not avail.get(eff["resolve"]) and any(avail.values()):
        eff["resolve"] = "tavily" if avail.get("tavily") else "exa"
        notes.append(f"resolve backend degraded to {eff['resolve']} (missing key for configured backend)")
    if not avail.get(eff["adjacency"]) and any(avail.values()):
        eff["adjacency"] = "exa" if avail.get("exa") else "tavily"
        notes.append(f"adjacency backend degraded to {eff['adjacency']} (missing key for configured backend)")
    if not any(avail.values()):
        raise RuntimeError(
            "No search backend keys found. Set TAVILY_API_KEY and/or EXA_API_KEY in the environment."
        )
    return eff, notes
