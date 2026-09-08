VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: venv
venv:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

# Re-resolve direct deps from requirements.in and re-pin the locked set.
# See agents/shared/decisions.md -> "[E-007] Two-file dependency management".
.PHONY: lock
lock:
	$(PIP) install -r requirements.in
	$(PIP) freeze > requirements.txt

.PHONY: tests
tests:
	$(VENV)/bin/pytest -v -s --cov=src --cov-report=term-missing

.PHONY: run
run:
	$(PY) -m src.cli run

.PHONY: sync
sync:
	$(PY) -m src.cli sync

.PHONY: snapshot
snapshot:
	$(PY) -m src.cli snapshot

.PHONY: report
report:
	$(PY) -m src.cli report

# Note: there is deliberately no `activate` target. Each recipe line runs in its
# own subshell, so `source .venv/bin/activate` in a Makefile cannot affect the
# caller's shell -- the old target silently did nothing. Use `make venv` to build
# the environment, and the $(PY)/$(PIP) variables to run inside it.
