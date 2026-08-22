# ------------------------------------------------------------
# Just Make It MCP (JMIM) Makefile
#
# Host-side developer surface for installing, validating,
# testing, packaging, and running JMIM locally or in Docker.
# Run from the repository root.
# ------------------------------------------------------------

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Tooling ------------------------------------------------------
UV ?= uv
UV_DEV_RUN := $(UV) run --extra dev
DOCKER ?= docker
DOCKER_COMPOSE ?= docker compose
IMAGE ?= make-mcp:local
PYTEST ?= $(UV_DEV_RUN) python -m pytest
PYTEST_ARGS ?=
PYTEST_BASE := PYTEST_ADDOPTS= $(PYTEST) -c pyproject.toml

# CLI inputs ---------------------------------------------------
TASK ?=
ARGS ?=
TEST ?=
TAG ?=

# Workspace archive --------------------------------------------
WORKSPACE_NAME ?= $(notdir $(CURDIR))
WORKSPACE_PARENT ?= $(abspath $(CURDIR)/..)
WORKSPACE_ZIP ?= $(WORKSPACE_PARENT)/$(WORKSPACE_NAME).zip
ZIPIGNORE ?= .zipignore
ZIP_MAX_FILES ?= 5000

# Terminal colors ---------------------------------------------
RESET   := \033[0m
BOLD    := \033[1m
RED     := \033[31m
GREEN   := \033[32m
YELLOW  := \033[33m
BLUE    := \033[34m
MAGENTA := \033[35m
CYAN    := \033[36m

.PHONY: \
	help env prerequisites install install-runtime install-cli lock \
	format format-check lint \
	test test-count test-unit test-integration test-security test-one test-last-failed test-verbose \
	check smoke ci \
	list list-json describe describe-json doctor doctor-json run run-json serve \
	package package-list package-smoke release-check release-check-dist zip-workspace \
	docker-build docker-doctor docker-list docker-check docker-serve docker-shell \
	clean distclean

##@General

help: ## Show categorized help
	@printf "\n$(BOLD)Just Make It MCP (JMIM)$(RESET)\n"
	@printf "\nDeveloper commands for the JMIM repository.\n"
	@printf "Typical flow: $(CYAN)make install$(RESET) -> $(MAGENTA)make check$(RESET)\n\n"
	@awk \
		-v reset="$(RESET)" \
		-v bold="$(BOLD)" \
		-v green="$(GREEN)" \
		-v yellow="$(YELLOW)" \
		-v blue="$(BLUE)" \
		-v magenta="$(MAGENTA)" \
		-v cyan="$(CYAN)" \
		'function section_color(name) { \
			if (name == "General") return cyan; \
			if (name == "Setup") return cyan; \
			if (name == "Quality") return magenta; \
			if (name == "Tests") return magenta; \
			if (name == "Validation") return yellow; \
			if (name == "JMIM CLI") return blue; \
			if (name == "Packaging") return yellow; \
			if (name == "Docker") return green; \
			if (name == "Maintenance") return cyan; \
			return cyan; \
		} \
		function flush_section(    i, j, tmp, color) { \
			if (section == "") return; \
			color = section_color(section); \
			printf "\n%s%s%s%s\n", bold, color, section, reset; \
			for (i = 1; i <= count; i++) { \
				for (j = i + 1; j <= count; j++) { \
					if (names[j] < names[i]) { \
						tmp = names[i]; names[i] = names[j]; names[j] = tmp; \
						tmp = descs[i]; descs[i] = descs[j]; descs[j] = tmp; \
					} \
				} \
			} \
			for (i = 1; i <= count; i++) { \
				printf "  %s%-24s%s %s\n", green, names[i], reset, descs[i]; \
			} \
			delete names; delete descs; count = 0; \
		} \
		BEGIN { FS = ":.*## "; section = ""; count = 0; } \
		/^##@/ { flush_section(); section = substr($$0, 4); next; } \
		/^[a-zA-Z0-9][a-zA-Z0-9_.-]*:.*## / { count++; names[count] = $$1; descs[count] = $$2; next; } \
		END { flush_section(); }' $(MAKEFILE_LIST)
	@printf "\n"

env: ## Show local tool versions
	@printf "$(BOLD)Environment$(RESET)\n"
	@printf "%-12s " "Python:"; python3 --version
	@printf "%-12s " "uv:"; $(UV) --version
	@printf "%-12s " "Make:"; make --version | head -n 1
	@printf "%-12s " "Docker:"; if command -v $(DOCKER) >/dev/null 2>&1; then $(DOCKER) --version; else printf "not installed\n"; fi

##@Setup

prerequisites: ## Check Python 3.11+, uv, make, and Git
	@command -v python3 >/dev/null || { printf "$(RED)error: python3 is required$(RESET)\n"; exit 1; }
	@python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
	@command -v $(UV) >/dev/null || { printf "$(RED)error: uv is required (https://docs.astral.sh/uv/)$(RESET)\n"; exit 1; }
	@command -v make >/dev/null || { printf "$(RED)error: make is required$(RESET)\n"; exit 1; }
	@command -v git >/dev/null || { printf "$(RED)error: git is required$(RESET)\n"; exit 1; }
	@printf "$(GREEN)prerequisites: ok$(RESET)\n"

install: prerequisites ## Install/sync the development environment
	$(UV) sync --extra dev

install-runtime: prerequisites ## Install/sync runtime dependencies only
	$(UV) sync

install-cli: prerequisites ## Install or replace make-mcp as a uv tool
	$(UV) tool install --force .

lock: prerequisites ## Refresh uv.lock from pyproject.toml
	$(UV) lock

##@Quality

format: ## Format Python sources and tests with Ruff
	$(UV_DEV_RUN) ruff format .

format-check: ## Check formatting without modifying files
	$(UV_DEV_RUN) ruff format --check .

lint: ## Run Ruff lint checks
	$(UV_DEV_RUN) ruff check .

##@Tests

test: ## Run the complete test suite
	$(PYTEST_BASE) tests $(PYTEST_ARGS)

test-count: ## Show the number of collected tests
	@$(PYTEST_BASE) -o addopts="" --collect-only -q tests | tail -n 1

test-unit: ## Run unit tests
	$(PYTEST_BASE) tests/unit $(PYTEST_ARGS)

test-integration: ## Run integration tests
	$(PYTEST_BASE) tests/integration $(PYTEST_ARGS)

test-security: ## Run security regression tests
	$(PYTEST_BASE) tests/security $(PYTEST_ARGS)

test-one: ## Run one test/file: make test-one TEST=tests/unit/test_x.py::test_name
	@test -n "$(TEST)" || { printf "$(RED)error: TEST is required$(RESET)\n"; exit 2; }
	$(PYTEST_BASE) "$(TEST)" $(PYTEST_ARGS)

test-last-failed: ## Re-run only tests that failed on the previous run
	$(PYTEST_BASE) --lf tests $(PYTEST_ARGS)

test-verbose: ## Run the complete test suite with verbose output
	$(PYTEST_BASE) -vv tests $(PYTEST_ARGS)

##@Validation

check: format-check lint test doctor ## Run local release-blocking checks

smoke: prerequisites ## Smoke-check CLI bootstrap, diagnostics, and task discovery
	@$(UV) run make-mcp --help >/dev/null
	$(UV) run make-mcp doctor
	$(UV) run make-mcp list

ci: check package ## Run checks and build distributions

##@JMIM CLI

list: ## List targets exposed by JMIM
	$(UV) run make-mcp list

list-json: ## List exposed targets as JSON
	$(UV) run make-mcp list --json

describe: ## Describe a target: make describe TASK=test
	@test -n "$(TASK)" || { printf "$(RED)error: TASK is required (example: make describe TASK=test)$(RESET)\n"; exit 2; }
	$(UV) run make-mcp describe "$(TASK)"

describe-json: ## Describe a target as JSON: make describe-json TASK=test
	@test -n "$(TASK)" || { printf "$(RED)error: TASK is required$(RESET)\n"; exit 2; }
	$(UV) run make-mcp describe "$(TASK)" --json

doctor: ## Run repository/configuration diagnostics
	$(UV) run make-mcp doctor

doctor-json: ## Run diagnostics as JSON
	$(UV) run make-mcp doctor --json

run: ## Run an exposed target: make run TASK=test [ARGS='KEY=value ...']
	@test -n "$(TASK)" || { printf "$(RED)error: TASK is required (example: make run TASK=test)$(RESET)\n"; exit 2; }
	$(UV) run make-mcp run "$(TASK)" $(ARGS)

run-json: ## Run an exposed target with JSON result output
	@test -n "$(TASK)" || { printf "$(RED)error: TASK is required$(RESET)\n"; exit 2; }
	$(UV) run make-mcp run "$(TASK)" $(ARGS) --json

serve: ## Start the MCP stdio server locally
	$(UV) run make-mcp serve

##@Packaging

package: ## Build a clean wheel and source distribution into dist/
	rm -rf dist
	$(UV) build

package-smoke: ## Install and exercise the built wheel in a clean Linux container
	@test -n "$$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit 2>/dev/null)" || { printf "$(RED)error: build dist/ first with make package$(RESET)\n"; exit 2; }
	$(DOCKER) run --rm -v "$(CURDIR)/dist:/dist:ro" python:3.13-slim sh -euxc '\
		apt-get update >/dev/null; \
		apt-get install -y --no-install-recommends make >/dev/null; \
		python -m pip install --disable-pip-version-check --no-cache-dir /dist/*.whl >/dev/null; \
		make-mcp --version; \
		tmp="$$(mktemp -d)"; \
		printf "hello: ## Clean-container package smoke\n\t@echo smoke-ok\n" > "$$tmp/Makefile"; \
		cd "$$tmp"; \
		make-mcp doctor; \
		make-mcp list | grep -q "hello"; \
		make-mcp run hello | grep -q "smoke-ok"'

release-check: ## Validate TAG against version and changelog: make release-check TAG=v0.1.0
	@test -n "$(TAG)" || { printf "$(RED)error: TAG is required$(RESET)\n"; exit 2; }
	python3 scripts/check_release.py --tag "$(TAG)"

release-check-dist: ## Validate TAG plus the built wheel/sdist metadata
	@test -n "$(TAG)" || { printf "$(RED)error: TAG is required$(RESET)\n"; exit 2; }
	python3 scripts/check_release.py --tag "$(TAG)" --dist dist

package-list: ## Show generated distribution artifacts
	@find dist -maxdepth 1 -type f -printf '%f\n' 2>/dev/null | sort || true

zip-workspace: ## Create a shareable workspace ZIP honoring .gitignore and .zipignore
	@command -v git >/dev/null || { printf "$(RED)error: git is required$(RESET)\n"; exit 1; }
	@command -v zip >/dev/null || { printf "$(RED)error: zip is required$(RESET)\n"; exit 1; }
	@git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { printf "$(RED)error: run from a Git repository$(RESET)\n"; exit 1; }
	@printf "$(BOLD)$(CYAN)Creating workspace archive$(RESET)\n"
	@printf "$(BLUE)%-16s$(RESET) %s\n" "Source:" "$(CURDIR)"
	@printf "$(BLUE)%-16s$(RESET) %s\n" "Output:" "$(WORKSPACE_ZIP)"
	@printf "$(BLUE)%-16s$(RESET) %s\n" "Ignore:" ".gitignore + $(ZIPIGNORE)"
	@included_files="$$(mktemp)"; \
	trap 'rm -f "$$included_files"' EXIT; \
	git ls-files --cached --others --exclude-standard -z | \
	while IFS= read -r -d '' file; do \
		if [ -f "$(ZIPIGNORE)" ] && git -c core.excludesFile="$$(pwd)/$(ZIPIGNORE)" check-ignore --no-index -q -- "$$file"; then \
			continue; \
		fi; \
		printf '%s\n' "$$file"; \
	done | sort -u > "$$included_files"; \
	file_count="$$(wc -l < "$$included_files" | tr -d ' ')"; \
	if [ "$$file_count" -eq 0 ]; then \
		printf "$(YELLOW)No files matched.$(RESET)\n"; \
		exit 0; \
	fi; \
	if [ "$$file_count" -gt "$(ZIP_MAX_FILES)" ]; then \
		printf "$(RED)Refusing to zip %s files. ZIP_MAX_FILES=%s.$(RESET)\n" "$$file_count" "$(ZIP_MAX_FILES)"; \
		exit 1; \
	fi; \
	mkdir -p "$$(dirname "$(WORKSPACE_ZIP)")"; \
	rm -f "$(WORKSPACE_ZIP)"; \
	zip -q -@ "$(WORKSPACE_ZIP)" < "$$included_files"; \
	printf "$(GREEN)Archive created (%s files): %s$(RESET)\n" "$$file_count" "$(WORKSPACE_ZIP)"

##@Docker

docker-build: ## Build the local runtime image
	$(DOCKER) build -t $(IMAGE) .

docker-doctor: ## Run JMIM diagnostics through Compose
	$(DOCKER_COMPOSE) run --rm make-mcp doctor

docker-list: ## List exposed tasks through Compose
	$(DOCKER_COMPOSE) run --rm make-mcp list

docker-check: docker-build docker-doctor docker-list ## Build image and verify JMIM in Docker

docker-serve: ## Start the MCP stdio server through Compose
	$(DOCKER_COMPOSE) run --rm -T make-mcp serve

docker-shell: ## Open a shell in the local runtime image
	$(DOCKER) run --rm -it --entrypoint /bin/sh -v "$(CURDIR):/workspace" -w /workspace $(IMAGE)

##@Maintenance

clean: ## Remove generated test, lint, and build artifacts
	rm -rf .pytest_cache .ruff_cache dist build
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

distclean: clean ## Also remove the local uv environment and JMIM locks
	rm -rf .venv .make-mcp/locks
