# syntax=docker/dockerfile:1
FROM apache/airflow:3.3.2-python3.12 AS runtime

USER root
RUN python -m venv /opt/dbt-venv \
    && mkdir -p /opt/dbt_packages /tmp/dbt \
    && chown -R airflow: /opt/dbt-venv /opt/dbt_packages /tmp/dbt
USER airflow

# `make lock` only: resolve the direct requirements (Airflow side under Airflow's official
# constraints) and freeze the result into requirements*.lock. Never used by the real image.
FROM runtime AS resolve
COPY --chown=airflow requirements.txt requirements-dbt.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
      -c https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt \
    && /opt/dbt-venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

FROM runtime AS base
# Exact, complete pins: --no-deps means nothing outside the lock files can be installed.
COPY --chown=airflow requirements.lock requirements-dbt.lock /tmp/
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.lock \
    && /opt/dbt-venv/bin/pip install --no-cache-dir --no-deps -r /tmp/requirements-dbt.lock \
    && pip check \
    && /opt/dbt-venv/bin/pip check

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
