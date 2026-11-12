SHELL := /bin/bash
export PATH := $(CURDIR)/.tools/bin:$(PATH)
export UV_CACHE_DIR := $(CURDIR)/.tools/uv-cache
export UV_PYTHON_INSTALL_DIR := $(CURDIR)/.tools/python
UV := $(CURDIR)/.tools/bin/uv
PYTHON := $(UV) run --directory apps/api --python 3.12
ROOT := $(CURDIR)

.PHONY: setup doctor dev test eval lint migrate seed up down widget backup restore restore-drill load-test security-test openapi api-client help

help:
	@echo "Amakuru targets: setup doctor dev test eval lint migrate seed up down widget backup restore-drill load-test security-test openapi api-client"

setup:
	@test -x $(UV) || (echo "Missing .tools/bin/uv — restore tooling first"; exit 1)
	@$(UV) python install 3.12
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		SECRET=$$(python3 -c "import secrets; print(secrets.token_urlsafe(64))"); \
		ENC=$$(python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"); \
		sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$$SECRET/" .env; \
		sed -i "s/^ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$$ENC/" .env; \
		sed -i "s/^BOOTSTRAP_ADMIN_EMAIL=.*/BOOTSTRAP_ADMIN_EMAIL=admin@example.com/" .env; \
		sed -i "s/^BOOTSTRAP_ADMIN_PASSWORD=.*/BOOTSTRAP_ADMIN_PASSWORD=ChangeMeNow123!/" .env; \
		sed -i "s/^LLM_API_KEY=.*/LLM_API_KEY=not-required-for-phase0/" .env; \
		echo "Created .env with generated secrets and bootstrap admin@example.com"; \
	fi
	@cd apps/api && $(UV) sync --python 3.12
	@docker compose up -d postgres redis
	@echo "Waiting for Postgres..."
	@for i in $$(seq 1 30); do \
		docker compose exec -T postgres pg_isready -U amakuru >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	@$(MAKE) migrate
	@$(MAKE) seed
	@echo "Setup complete. Run 'make doctor' then 'make dev'."

doctor:
	@$(PYTHON) python -m amakuru.scripts.doctor

dev:
	@docker compose up -d postgres redis
	@cd apps/api && $(UV) run --python 3.12 uvicorn amakuru.main:app --host 0.0.0.0 --port 8000 --reload

test:
	@cd apps/api && $(UV) run --python 3.12 pytest -q

eval:
	@cd apps/api && $(UV) run --python 3.12 python -m amakuru.scripts.eval_cli --tenant demo-university

widget:
	@cd apps/widget && npm install && npm run build
	@echo "Widget bundle: apps/widget/dist/amakuru-widget.js"
	@gzip -c apps/widget/dist/amakuru-widget.js | wc -c | awk '{printf "gzip size: %d bytes\n", $$1}'

lint:
	@cd apps/api && $(UV) run --python 3.12 ruff check src tests
	@cd apps/api && $(UV) run --python 3.12 ruff format --check src tests
	@cd apps/api && $(UV) run --python 3.12 mypy src
	@if [ -d apps/admin/node_modules ]; then cd apps/admin && npm run lint; else echo "Admin deps not installed; skip TS lint"; fi

migrate:
	@cd apps/api && $(UV) run --python 3.12 alembic upgrade head

seed:
	@cd apps/api && $(UV) run --python 3.12 python -m amakuru.scripts.seed

up:
	@docker compose up -d postgres redis

down:
	@docker compose down

backup:
	@chmod +x infra/backup/backup.sh
	@./infra/backup/backup.sh

restore:
	@chmod +x infra/backup/restore.sh
	@test -n "$(DUMP)" || (echo "Usage: make restore DUMP=.backups/file.sql.gz"; exit 1)
	@./infra/backup/restore.sh "$(DUMP)"

restore-drill:
	@chmod +x infra/backup/backup.sh infra/backup/restore_drill.sh
	@./infra/backup/restore_drill.sh

load-test:
	@cd apps/api && $(UV) run --python 3.12 python -m amakuru.scripts.load_test --base http://127.0.0.1:8000 --concurrency 8 --requests 40

security-test:
	@cd apps/api && $(UV) run --python 3.12 pytest -q tests/security tests/isolation

openapi:
	@cd apps/api && $(UV) run --python 3.12 python -m amakuru.scripts.export_openapi

api-client: openapi
	@cd packages/api-client && npm install && npm run generate
	@echo "Generated packages/api-client/src/schema.ts"
