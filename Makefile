# qgate-agent — every target here maps 1:1 to a CI job. If it works here, it works in CI.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE        := docker compose
CORE           := --profile core
OBS            := --profile obs
EVAL           := --profile eval
CHAOS          := --profile chaos
LOAD           := --profile load
DEMO           := --profile demo

.PHONY: help up up-infra up-all up-airgap down logs ps demo chaos chaos-test load flows \
        install lint fmt typecheck unit contract integration eval-replay eval-live scan build console-e2e \
        token migrate goldens-freeze clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- stack -------------------------------------------------------------------

up: ## start core services (ingest, detect, agent, api, mock-mes, console + infra); `make demo` replays a line
	$(COMPOSE) $(CORE) up -d --build --wait

up-infra: ## infra only: redpanda, postgres, migrations, roles, dimension seed
	$(COMPOSE) $(CORE) up -d --wait redpanda postgres && $(COMPOSE) $(CORE) run --rm migrate && $(COMPOSE) $(CORE) run --rm roles && $(COMPOSE) $(CORE) run --rm seed

up-all: ## core + observability + prefect
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) up -d --build

up-airgap: ## core with the agent on a native Ollama (install Ollama, `ollama pull qwen2.5:7b`, then this)
	$(COMPOSE) $(CORE) up -d --build --scale agent=0
	$(COMPOSE) $(CORE) --profile airgap up -d --build agent-airgap

down: ## stop everything and drop volumes
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) $(CHAOS) $(DEMO) down -v --remove-orphans

logs: ## tail all logs
	$(COMPOSE) $(CORE) logs -f --tail=200

ps: ## container status
	$(COMPOSE) $(CORE) $(OBS) $(EVAL) ps

demo: ## export a scenario and replay it with the C++ line-sim: make demo SCENARIO=tool_wear SPEED=100
	$(COMPOSE) $(CORE) $(DEMO) build gen line-sim
	$(COMPOSE) $(CORE) up -d --wait ingest
	SCENARIO=$(or $(SCENARIO),tool_wear) $(COMPOSE) $(CORE) $(DEMO) run --rm --no-deps gen
	SCENARIO=$(or $(SCENARIO),tool_wear) REPLAY_SPEED=$(or $(SPEED),100) $(COMPOSE) $(CORE) $(DEMO) run --rm --no-deps --service-ports line-sim
	@echo "console: http://localhost:8080   api docs: http://localhost:8000/docs"

chaos: ## start core + toxiproxy with agent->mock-mes routed through the proxy
	MES_BASE_URL=http://toxiproxy:8003 $(COMPOSE) $(CORE) $(CHAOS) up -d --build

load: ## k6: 5 VUs steady + 50 burst against the api; agent in replay mode; writes eval/load.json
	MSYS_NO_PATHCONV=1 LLM_MODE=replay CASSETTE_DIR=/cassettes $(COMPOSE) $(CORE) up -d --wait agent api detect mock-mes
	uv run python loadtest/prepare.py
	$(COMPOSE) $(CORE) $(LOAD) run --rm k6
	@uv run python loadtest/check.py

chaos-test: ## run tests/chaos against a `make chaos` stack (kills containers, cuts links)
	CHAOS=1 uv run pytest tests/chaos -m chaos -v

migrate: ## apply db/migrations with dbmate
	$(COMPOSE) $(CORE) run --rm migrate up

token: ## mint a dev JWT: make token ROLE=approver SUB=alice
	$(COMPOSE) $(CORE) run --rm --no-deps --entrypoint api-cli api token --role $(or $(ROLE),approver) --sub $(or $(SUB),dev)

# --- quality gates (CI jobs) ---------------------------------------------------

install: ## sync the uv workspace and console deps
	uv sync --all-packages --group dev
	cd console && npm ci

lint: ## ruff, prettier, eslint, tsc (no changes)
	uv run ruff check .
	uv run ruff format --check .
	uv run python scripts/check_links.py
	cd console && npx prettier --check "src/**/*.{ts,tsx,json,css}" "e2e/*.ts" "*.ts" && npx eslint . && npx tsc -b

fmt: ## apply formatters
	uv run ruff check --fix .
	uv run ruff format .
	cd console && npx prettier --write "src/**/*.{ts,tsx,json,css}" "e2e/*.ts" "*.ts"

console-e2e: ## Playwright smoke: qgate-eval serve (one golden at the gate) + built console
	cd console && npx playwright test

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

eval-replay: ## golden cases with recorded LLM responses; compare to eval/baseline.json (needs Docker)
	LLM_MODEL=$${LLM_MODEL:-claude-haiku-4-5} uv run qgate-eval run --mode replay --baseline eval/baseline.json --report eval/report.md

flows: ## register and run the Prefect flows locally: replay-scenario, nightly-eval (replay), publish-report
	$(COMPOSE) $(CORE) $(EVAL) up -d --build --wait prefect-server eval-db prefect-worker
	$(COMPOSE) $(CORE) $(EVAL) run --rm prefect-deploy
	$(COMPOSE) $(CORE) $(EVAL) run --rm prefect-deploy deployment run 'replay-scenario/replay-scenario' --param scenario=clean_baseline --watch
	$(COMPOSE) $(CORE) $(EVAL) run --rm prefect-deploy deployment run 'nightly-eval/nightly-eval' --param mode=replay --watch
	$(COMPOSE) $(CORE) $(EVAL) run --rm prefect-deploy deployment run 'publish-report/publish-report' --watch
	@echo "prefect ui: http://localhost:4200   site: eval/site/index.html"

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
