#!/bin/sh
set -eu
cd /tmp
export DEBIAN_FRONTEND=noninteractive
export UV_CACHE_DIR=/tmp/uv-cache
export MPLBACKEND=Agg
export SASHINY_LIVE=0
export R_LIBS_USER=/tmp/Rlib
mkdir -p /tmp/audit/results /tmp/Rlib
if [ ! -d /tmp/SAShiny/.git ]; then
  git clone https://github.com/procogia/SAShiny.git /tmp/SAShiny
  git -C /tmp/SAShiny checkout --detach dd0bf602379ab3822e23eefec694514874d860f8
fi
test "$(git -C /tmp/SAShiny rev-parse HEAD)" = dd0bf602379ab3822e23eefec694514874d860f8
sudo apt-get update
sudo apt-get install -y --no-install-recommends r-base r-base-dev r-cran-jsonlite r-cran-yaml r-cran-openssl r-cran-v8 r-cran-shiny r-cran-bslib r-cran-ggplot2 r-cran-plotly r-cran-haven r-cran-openxlsx r-cran-reticulate r-cran-testthat r-cran-knitr r-cran-rmarkdown r-cran-pkgload r-cran-covr pandoc libcurl4-openssl-dev libssl-dev libxml2-dev default-jre-headless
sudo apt-get clean
Rscript -e 'install.packages(c("jsonvalidate", "reticulate"), repos="https://cloud.r-project.org", Ncpus=1)'
cd /tmp/SAShiny/Python
uv sync --all-extras
uv pip install --python .venv/bin/python fastapi uvicorn httpx coverage build hatchling
.venv/bin/python -m build --outdir /tmp/audit/dist
uv pip install --python .venv/bin/python --reinstall --no-deps /tmp/audit/dist/sashiny-0.1.6-py3-none-any.whl
cd /tmp
R CMD INSTALL /tmp/SAShiny/R
printf '\nBOOTSTRAP COMPLETE\n'
