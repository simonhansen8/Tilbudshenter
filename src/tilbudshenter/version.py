"""Hvilken udgave af Tilbudshenter der kører.

Udgaven er den commit, programmet er bygget fra. Den findes, i den
rækkefølge, fra git (når programmet kører fra en klon, og på GitHub
Actions), fra ``VERSION.txt``, som opdateringen lægger i programmappen, og
fra GitHub Actions' miljøvariabler.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = "simonhansen8/Tilbudshenter"

# src/tilbudshenter/version.py -> roden af repoet eller programmappen
ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def current(root: Path = ROOT, env: dict | None = None) -> dict:
    """Udgaven som ``{"sha", "date", "dirty", "repo", "source"}``. ``sha``
    er None, hvis den ikke kan findes (fx en udpakket zip uden VERSION.txt).
    ``source`` er "git", "installeret" eller "actions"."""
    env = os.environ if env is None else env
    repo = env.get("GITHUB_REPOSITORY") or REPO
    sha = date = None
    dirty = False
    source = None
    if (root / ".git").exists():
        sha = _git(root, "rev-parse", "HEAD")
        if sha:
            source = "git"
            date = _git(root, "log", "-1", "--format=%cI") or None
            # Rettelser, der ikke er gemt i git, kun i src (data og
            # indstillinger ligger også i mappen, men er ikke programmet)
            dirty = bool(_git(root, "status", "--porcelain", "--", "src"))
    if not sha:
        try:
            sha = (root / "VERSION.txt").read_text("utf-8").strip() or None
            source = "installeret"
        except OSError:
            sha = None
    if not sha:
        sha, source = env.get("GITHUB_SHA") or None, "actions"
    if not sha or len(sha) != 40:  # fx "lokal" fra installationen
        sha = source = None
    return {"sha": sha, "date": date, "dirty": dirty, "repo": repo, "source": source}


def includes(sha: str, root: Path = ROOT) -> bool:
    """Om en klon allerede har commit ``sha`` med (den kan også være nyere,
    fx en gren man arbejder på)."""
    return _git(root, "merge-base", "--is-ancestor", sha, "HEAD") is not None
