#!/usr/bin/env bash
set -euo pipefail

echo "Starting nisar_access_subset"

basedir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
OUTDIR="${USER_OUTPUT_DIR:-${OUTPUT_DIR:-output}}"
ENV_PREFIX="${CONDA_ENV_PREFIX:-/opt/conda/envs/nisar_access_subset}"

mkdir -p "${OUTDIR}"

if command -v conda >/dev/null 2>&1 && [ -d "${ENV_PREFIX}" ]; then
  conda run --live-stream -p "${ENV_PREFIX}" \
    python "${basedir}/nisar_access_subset.py" --out_dir "${OUTDIR}" "$@"
else
  python "${basedir}/nisar_access_subset.py" --out_dir "${OUTDIR}" "$@"
fi

echo "Finished nisar_access_subset"
echo "Output directory contents:"
find "${OUTDIR}" -maxdepth 3 -print || true
