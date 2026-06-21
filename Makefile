.PHONY: install install-dev lint typecheck test validate ci scrape enrich server docker-build docker-run cli clean

## ── Installation ──────────────────────────────────────────────

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]" || pip install -r requirements-dev.txt
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
	bandit -r src/ -x tests/ || true

ci: lint typecheck test validate

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

## ── Housekeeping ──────────────────────────────────────────────

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
