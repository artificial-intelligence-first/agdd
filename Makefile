.PHONY: help install test test-unit test-agents test-integration \
        setup-flowrunner clean-flowrunner agent-run flow-run \
        docs-check vendor-check build install-dev \
        api-server api-test api-examples bench bench-cache

# Default target
help:
	@echo "AGDD Framework - Make targets"
	@echo ""
	@echo "Development:"
	@echo "  make install          - Install dependencies (uv sync)"
	@echo "  make install-dev      - Install with dev dependencies"
	@echo "  make build            - Build distribution packages"
	@echo ""
	@echo "Testing:"
	@echo "  make test             - Run fast suite (default, excludes slow)"
	@echo "  make test-all         - Run all tests (fast + slow)"
	@echo "  make test-slow        - Run slow tests only"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-agents      - Run agent tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-coverage    - Run tests with coverage report"
	@echo ""
	@echo "Quality Checks:"
	@echo "  make docs-check       - Validate documentation"
	@echo "  make vendor-check     - Verify vendored assets"
	@echo ""
	@echo "Agent Execution:"
	@echo "  make agent-run        - Run sample MAG execution"
	@echo "  make flow-run         - Run sample flow (requires Flow Runner)"
	@echo ""
	@echo "HTTP API:"
	@echo "  make api-server       - Start HTTP API server"
	@echo "  make api-test         - Run API integration tests"
	@echo "  make api-examples     - Show API usage examples"
	@echo ""
	@echo "Flow Runner:"
	@echo "  make setup-flowrunner - Setup Flow Runner (one-time)"
	@echo "  make clean-flowrunner - Remove Flow Runner installation"
	@echo ""
	@echo "Benchmarks:"
	@echo "  make bench            - Run benchmark harness"
	@echo "  make bench-cache      - Run cache benchmark"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            - Remove build artifacts and caches"
	@echo ""

# Development
install:
	uv sync

install-dev:
	uv sync --extra dev

# One-time developer environment setup
dev-setup:
	uv sync --extra dev

build:
	uv build

# Testing
test:
	uv run --no-sync -m pytest -q

test-all:
	PYTEST_ADDOPTS="-k 'slow or not slow'" uv run --no-sync -m pytest -q

test-slow:
	uv run --no-sync -m pytest -q -m slow -k ""

test-unit:
	uv run --no-sync -m pytest tests/unit/ -v -n auto

test-agents:
	uv run --no-sync -m pytest tests/agents/ -v -n auto

test-integration:
	uv run --no-sync -m pytest tests/integration/ -v -n auto

test-coverage:
	uv run -m pytest --cov=agdd --cov-report=term-missing --cov-report=html

test-mcp:
	@echo "Running MCP tests (sequential mode with proper cleanup)..."
	PYTEST_ADDOPTS='-n 0 --import-mode=importlib -m "slow or not slow"' uv run -m pytest tests/mcp -q --tb=short -k 'slow or not slow'

# Quality Checks
docs-check:
	uv run python ops/tools/check_docs.py

vendor-check:
	uv run python ops/tools/verify_vendor.py

# Agent Execution Examples
agent-run:
	@echo "Running sample MAG execution..."
	@echo '{"role":"Senior Engineer","level":"Senior","experience_years":8}' | \
		uv run agdd agent run offer-orchestrator-mag

flow-run:
	@echo "Running sample flow..."
	@if [ ! -d ".flow-runner" ]; then \
		echo "Error: Flow Runner not installed. Run 'make setup-flowrunner' first."; \
		exit 1; \
	fi
	@source ops/scripts/flowrunner-env.sh && \
		uv run agdd flow run examples/flowrunner/prompt_flow.yaml

# Flow Runner Setup
setup-flowrunner:
	@echo "Setting up Flow Runner..."
	@./ops/scripts/setup-flowrunner.sh

clean-flowrunner:
	@echo "Removing Flow Runner installation..."
	@rm -rf .flow-runner
	@rm -f ops/scripts/flowrunner-env.sh
	@echo "Flow Runner removed."

# HTTP API
api-server:
	@echo "Starting HTTP API server..."
	@./ops/scripts/run-api-server.sh

api-test:
	@echo "Running API integration tests..."
	@uv run -m pytest tests/integration/test_api_*.py -v

api-examples:
	@echo "API Usage Examples"
	@echo "=================="
	@echo ""
	@echo "Start server:    make api-server"
	@echo "Run tests:       make api-test"
	@echo ""
	@echo "List agents:     curl http://localhost:8000/api/v1/agents | jq"
	@echo "Run agent:       curl -X POST http://localhost:8000/api/v1/agents/offer-orchestrator-mag/run \\"
	@echo "                      -H 'Content-Type: application/json' \\"
	@echo "                      -d '{\"payload\": {\"role\":\"Engineer\",\"level\":\"Senior\"}}' | jq"
	@echo "Get run summary: curl http://localhost:8000/api/v1/runs/<RUN_ID> | jq"
	@echo "Stream logs:     curl http://localhost:8000/api/v1/runs/<RUN_ID>/logs?follow=true"
	@echo ""
	@echo "Docs:            http://localhost:8000/docs"
	@echo ""
	@echo "For more examples: ./examples/api/curl_examples.sh"

# Cleanup
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf dist/ build/ *.egg-info
	@rm -rf .pytest_cache __pycache__
	@rm -rf htmlcov .coverage
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@echo "Clean complete."

# Benchmarks (optional)
bench-cache:
	@echo "Running cache benchmark..."
	@uv run python benchmarks/cache_benchmark.py

bench:
	@echo "Running benchmark harness..."
	@uv run python benchmarks/harness.py
