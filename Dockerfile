# nameproof: EPC Verification of Payee responder
#   docker build -t nameproof .
#   docker run -p 8080:8080 -e NAMEPROOF_DIRECTORY=json:/data/accounts.json \
#     -v "$PWD/examples:/data:ro" nameproof
# Base image pinned by digest (python:3.13-slim); dependencies installed from uv.lock
# with hash checking, so every build gets exactly the tested versions.
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN pip install "uv==0.13.7" \
 && uv export --frozen --no-dev --extra service --no-emit-project --no-header \
      --format requirements-txt -o /tmp/requirements.txt \
 && pip install --require-hashes -r /tmp/requirements.txt \
 && pip install --no-deps . \
 && pip uninstall -y uv \
 && rm -rf /build /tmp/requirements.txt

RUN useradd --create-home --uid 10001 nameproof
USER nameproof
WORKDIR /home/nameproof

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"]
ENTRYPOINT ["nameproof", "serve", "--host", "0.0.0.0", "--port", "8080"]
