FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY requirements.txt agent-framework-core.sha256 ./
COPY scripts/verify_framework_supply_chain.py scripts/
RUN mkdir -p /tmp/agent-framework-core \
    && python scripts/verify_framework_supply_chain.py \
        --output-dir /tmp/agent-framework-core \
        --index-url "$PYTHON_PACKAGE_INDEX" \
    && python -m pip install --no-cache-dir --no-deps \
        /tmp/agent-framework-core/agent_framework_core-1.26.0-py3-none-any.whl \
    && python -m pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" -r requirements.txt \
    && rm -f /tmp/agent-framework-core/agent_framework_core-1.26.0-py3-none-any.whl \
    && groupadd --system --gid 10001 blueprint \
    && useradd --system --uid 10001 --gid blueprint --no-create-home blueprint \
    && mkdir -p /var/lib/blueprint/checkpoints \
    && chown blueprint:blueprint /var/lib/blueprint/checkpoints \
    && chmod 700 /var/lib/blueprint/checkpoints

COPY --chown=blueprint:blueprint app/ app/
COPY --chown=blueprint:blueprint examples/ examples/
USER blueprint

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
