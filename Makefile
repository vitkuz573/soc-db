.PHONY: validate scrape clean server

validate:
	python3 tests/validate.py

scrape:
	bash scripts/run_all.sh

server:
	python3 -m http.server 8080 --bind 0.0.0.0

clean:
	rm -rf __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
