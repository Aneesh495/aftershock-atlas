UV_CACHE_DIR := $(CURDIR)/.agent-local/uv-cache
export UV_CACHE_DIR
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
PY=uv run --frozen
RUN_ID ?= diagnostic
PROFILE ?= diagnostic
EVIDENCE ?= evidence/$(RUN_ID)
.PHONY: bootstrap doctor build test data demo bench stress docs acceptance verify release covid-data panel fit forecasts causal studies atlas
bootstrap:
	uv sync --frozen
	cd client && npm ci --cache ../.agent-local/npm-cache
build:
	$(PY) python -m compileall -q src
	cd client && npm run build

doctor data covid-data panel fit forecasts causal studies atlas bench stress docs:
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
	$(PY) aftershock verify --evidence $(EVIDENCE) --expected-source $$(git rev-parse HEAD)
release:
	$(PY) aftershock release
