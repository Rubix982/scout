.PHONY: activate
activate:
	source .venv/bin/activate

.PHONY: tests
tests:
	pytest -v -s --cov=src --cov-report=term-missing

.PHONY: run
run:
	python3 src/main.py
