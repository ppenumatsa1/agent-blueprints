FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1 \
    HOME=/home/hosted \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
COPY requirements.txt .
RUN python -c "import sys; from urllib.parse import urlsplit; u=urlsplit(sys.argv[1]); assert u.scheme == 'https' and u.hostname and not (u.username or u.password or u.query or u.fragment)" "$PYTHON_PACKAGE_INDEX" \
    && test -r /etc/ssl/certs/ca-certificates.crt \
    && python -m pip install --no-cache-dir --index-url "$PYTHON_PACKAGE_INDEX" -r requirements.txt \
    && groupadd --system --gid 10001 hosted \
    && useradd --system --uid 10001 --gid hosted --create-home --home-dir /home/hosted hosted

COPY --chown=10001:10001 main.py .
COPY --chown=10001:10001 order_resolution_hosted/ order_resolution_hosted/
COPY --chown=10001:10001 app/ app/
USER 10001:10001

EXPOSE 8088
CMD ["python", "main.py"]
