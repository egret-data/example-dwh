COMPOSE := docker compose -f dev/compose.yml

.PHONY: dev-up dev-down smoke lint fmt

dev-up:
	$(COMPOSE) up -d trino
	./dev/wait-for-trino.sh

dev-down:
	$(COMPOSE) down -v

smoke:
	./dev/smoke.sh

lint:
	uvx ruff@0.17.3 check .
	uvx ruff@0.17.3 format --check .

fmt:
	uvx ruff@0.17.3 check --fix .
	uvx ruff@0.17.3 format .
