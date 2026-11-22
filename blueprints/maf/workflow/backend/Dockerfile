FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" -r requirements.txt \
    && groupadd --system --gid 10001 blueprint \
    && useradd --system --uid 10001 --gid blueprint --no-create-home blueprint \
    && mkdir -p /var/lib/blueprint/checkpoints \
    && chown blueprint:blueprint /var/lib/blueprint/checkpoints \
    && chmod 700 /var/lib/blueprint/checkpoints

COPY --chown=blueprint:blueprint app/ app/
COPY --chown=blueprint:blueprint examples/ examples/
COPY --chown=blueprint:blueprint migrations/ migrations/
USER blueprint

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
