PY ?= python3
OUT ?= out

.PHONY: setup doctor samples demo test clean live docker

# run this first if `pip install` complains about pydantic/pymupdf versions
doctor:
	$(PY) scripts/doctor.py

setup:
	$(PY) -m venv .venv && .venv/bin/pip install -q -r requirements.txt

samples:
	$(PY) -m samples.build_samples
	$(PY) -m samples.rasterize

# offline end-to-end run: fixtures -> triage -> match -> validate -> CSV + review pack
demo:
	$(PY) -m chronik.cli
	$(PY) -m chronik.preview

live:
	$(PY) -m chronik.cli --live

# no local Python needed (see ../docker-compose.yml)
docker:
	cd .. && docker compose run --rm demo

test:
	$(PY) -m pytest -q

clean:
	rm -rf $(OUT) samples/_textlayer

# open the artefacts produced by `make demo`
show:
	@echo "CSV      : $(OUT)/csv"
	@echo "Review   : $(OUT)/review/review.html"
	@echo "Metrics  : $(OUT)/metrics.json"
