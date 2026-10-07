.PHONY: setup start test lint format clean db-reset data-synth help

help: ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Python / Backend ---

setup-backend: ## Install backend dependencies using uv
	@echo "Setting up backend..."
	cd backend && pip install uv && uv pip install -e .[dev,llm]

start-backend: ## Run the FastAPI backend server
	@echo "Starting FastAPI server..."
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test-backend: ## Run backend tests
	@echo "Running tests..."
	cd backend && pytest

lint-backend: ## Run Ruff and MyPy
	@echo "Linting backend..."
	cd backend && ruff check . && mypy .

format-backend: ## Format code with Black and Ruff
	@echo "Formatting backend..."
	cd backend && black . && ruff check . --fix

db-reset: ## Reset the SQLite database and seed defaults
	@echo "Resetting database..."
	rm -f carbonshift.db
	curl -X POST http://localhost:8000/api/v1/demo/reset

# --- Node / Frontend ---

setup-frontend: ## Install frontend dependencies
	@echo "Setting up frontend..."
	cd frontend && npm install

start-frontend: ## Run the Vite frontend dev server
	@echo "Starting Vite server..."
	cd frontend && npm run dev

build-frontend: ## Build frontend for production
	@echo "Building frontend..."
	cd frontend && npm run build

# --- Global / Combined ---

setup: setup-backend setup-frontend ## Setup both backend and frontend

start: ## Run both backend and frontend (requires foreman or just run in separate tabs)
	@echo "To run both, please open two terminal tabs:"
	@echo "Tab 1: make start-backend"
	@echo "Tab 2: make start-frontend"

# --- Data Gen ---

data-synth: ## Run data generation scripts for testing
	@echo "Generating synthetic data..."
	cd ml && python scripts/generate_synthetic.py
