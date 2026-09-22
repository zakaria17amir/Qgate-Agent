# qgate-agent — every target here maps 1:1 to a CI job. If it works here, it works in CI.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE        := docker compose
CORE           := --profile core
OBS            := --profile obs
EVAL           := --profile eval
CHAOS          := --profile chaos

.PHONY: help up up-infra up-all down logs ps demo chaos \
        install lint fmt typecheck unit contract integration eval-replay eval-live scan build \
        token migrate goldens-freeze clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- stack -------------------------------------------------------------------

up: ## start core services (line-sim, ingest, detect, agent, api, mock-mes, console + infra)
	$(COMPOSE) $(CORE) up -d --build

up-infra: ## infra only: redpanda, postgres, migrations
	$(COMPOSE) $(CORE) up -d --wait redpanda postgres && $(COMPOSE) $(CORE) run --rm migrate && $(COMPOSE) $(CORE) run --rm roles

up-all: ## core + observability + prefect
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) up -d --build

down: ## stop everything and drop volumes
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) $(CHAOS) down -v --remove-orphans

logs: ## tail all logs
	$(COMPOSE) $(CORE) logs -f --tail=200

ps: ## container status
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) ps

demo: ## replay the tool-wear scenario at 10x and open the console
	$(COMPOSE) $(CORE) run --rm -e SCENARIO=tool_wear -e REPLAY_SPEED=10 line-sim
	@echo "console: http://localhost:8080   api docs: http://localhost:8000/docs"

chaos: ## start core + toxiproxy with agent->mock-mes routed through the proxy
	$(COMPOSE) $(CORE) $(CHAOS) up -d --build

migrate: ## apply db/migrations with dbmate
	$(COMPOSE) $(CORE) run --rm migrate up

token: ## mint a dev JWT: make token ROLE=approver SUB=alice
	$(COMPOSE) $(CORE) run --rm --no-deps --entrypoint api-cli api token --role $(or $(ROLE),approver) --sub $(or $(SUB),dev)

# --- quality gates (CI jobs) ---------------------------------------------------

install: ## sync the uv workspace and console deps
	uv sync --all-packages --group dev
	cd console && npm ci

lint: ## ruff, prettier, clang-format (no changes)
	uv run ruff check .
	uv run ruff format --check .
	cd console && npx prettier --check "src/**/*.{ts,tsx,json,css}" && npx tsc -b

fmt: ## apply formatters
	uv run ruff check --fix .
	uv run ruff format .
	cd console && npx prettier --write "src/**/*.{ts,tsx,json,css}"

typecheck: ## mypy --strict on all Python packages
	uv run mypy .

unit: ## fast tests, no external services (SKIP_CPP=1 skips the line-sim build)
	uv run pytest -m unit --cov --cov-report=term-missing --cov-report=xml
ifndef SKIP_CPP
	$(COMPOSE) --profile test build line-sim-test && $(COMPOSE) --profile test run --rm line-sim-test
endif

# `|| [ $$? -eq 5 ]`: pytest exit 5 = no tests collected; tolerated until these layers have tests
contract: ## schemathesis against api + mock-mes OpenAPI; Avro compatibility
	uv run pytest -m contract -p no:cacheprovider || [ $$? -eq 5 ]

integration: ## testcontainers: Postgres + Redpanda end to end
	uv run pytest -m "integration or slow" || [ $$? -eq 5 ]

eval-replay: ## golden cases with recorded LLM responses; compare to eval/baseline.json
	uv run qgate-eval run --mode replay --baseline eval/baseline.json

eval-live: ## golden cases against the live model (costs money; nightly)
	uv run qgate-eval run --mode live --report eval/report.md

scan: ## dependency + image + secret scans
	uv run pip-audit
	gitleaks detect --no-git --source .
	trivy fs --severity CRITICAL --exit-code 1 .

build: ## build every image for the host platform (release.yml does multi-arch)
	$(COMPOSE) $(CORE) $(EVAL) build

goldens-freeze: ## tag the golden set (run once at the end of Phase 1)
	git tag -a goldens-v1 -m "Golden cases frozen before the agent exists"

clean: ## remove caches and build artefacts
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache .hypothesis htmlcov coverage.xml
	rm -rf services/line-sim/build console/dist console/node_modules
