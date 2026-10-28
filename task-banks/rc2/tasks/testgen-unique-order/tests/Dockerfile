FROM ubuntu:24.04

# The container gate resolves and freezes the built image ID and package versions.
# This source recipe alone is not an immutable environment lock.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pytest \
    && rm -rf /var/lib/apt/lists/*
COPY . /tests
RUN chmod -R a-w /tests && mkdir -p /app /logs/verifier && chmod 1777 /app
ENV PYTHONPATH=/app/repo PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONUTF8=1
WORKDIR /app
