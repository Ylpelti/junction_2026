# Pinned multi-platform base; update deliberately with dependency locks.
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    CANCERSIGNAL_EXTRACTION=off CANCERSIGNAL_EXTRACTION_ALLOW_LIVE=false \
    CANCERSIGNAL_EXPLANATION=deterministic CANCERSIGNAL_EXPLANATION_ALLOW_LIVE=false \
    CANCERSIGNAL_RETRIEVAL=auto CANCERSIGNAL_RETRIEVAL_MODEL_CACHE=/var/cache/cancersignal/models \
    CANCERSIGNAL_EXTRACTION_CACHE_DIR=/var/cache/cancersignal/extraction \
    CANCERSIGNAL_EXPLANATION_CACHE_DIR=/var/cache/cancersignal/explanation \
    HF_HUB_DISABLE_TELEMETRY=1 TOKENIZERS_PARALLELISM=false
WORKDIR /app
COPY deploy/requirements.lock /app/deploy/requirements.lock
RUN pip install -r deploy/requirements.lock
COPY . /app
RUN pip install --no-deps --no-build-isolation . && \
    useradd --uid 10001 --create-home app && \
    mkdir -p /var/cache/cancersignal/models /var/cache/cancersignal/extraction /var/cache/cancersignal/explanation && \
    chown -R app:app /var/cache/cancersignal && chmod +x /app/deploy/start.sh
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=7s --start-period=30s --retries=3 \
    CMD python -c 'import os,urllib.request; urllib.request.urlopen("http://127.0.0.1:"+os.getenv("PORT","8000")+"/ready",timeout=6)'
ENTRYPOINT ["/app/deploy/start.sh"]

# Optional heavyweight image. Model download is an explicit preparation step.
FROM base AS hybrid
USER root
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r deploy/requirements-hybrid.lock
USER app
ENV CANCERSIGNAL_RETRIEVAL=hybrid

# The default build stays small and supports lexical fallback.
FROM base AS runtime
