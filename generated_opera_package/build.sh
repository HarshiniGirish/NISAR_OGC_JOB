#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

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

if command -v conda >/dev/null 2>&1; then
  mkdir -p "$(dirname "${ENV_PREFIX}")"
  conda env remove -p "${ENV_PREFIX}" -y || true
  conda env create -f "${basedir}/env.yml" --prefix "${ENV_PREFIX}"
  conda clean -afy
  conda run -p "${ENV_PREFIX}" python -m py_compile "${basedir}/opera_access_structure.py"
  conda run -p "${ENV_PREFIX}" python - <<'PY'
import maap
import numpy
import pyproj
import requests
import rioxarray
import s3fs
import shapely
import xarray
print("Environment validation successful.")
PY
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
  "${PYTHON_BIN}" -m pip install -r "${basedir}/requirements.txt"
  "${PYTHON_BIN}" -m py_compile "${basedir}/opera_access_structure.py"
fi
