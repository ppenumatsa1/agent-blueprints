FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /offline
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/agent-framework-core.sha256 ./
COPY backend/scripts/verify_framework_supply_chain.py scripts/
RUN python -m pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" uv==0.9.26 \
    && python scripts/verify_framework_supply_chain.py --index-url "$PYTHON_PACKAGE_INDEX" \
    && uv export --locked --no-dev --no-emit-project --no-header --no-annotate > requirements-lock.txt \
    && uv pip install --system --no-cache --require-hashes --default-index "$PYTHON_PACKAGE_INDEX" -r requirements-lock.txt \
    && python -m pip uninstall -y uv \
    && rm requirements-lock.txt
COPY backend/app/__init__.py app/__init__.py
COPY backend/app/domain/__init__.py backend/app/domain/models.py app/domain/
COPY backend/app/workflows/__init__.py backend/app/workflows/workflow.py app/workflows/
COPY scripts/offline/runner.py runner.py
COPY scripts/offline/LICENSE LICENSE
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/python", "-I", "-B", "/offline/runner.py"]
