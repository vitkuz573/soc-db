.PHONY: validate server clean

validate:
	python3 tests/validate.py

server:
	python3 -m http.server 8080 --bind 0.0.0.0

clean:
	rm -rf __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
