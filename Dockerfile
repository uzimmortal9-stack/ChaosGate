# ChaosGate control plane.
#
# Multi-stage: dependencies are resolved into a wheel layer, then copied into
# a slim runtime that carries git (for cloning targets) and the Docker CLI
# (so the container stage can build images through a mounted socket).

FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /wheels

COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=5000

# git clones targets; docker-cli drives the container stage; curl is for probes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates curl gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && chmod a+r /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
 && apt-get purge -y gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deps /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY . .

RUN mkdir -p data/workspaces data/artifacts \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin gate \
 && chown -R gate:gate /app

# Kept as root by default: the Docker stage needs access to the mounted
# socket, which is typically root-owned. Set `user: "10001"` in compose to
# drop privileges when you do not need container builds.

EXPOSE 5000

HEALTHCHECK --interval=25s --timeout=6s --start-period=20s --retries=4 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/healthz', timeout=5).status==200 else 1)"

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "16", \
     "--timeout", "1800", "--graceful-timeout", "30", "--access-logfile", "-", "app:app"]
