COMPOSE := docker compose -f dev/compose.yml
RUN := $(COMPOSE) run --rm airflow

.PHONY: dev-up dev-down smoke lint fmt image dbt-parse

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

image:
	docker build --target dev -t example-dwh-airflow:dev .

dbt-parse:
	$(RUN) 'cd dags/dbt && $$DBT_EXECUTABLE_PATH parse'
