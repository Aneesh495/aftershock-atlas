UV_CACHE_DIR := $(CURDIR)/.agent-local/uv-cache
export UV_CACHE_DIR
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=uv run --frozen
RUN_ID ?= diagnostic
PROFILE ?= diagnostic
EVIDENCE ?= evidence/$(RUN_ID)
EXPECTED_SOURCE ?= $(shell git rev-parse HEAD)
.PHONY: bootstrap doctor build test data demo bench stress docs acceptance verify release covid-data panel fit forecasts causal studies atlas survey-data surveys dynamic history-data history-panel
bootstrap:
	uv sync --frozen
	cd client && npm ci --cache ../.agent-local/npm-cache
build:
	$(PY) python -m compileall -q src
	cd client && npm run build
	$(PY) python -c "import shutil; shutil.copytree('client/dist','dist',dirs_exist_ok=True)"

doctor data covid-data panel fit forecasts causal studies atlas bench stress docs survey-data surveys dynamic history-data history-panel:
	$(PY) aftershock $@
test:
	$(PY) ruff check src tests
	$(PY) pytest -q
	cd client && npm run check
demo:
	$(PY) aftershock demo
acceptance:
	$(PY) aftershock acceptance --run-id $(RUN_ID) --profile $(PROFILE)
verify:
	$(PY) aftershock verify --evidence $(EVIDENCE) --expected-source $(EXPECTED_SOURCE)
release:
	$(PY) aftershock release --evidence $(EVIDENCE)
