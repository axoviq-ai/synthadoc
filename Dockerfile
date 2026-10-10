# syntax=docker/dockerfile:1
# SPDX-License-Identifier: AGPL-3.0-or-later

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# SYNTHADOC_VERSION: pinned by CI to the exact release tag (e.g. 1.3.3).
# Omit the build-arg for local builds — installs the latest published version.
ARG SYNTHADOC_VERSION=

# Install synthadoc and all runtime deps.
# --user installs to /root/.local; copied into the runtime stage below.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir --user "synthadoc${SYNTHADOC_VERSION:+==$SYNTHADOC_VERSION}"

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user (uid 1000) — standard container hardening.
RUN groupadd --gid 1000 synthadoc \
 && useradd --uid 1000 --gid synthadoc --no-create-home synthadoc

# Copy installed packages from builder stage.
COPY --from=builder /root/.local /home/synthadoc/.local

# Wiki volume — user mounts their wiki root here at runtime.
RUN mkdir /wiki && chown synthadoc:synthadoc /wiki
VOLUME ["/wiki"]
WORKDIR /wiki

# Expose the default synthadoc server port.
EXPOSE 7070

# Health check — /health responds in < 1 s when the server is ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:7070/health')" \
    || exit 1

USER synthadoc

# PATH for user-installed binaries.
ENV PATH="/home/synthadoc/.local/bin:$PATH"

# Start the server bound to all interfaces so the mapped port is reachable.
# -w /wiki bypasses the registry (not used inside the container).
# --host 0.0.0.0 overrides the config default of 127.0.0.1.
# Default mode (no --http-only) enables the /mcp HTTP endpoint alongside the
# HTTP API and Web UI — all three are served on the same port.
CMD ["synthadoc", "serve", "-w", "/wiki", "--host", "0.0.0.0"]
