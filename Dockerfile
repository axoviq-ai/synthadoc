# syntax=docker/dockerfile:1
# SPDX-License-Identifier: AGPL-3.0-or-later

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# SYNTHADOC_VERSION: pinned by CI to the exact release tag (e.g. 1.3.3).
# Omit the build-arg for local builds — source is installed directly instead.
ARG SYNTHADOC_VERSION=

# SYNTHADOC_EXTRAS: optional dependency groups. "vectors" (default) adds
# semantic search: fastembed plus the embedding model, baked into the image so
# containers never download it at runtime. Build with SYNTHADOC_EXTRAS= for a
# smaller BM25-only image.
ARG SYNTHADOC_EXTRAS=vectors
ENV FASTEMBED_CACHE_PATH=/opt/synthadoc/models

# Copy source for local builds (filtered by .dockerignore).
# CI builds ignore this layer and install from PyPI using SYNTHADOC_VERSION.
COPY . /build/source/

# Install synthadoc and all runtime deps.
# Local build  (no SYNTHADOC_VERSION): install from the copied source tree.
# CI build (SYNTHADOC_VERSION set):    install exact release from PyPI.
# --user installs to /root/.local; copied into the runtime stage below.
RUN pip install --no-cache-dir --upgrade pip \
 && EXTRAS="${SYNTHADOC_EXTRAS:+[$SYNTHADOC_EXTRAS]}" \
 && if [ -n "$SYNTHADOC_VERSION" ]; then \
      pip install --no-cache-dir --user "synthadoc${EXTRAS}==$SYNTHADOC_VERSION"; \
    else \
      pip install --no-cache-dir --user "/build/source${EXTRAS}"; \
    fi

# Download the embedding model now (same loader the server uses), so semantic
# search works offline and new containers start without a download.
RUN mkdir -p "$FASTEMBED_CACHE_PATH" \
 && if python -c "import fastembed" 2>/dev/null; then \
      python -c "from synthadoc.storage.search import load_embed_model; load_embed_model()"; \
    fi

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user (uid 1000) — standard container hardening.
# A real, user-owned home is required: CLI commands such as `synthadoc install`
# write ~/.synthadoc/ (registry, default wiki), which fails if the home
# directory is missing or root-owned.
RUN groupadd --gid 1000 synthadoc \
 && useradd --uid 1000 --gid synthadoc --create-home synthadoc

# Copy installed packages (and the embedding model, if built in) from builder stage.
COPY --from=builder --chown=synthadoc:synthadoc /root/.local /home/synthadoc/.local
COPY --from=builder --chown=synthadoc:synthadoc /opt/synthadoc/models /opt/synthadoc/models
ENV FASTEMBED_CACHE_PATH=/opt/synthadoc/models

# Wiki volume — user mounts their wiki root here at runtime.
RUN mkdir /wiki && chown synthadoc:synthadoc /wiki
VOLUME ["/wiki"]
WORKDIR /wiki

# Expose the default synthadoc server port.
EXPOSE 7070

# Health check — /health responds in < 1 s when the server is ready.
# Polls the port from the wiki's config.toml (falls back to 7070), so wikis
# installed on 7071, 7072, … report healthy without overriding the check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
    "import tomllib, urllib.request; c = tomllib.load(open('/wiki/.synthadoc/config.toml', 'rb')); urllib.request.urlopen('http://localhost:%d/health' % c.get('server', {}).get('port', 7070))" \
    || exit 1

USER synthadoc

# PATH for user-installed binaries.
ENV PATH="/home/synthadoc/.local/bin:$PATH"

# Default wiki for `docker exec <container> synthadoc <cmd>` — no -w needed.
ENV SYNTHADOC_WIKI=/wiki

# Start the server bound to all interfaces so the mapped port is reachable.
# -w /wiki bypasses the registry (not used inside the container).
# --host 0.0.0.0 overrides the config default of 127.0.0.1.
# Default mode (no --http-only) enables the /mcp HTTP endpoint alongside the
# HTTP API and Web UI — all three are served on the same port.
CMD ["synthadoc", "serve", "-w", "/wiki", "--host", "0.0.0.0"]
