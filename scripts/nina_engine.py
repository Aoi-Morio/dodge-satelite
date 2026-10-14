"""Headless frozen engine for the N.I.N.A. plugin; no Qt libraries required."""

from dodge_satelite.nina_bridge import main

if __name__ == "__main__":
    raise SystemExit(main())
