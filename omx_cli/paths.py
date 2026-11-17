"""Pfadauflösung — profil-sicher, ohne hartkodierte Home-Pfade."""
from __future__ import annotations

import os
from pathlib import Path

# Wurzel dieses Monorepos (…/openamer-agent-max)
ROOT = Path(__file__).resolve().parent.parent


def openamer_home() -> Path:
    """OpenAmer-Home: $OPENAMER_HOME, sonst %LOCALAPPDATA%\\openamer, sonst ~/.openamer."""
    env = os.environ.get("OPENAMER_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "openamer").exists():
        return Path(local) / "openamer"
    return Path.home() / ".openamer"


def agent_repo() -> Path:
    """Quellbaum des Agenten (dort liegt os/ und openamer_cli/)."""
    return openamer_home() / "openamer-agent"


def skills_dir() -> Path:
    return openamer_home() / "skills"


def model_dir() -> Path:
    return ROOT / "model" / "openamer-max-one"


def os_dir() -> Path:
    return ROOT / "os" / "openamer-os"
