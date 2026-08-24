#!/usr/bin/env bash
# Launcher for the section-positioning study. Mirrors the panelling study's
# environment and puts panelling_study/ on PYTHONPATH so `import common as pc`
# resolves to the shared runner.
set -euo pipefail

source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate aeris

OMPI="$HOME/packages/openmpi-5.0.10/opt-gfortran"
CGNS="$HOME/packages/CGNS-4.5.2/opt-gfortran"
export PATH="$OMPI/bin:$PATH:/usr/local/bin"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:$OMPI/lib:$CGNS/lib"

HERE="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$HERE:$HERE/../panelling_study:${PYTHONPATH:-}"

cd "$HERE"
exec python "$@"
