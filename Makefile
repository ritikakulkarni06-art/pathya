PYTHON ?= python
.PHONY: install dev worker test lint typecheck check openapi contracts contracts-check demo demo-check
install:
	$(PYTHON) -m pip install -r requirements.lock
dev:
	$(PYTHON) -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
worker:
	$(PYTHON) -m app.worker
test:
	$(PYTHON) -m pytest -q
lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
typecheck:
	$(PYTHON) -m mypy
check:
	$(PYTHON) -m scripts.check
openapi contracts:
	$(PYTHON) -m scripts.export_contracts
contracts-check:
	$(PYTHON) -m scripts.export_contracts --check
demo:
	$(PYTHON) -m scripts.demo
demo-check:
	$(PYTHON) -m scripts.demo --smoke --port 0
