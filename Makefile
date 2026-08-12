.PHONY: run test seed demo

run:
	python app.py

test:
	python -m pytest -q

demo: run
