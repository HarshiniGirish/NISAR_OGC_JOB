#!/usr/bin/env bash
set -euo pipefail

echo "Starting opera_water_mask_to_cog"

basedir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
OUTDIR="${USER_OUTPUT_DIR:-${OUTPUT_DIR:-output}}"

determine_env_prefix() {
  if [ -n "${CONDA_ENV_PREFIX:-}" ]; then
    printf '%s\n' "${CONDA_ENV_PREFIX}"
    return
  fi

  if [ -w /opt/conda/envs ] || { [ ! -e /opt/conda/envs ] && [ -w /opt/conda ]; }; then
    printf '%s\n' "/opt/conda/envs/opera_water_mask_to_cog"
    return
  fi

  printf '%s\n' "${HOME}/.conda/envs/opera_water_mask_to_cog"
}

ENV_PREFIX="$(determine_env_prefix)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

mkdir -p "${OUTDIR}"

if command -v conda >/dev/null 2>&1 && [ -d "${ENV_PREFIX}" ]; then
  conda run --live-stream -p "${ENV_PREFIX}" \
    python "${basedir}/opera_access_structure.py" --dest "${OUTDIR}" "$@"
else
  "${PYTHON_BIN}" "${basedir}/opera_access_structure.py" --dest "${OUTDIR}" "$@"
fi

echo "Finished opera_water_mask_to_cog"
echo "Output directory contents:"
find "${OUTDIR}" -maxdepth 3 -print || true
