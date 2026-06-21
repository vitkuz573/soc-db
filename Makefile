.PHONY: validate scrape enrich server docker-build docker-run cli clean

validate:
	python3 tests/validate.py

scrape:
	bash scripts/run_all.sh 2>/dev/null || echo "No run_all.sh found"

enrich:
	python3 scripts/migrate.py

server:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t soc-db .

docker-run:
	docker run -d --name soc-db -p 8000:8000 -v $(PWD)/data:/app/data:ro soc-db

cli:
	@python3 bin/soc-db $(filter-out $@,$(MAKECMDGOALS))

clean:
	rm -rf __pycache__ .pytest_cache
	find . -name "*.pyc" -delete

%:
	@:
