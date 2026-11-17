#!/usr/bin/env python3
"""Einstiegspunkt: python omx.py <befehl>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from omx_cli.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
