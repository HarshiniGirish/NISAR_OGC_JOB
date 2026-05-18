#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "${basedir}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"${PYTHON_BIN}" -m py_compile *.py

if command -v cwltool >/dev/null 2>&1; then
  cwltool --validate "application.cwl"
  cwltool --validate workflow.cwl
else
  echo "cwltool not installed; skipping CWL validation."
fi

if command -v docker >/dev/null 2>&1; then
  docker build -t "both-generated-app:local" .
else
  echo "docker not installed; skipping container build."
fi
