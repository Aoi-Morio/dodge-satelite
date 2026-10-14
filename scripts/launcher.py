"""Shared frozen entry point; CLI and windowed EXEs reuse the same runtime."""

import sys
from pathlib import Path

if Path(sys.executable).stem.lower() == "dodge-satelite-gui":
    from dodge_satelite.gui import main
else:
    from dodge_satelite.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
