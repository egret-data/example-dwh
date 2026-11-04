# syntax=docker/dockerfile:1
FROM apache/airflow:3.3.2-python3.12 AS base

USER root
RUN python -m venv /opt/dbt-venv \
    && mkdir -p /opt/dbt_packages /tmp/dbt \
    && chown -R airflow: /opt/dbt-venv /opt/dbt_packages /tmp/dbt
USER airflow

# Airflow side: pinning apache-airflow stops pip from up/downgrading the base install.
COPY --chown=airflow requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# dbt side: separate venv so dbt and Airflow never share dependency pins.
COPY --chown=airflow requirements-dbt.txt /tmp/requirements-dbt.txt
RUN /opt/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

# DBT_SEND_ANONYMOUS_USAGE_STATS=false: no .user.yml cookie written into the read-only profiles dir.
ENV DBT_EXECUTABLE_PATH=/opt/dbt-venv/bin/dbt \
    DBT_PACKAGES_INSTALL_PATH=/opt/dbt_packages \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

# Bake dbt packages; git-sync delivers models but never runs `dbt deps`.
# Runs as root: `dbt deps` rmtree()s the install dir itself, which needs write access to /opt.
COPY dags/dbt/dbt_project.yml dags/dbt/packages.yml dags/dbt/package-lock.yml /tmp/dbt-deps/
USER root
RUN cd /tmp/dbt-deps && /opt/dbt-venv/bin/dbt deps \
    && rm -rf /tmp/dbt-deps \
    && chown -R airflow: /opt/dbt_packages /tmp/dbt
USER airflow

FROM base AS dev
RUN pip install --no-cache-dir pytest==9.2.0 \
    && /opt/dbt-venv/bin/pip install --no-cache-dir pytest==9.2.0

FROM base AS prod
