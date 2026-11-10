# SAShiny demo image (issue #12).
#
# Builds a container with R, Python, Java 17, saspy and both demo apps. The
# image defaults to the Offline profile (recorded results); live SAS (ODA/Viya/
# 9.4) is enabled only when credentials are supplied at runtime via the
# platform's secret/env store — never baked into the image.
#
# Build from the repository root:
#   docker build -t sashiny-demo .

# --- R + Python + Java base -------------------------------------------------
FROM rocker/r-ver:4.4.3 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Java 17 (for SAS 9.4 IOM connections via saspy).
RUN apt-get update && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless \
        build-essential \
        python3-dev \
        libcurl4-openssl-dev \
        libssl-dev \
        libxml2-dev \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv (Python package manager).
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# --- Python library + demo app ---------------------------------------------
WORKDIR /app

COPY Python/pyproject.toml Python/uv.lock Python/README.md ./Python/
COPY Python/src ./Python/src
COPY Python/examples ./Python/examples

# Install the Python library with the shiny + saspy extras.
RUN cd Python && uv sync --extra shiny --extra saspy

# --- R package + demo app ---------------------------------------------------
COPY R/DESCRIPTION R/NAMESPACE R/LICENSE R/LICENSE.md R/NEWS.md ./R/
COPY R/R ./R/R
COPY R/inst ./R/inst
COPY R/man ./R/man

# Install the R package and its dependencies.
RUN Rscript -e 'install.packages(c("remotes"), repos="https://cloud.r-project.org")' \
 && Rscript -e 'remotes::install_local("R", dependencies=TRUE, upgrade="never")'

# --- Shared spec + examples -------------------------------------------------
COPY spec ./spec
COPY examples ./examples

# --- Runtime ----------------------------------------------------------------
# The demo app defaults to Offline. Credentials are injected at runtime from the
# platform secret store (never in the image).
ENV SASHINY_CONNECTIONS=/app/examples/connections.example.yml \
    SASHINY_PROFILE=offline

EXPOSE 8000

# Run the Python demo app (Shiny for Python) by default.
CMD ["sh", "-c", "cd Python && uv run --with shiny shiny run examples/demo/app.py --host 0.0.0.0 --port 8000"]