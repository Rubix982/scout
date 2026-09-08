# src/main.py
"""Entry point. Delegates to the CLI so `python -m src.main` and
`python -m src.cli` behave identically."""

from src.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
