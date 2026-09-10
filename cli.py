"""OS Simulator CLI entrypoint.

Emulates the OS startup with loading animation and custom text,
and provides an interactive shell for the operating system simulation.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli import app

if __name__ == "__main__":
    app()
