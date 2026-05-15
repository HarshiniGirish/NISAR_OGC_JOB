#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

determine_env_prefix() {
  if [ -n "${CONDA_ENV_PREFIX:-}" ]; then
    printf '%s\n' "${CONDA_ENV_PREFIX}"
    return
  fi

  if [ -w /opt/conda/envs ] || { [ ! -e /opt/conda/envs ] && [ -w /opt/conda ]; }; then
    printf '%s\n' "/opt/conda/envs/nisar_access_subset"
    return
  fi

  printf '%s\n' "${HOME}/.conda/envs/nisar_access_subset"
}

ENV_PREFIX="$(determine_env_prefix)"

if command -v conda >/dev/null 2>&1; then
  mkdir -p "$(dirname "${ENV_PREFIX}")"
  conda env remove -p "${ENV_PREFIX}" -y || true
  conda env create -f "${basedir}/env.yml" --prefix "${ENV_PREFIX}"
  conda clean -afy
  conda run -p "${ENV_PREFIX}" python -m py_compile "${basedir}/nisar_access_subset.py"
  conda run -p "${ENV_PREFIX}" python - <<'PY'
import earthaccess
import h5py
import maap
import numpy
import pyproj
import s3fs
import xarray
print("Environment validation successful.")
PY
else
  python -m pip install -r "${basedir}/requirements.txt"
  python -m py_compile "${basedir}/nisar_access_subset.py"
fi
