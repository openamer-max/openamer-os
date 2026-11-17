# OpenAmer-OS — Userspace-Image (Ebene 2)
#
# Ein minimales Debian mit allem, was der Agent zum Arbeiten braucht: Python,
# git, ripgrep, ffmpeg, tini als PID 1. Der Agent-Quellbaum wird NICHT
# eingebacken, sondern beim Start hereingemountet — so bleibt das Image klein
# und der Code ist aktualisierbar, ohne das Image neu zu bauen.
#
# Bau:   omx os build
# Start: docker run --rm -it \
#          -v "$HOME/AppData/Local/openamer/openamer-agent:/opt/openamer:ro" \
#          -v openamer-data:/data --gpus all openamer-os:0.1
#
# Ebene 1 (freestanding Rust-Kernel) liegt unter <agent-repo>/os und bootet in
# QEMU. Er traegt noch keinen Userspace; dieses Image ist der lauffaehige Pfad.

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENAMER_HOME=/data/openamer

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        ca-certificates curl git ripgrep ffmpeg \
        procps tini less \
    && rm -rf /var/lib/apt/lists/*

# Der Agent fuehrt Kommandos aus — deshalb kein root im Betrieb.
RUN useradd -m -u 1000 -s /bin/bash openamer \
    && mkdir -p /data/openamer /opt/openamer \
    && chown -R openamer:openamer /data

WORKDIR /opt/openamer
COPY entrypoint.sh /usr/local/bin/openamer-entrypoint
RUN chmod +x /usr/local/bin/openamer-entrypoint

USER openamer
EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s \
    CMD python3 -c "import os,sys; sys.exit(0 if os.path.isdir(os.environ['OPENAMER_HOME']) else 1)"

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/openamer-entrypoint"]
