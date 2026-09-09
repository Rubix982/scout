"""E-001 regression tests: the plumbing invariants.

Each import check runs in a *fresh subprocess* with the project root as cwd.
Testing "importing this module has no side effects" in-process is meaningless --
by the time the test body runs, the suite has already imported half the package.
A subprocess is the only honest check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SRC_MODULES = [
    "src.clients.gsuite",
    "src.clients",
    "src.db.init",
    "src.db.insert",
    "src.db",
    "src.log.config",
    "src.log",
    "src.common.models",
    "src.common.utils",
    "src.common.entities",
    "src.common",
    "src.constants.tables",
    "src.config",
    "src.db.migrations",
    "src.db.companies",
    "src.db.roles",
    "src.sources",
    "src.sources.ats",
    "src.sources.ats.platforms",
    "src.sources.ats.roles",
    "src.sources.ats.resolve",
    "src.sources.ats.snapshot",
    "src.main",
]


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


def test_every_module_imports_without_secrets_present():
    """No module may raise at import when credentials are absent.

    `src/clients/gsuite.py` used to raise FileNotFoundError at module scope,
    which made it unimportable and took the entire test suite down with it.
    """
    failures = []
    for mod in SRC_MODULES:
        result = _run(f"import {mod}")
        if result.returncode != 0:
            failures.append(f"{mod}: {result.stderr.strip().splitlines()[-1:]}")
    assert not failures, "modules failed to import:\n" + "\n".join(failures)


def test_importing_db_does_not_create_scout_dir():
    """Importing the storage layer must not create ~/.scout.

    Measured before/after *inside* the subprocess. Checking only whether the
    directory exists afterwards cannot distinguish "created by this import"
    from "already there from a previous run" -- and it will be already there on
    any machine that has ever run the app.
    """
    result = _run(
        "import pathlib;"
        "d = pathlib.Path.home() / '.scout';"
        "before = d.exists();"
        "import src.db.init;"
        "print('created' if d.exists() and not before else 'unchanged')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unchanged", (
        "importing src.db.init created ~/.scout -- import-time side effect"
    )


def test_importing_log_does_not_create_log_dir():
    """Importing the logging layer must not create logs/."""
    result = _run(
        "import pathlib, shutil;"
        "existed = pathlib.Path('logs').exists();"
        "import src.log;"
        "print('unchanged' if pathlib.Path('logs').exists() == existed else 'created')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unchanged"


def test_single_shared_db_connection():
    """get_con() must return one connection per process, not one per caller."""
    from src.db.init import close_con, get_con

    try:
        assert get_con() is get_con()
    finally:
        close_con()


def test_logger_is_cached_per_name():
    """Distinct names must yield distinct loggers.

    The previous implementation cached one global logger, so the first name
    requested won and every module logged under it.
    """
    from src.log import get_logger

    alpha, beta = get_logger("alpha"), get_logger("beta")
    assert alpha.name == "alpha"
    assert beta.name == "beta"
    assert alpha is not beta
    assert get_logger("alpha") is alpha
