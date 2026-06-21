.PHONY: validate scrape enrich pipeline server docker-build docker-run cli clean

validate:
	python3 tests/validate.py

scrape:
	python3 scripts/scraper_wikipedia.py

scrape-apple:
	python3 scripts/scraper_apple.py

enrich:
	python3 scripts/migrate.py

pipeline:
	python3 scripts/pipeline.py

server:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t soc-db .

docker-run:
	docker run -d --name soc-db -p 8000:8000 -v $(PWD)/data:/app/data:ro soc-db

cli:
	@python3 bin/soc-db $(filter-out $@,$(MAKECMDGOALS))

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

clean:
	rm -rf __pycache__ .pytest_cache
	find . -name "*.pyc" -delete

%:
	@:
