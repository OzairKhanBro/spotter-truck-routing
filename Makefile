# Weather-aware truck routing — common tasks. Run `make` or `make help` for the list.
.DEFAULT_GOAL := help
.PHONY: help install dev api web migrate test test-api test-web lint fmt check build serve-prod \
	docker-build docker-up docker-down docker-logs clean

API := backend
WEB := frontend
API_PORT ?= 8000
WEB_PORT ?= 5173

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install backend and frontend dependencies, apply migrations
	cd $(API) && uv sync
	cd $(WEB) && bun install
	cd $(API) && uv run python manage.py migrate

dev: ## Run API and web app together (Ctrl-C stops both)
	@$(MAKE) -j2 api web

api: ## Run the Django API on :8000
	cd $(API) && uv run python manage.py migrate --verbosity 0 && uv run python manage.py runserver $(API_PORT)

web: ## Run the Vite dev server on :5173 (proxies /api to :8000)
	cd $(WEB) && bun run dev --port $(WEB_PORT)

migrate: ## Apply database migrations
	cd $(API) && uv run python manage.py migrate

test: test-api test-web ## Run all tests

test-api: ## Run backend tests
	cd $(API) && uv run pytest -q

test-web: ## Run frontend tests
	cd $(WEB) && bun run test

lint: ## Lint and type-check both apps
	cd $(API) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB) && bun run check

fmt: ## Auto-format and fix lint where possible
	cd $(API) && uv run ruff check --fix . && uv run ruff format .
	cd $(WEB) && bunx vp check --fix

check: lint test ## Lint, type-check and test everything

build: ## Build the SPA into backend/frontend_dist
	cd $(WEB) && bun run build
	rm -rf $(API)/frontend_dist && cp -r $(WEB)/dist $(API)/frontend_dist

serve-prod: build ## Serve API + built SPA with gunicorn on :8000, like production
	cd $(API) && DJANGO_DEBUG=0 uv run python manage.py collectstatic --noinput --verbosity 0 \
		&& uv run python manage.py migrate --verbosity 0 \
		&& DJANGO_DEBUG=0 uv run gunicorn config.wsgi --bind 0.0.0.0:$(API_PORT) --workers 2 --threads 4 --timeout 120

docker-build: ## Build the production image
	docker compose build

docker-up: ## Start the app in Docker on :8000 (detached)
	docker compose up -d --build

docker-down: ## Stop the Docker app
	docker compose down

docker-logs: ## Follow the Docker app logs
	docker compose logs -f

clean: ## Remove build output, caches and the local database
	rm -rf $(WEB)/dist $(API)/frontend_dist $(API)/staticfiles $(API)/db.sqlite3
	find $(API) -name __pycache__ -type d -prune -exec rm -rf {} +
