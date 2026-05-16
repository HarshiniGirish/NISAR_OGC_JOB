from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from maap_package_service.analysis import AnalysisReport
from maap_package_service.manifest import AppManifest, Parameter


def emit_dps_package(
    artifact_path: str | Path,
    manifest: AppManifest,
    analysis: AnalysisReport,
    output_dir: str | Path,
) -> list[Path]:
    artifact = Path(artifact_path)
    package_dir = Path(output_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    entrypoint_name = artifact.name
    shutil.copy2(artifact, package_dir / entrypoint_name)

    files = [package_dir / entrypoint_name]
    files.append(_write(package_dir / "run.sh", _run_script(entrypoint_name)))
    files.append(_write_yaml(package_dir / "environment.yaml", _environment_yaml(manifest)))
    files.append(_write_yaml(package_dir / "algorithm_config.yaml", _algorithm_config(manifest)))
    files.append(_write(package_dir / "register_algorithm.py", _register_script(manifest)))
    files.append(_write(package_dir / "analysis-report.json", analysis.to_json() + "\n"))
    files.append(_write(package_dir / "README.md", _readme(manifest)))

    run_sh = package_dir / "run.sh"
    run_sh.chmod(run_sh.stat().st_mode | 0o755)
    return files


def _run_script(entrypoint_name: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)"
outdir="${{USER_OUTPUT_DIR:-${{OUTPUT_DIR:-output}}}}"
mkdir -p "${{outdir}}"

case "{entrypoint_name}" in
  *.ipynb)
    python -m jupyter nbconvert --to notebook --execute "${{basedir}}/{entrypoint_name}" \\
      --output executed.ipynb --output-dir "${{outdir}}" "$@"
    ;;
  *)
    python "${{basedir}}/{entrypoint_name}" --out_dir "${{outdir}}" "$@"
    ;;
esac
"""


def _environment_yaml(manifest: AppManifest) -> dict:
    dependencies: list[str | dict[str, list[str]]] = list(manifest.dependencies.conda)
    if manifest.dependencies.pip:
        if "pip" not in dependencies:
            dependencies.append("pip")
        dependencies.append({"pip": manifest.dependencies.pip})
    return {
        "name": manifest.name.replace("-", "_"),
        "channels": ["conda-forge", "defaults"],
        "dependencies": dependencies,
    }


def _algorithm_config(manifest: AppManifest) -> dict:
    return {
        "algorithm_name": manifest.name,
        "algorithm_version": manifest.version,
        "algorithm_description": f"{manifest.name} generated from app.yaml",
        "run_command": "run.sh",
        "build_command": "conda env create -f environment.yaml",
        "ram_min": manifest.resources.ram_min,
        "cores_min": manifest.resources.cores_min,
        "outdir_max": manifest.resources.outdir_max,
        "base_container_url": manifest.base_container,
        "inputs": [_dps_input(name, parameter) for name, parameter in manifest.inputs.items()],
        "outputs": [
            {
                "name": name,
                "type": "Directory" if output.type == "directory" else "File",
                "description": output.description,
            }
            for name, output in manifest.outputs.items()
        ],
    }


def _dps_input(name: str, parameter: Parameter) -> dict:
    return {
        "name": name,
        "label": name,
        "doc": parameter.description,
        "type": {
            "string": "string",
            "integer": "integer",
            "float": "float",
            "boolean": "boolean",
            "file": "File",
            "directory": "Directory",
        }[parameter.type],
        "default": parameter.default,
    }


def _register_script(manifest: AppManifest) -> str:
    return f'''#!/usr/bin/env python3
"""Register {manifest.name} with the MAAP DPS API.

This script intentionally keeps credentials/configuration external. Set MAAP_API_URL
and any authentication environment required by the deployed MAAP client.
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        from maap.maap import MAAP
    except ImportError as exc:
        raise SystemExit("Install maap-py before registering DPS algorithms.") from exc

    api_url = os.environ.get("MAAP_API_URL")
    maap = MAAP(maap_host=api_url) if api_url else MAAP()
    config_path = Path(__file__).with_name("algorithm_config.yaml")
    print(f"Registering {{config_path}} with MAAP DPS")
    result = maap.register_algorithm_from_yaml_file(str(config_path))
    print(result)


if __name__ == "__main__":
    main()
'''


def _readme(manifest: AppManifest) -> str:
    return f"""# {manifest.name} MAAP DPS Package

Generated DPS package files:

- `algorithm_config.yaml`
- `environment.yaml`
- `run.sh`
- `register_algorithm.py`

Register with MAAP after reviewing the generated configuration:

```bash
python register_algorithm.py
```
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
