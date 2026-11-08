PYTHON ?= python3

.PHONY: setup demo validate test reproduce clean-results

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -r requirements.txt

demo:
	.venv/bin/python -m app.cli make-demo-data --output-dir data/demo

validate:
	.venv/bin/python -m app.cli validate --data-dir data/demo --allow-synthetic

test:
	.venv/bin/behave

reproduce: demo validate test
	.venv/bin/python -m app.cli run --config configs/demo.json

clean-results:
	find results -type f ! -name '.gitkeep' -delete

