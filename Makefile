.PHONY: install install-dev lint typecheck test validate ci scrape enrich server docker-build docker-run cli clean

## ── Installation ──────────────────────────────────────────────

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

## ── Quality ───────────────────────────────────────────────────

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy src/soc_db/cli.py src/soc_db/common.py src/soc_db/__init__.py src/soc_db/__main__.py

test:
	python -m pytest tests/ -v --tb=short

test-cov:
	python -m pytest tests/ -v --tb=short --cov=soc_db --cov-report=term-missing

security:
	bandit -r src/ -x tests/

ci: lint typecheck security test validate check-docs-guard

## ── Data ──────────────────────────────────────────────────────

validate:
	python tests/validate.py

scrape:
	python scripts/scraper_wikipedia.py

scrape-apple:
	python scripts/scraper_apple.py

enrich:
	python scripts/migrate.py

pipeline:
	cd scripts && python pipeline.py

## ── API Server ────────────────────────────────────────────────

server:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

## ── Docker ────────────────────────────────────────────────────

docker-build:
	docker build -t soc-db .

docker-run:
	docker run -d --name soc-db -p 8000:8000 -v $(PWD)/data:/app/data:ro soc-db

## ── CLI ───────────────────────────────────────────────────────

cli:
	@python -m soc_db.cli $(filter-out $@,$(MAKECMDGOALS))

check-docs-guard:
	python tests/check_docs_guard.py
	python -m pytest tests/unit/test_common.py::TestGuardPath -x --no-header -q

## ── Deployment ────────────────────────────────────────────────

deploy:
	@echo "To install auto-deploy timer:"
	@echo "  sudo cp deploy/soc-db-update.* /etc/systemd/system/"
	@echo "  sudo systemctl daemon-reload"
	@echo "  sudo systemctl enable --now soc-db-update.timer"
	@echo ""
	@echo "To run once: sudo systemctl start soc-db-update.service"

install-timer:
	sudo cp deploy/soc-db-update.* /etc/systemd/system/ && \
	sudo systemctl daemon-reload && \
	sudo systemctl enable --now soc-db-update.timer && \
	echo "Timer installed. Status:" && \
	sudo systemctl status soc-db-update.timer --no-pager

## ── Release ───────────────────────────────────────────────────

release:
	@if [ -z "$(v)" ]; then echo "Usage: make release v=x.y.z"; exit 1; fi
	@if ! git diff --quiet; then echo "Working tree is dirty. Commit first."; exit 1; fi
	sed -i 's/^version = ".*"/version = "$(v)"/' pyproject.toml
	git add pyproject.toml
	git commit -m "release: $(v)"
	git tag -a "v$(v)" -m "soc-db v$(v)"
	@echo "Tagged v$(v). Push with: git push --follow-tags"

## ── Housekeeping ──────────────────────────────────────────────

pre-commit:
	pre-commit run --all-files

benchmark:
	python -m pytest tests/ --benchmark-only -v 2>/dev/null || echo "pytest-benchmark not installed; run: pip install pytest-benchmark"

.PHONY: benchmark security

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true

%:
	@:
