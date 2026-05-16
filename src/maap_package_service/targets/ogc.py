from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from maap_package_service.analysis import AnalysisReport
from maap_package_service.manifest import AppManifest, Parameter


def emit_ogc_package(
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
    files.append(_write(package_dir / "Dockerfile", _dockerfile(manifest)))
    files.append(_write(package_dir / "run.sh", _run_script(entrypoint_name)))
    files.append(_write_yaml(package_dir / "commandline.cwl", _commandline_cwl(manifest)))
    files.append(_write_yaml(package_dir / "workflow.cwl", _workflow_cwl(manifest)))
    files.append(_write(package_dir / "stac-input.json", _stac_input(manifest)))
    files.append(_write(package_dir / "stac-output.json", _stac_output(manifest)))
    files.append(_write(package_dir / "analysis-report.json", analysis.to_json() + "\n"))
    files.append(_write(package_dir / "README.md", _readme(manifest)))

    run_sh = package_dir / "run.sh"
    run_sh.chmod(run_sh.stat().st_mode | 0o755)
    return files


def _dockerfile(manifest: AppManifest) -> str:
    pip_packages = " ".join(manifest.dependencies.pip)
    system_install = ""
    if pip_packages:
        system_install = f"RUN python -m pip install --no-cache-dir {pip_packages}\n"
    return f"""FROM {manifest.base_container}

WORKDIR /opt/app
COPY . /opt/app
{system_install}RUN chmod +x /opt/app/run.sh
ENTRYPOINT ["/opt/app/run.sh"]
"""


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


def _commandline_cwl(manifest: AppManifest) -> dict:
    return {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "label": manifest.name,
        "baseCommand": ["/opt/app/run.sh"],
        "inputs": {
            name: {
                "type": _cwl_type(parameter),
                "default": parameter.default,
                "inputBinding": {"prefix": f"--{name}"},
            }
            for name, parameter in manifest.inputs.items()
        },
        "outputs": {
            name: {
                "type": "Directory" if output.type == "directory" else "File",
                "outputBinding": {"glob": output.path},
            }
            for name, output in manifest.outputs.items()
        },
    }


def _workflow_cwl(manifest: AppManifest) -> dict:
    return {
        "cwlVersion": "v1.2",
        "class": "Workflow",
        "label": f"{manifest.name}-workflow",
        "inputs": {
            name: _cwl_type(parameter)
            for name, parameter in manifest.inputs.items()
        },
        "outputs": {
            name: {
                "type": "Directory" if output.type == "directory" else "File",
                "outputSource": f"run/{name}",
            }
            for name, output in manifest.outputs.items()
        },
        "steps": {
            "run": {
                "run": "commandline.cwl",
                "in": {name: name for name in manifest.inputs},
                "out": list(manifest.outputs),
            }
        },
    }


def _stac_input(manifest: AppManifest) -> str:
    item = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"{manifest.name}-input-template",
        "properties": {},
        "geometry": None,
        "bbox": None,
        "links": [],
        "assets": {},
    }
    return json.dumps(item, indent=2) + "\n"


def _stac_output(manifest: AppManifest) -> str:
    item = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": f"{manifest.name}-output-template",
        "properties": {},
        "geometry": None,
        "bbox": None,
        "links": [],
        "assets": {
            name: {
                "href": output.path,
                "title": output.description,
                "roles": ["data"],
            }
            for name, output in manifest.outputs.items()
        },
    }
    return json.dumps(item, indent=2) + "\n"


def _readme(manifest: AppManifest) -> str:
    return f"""# {manifest.name} OGC Application Package

Generated package files follow the EOAP-style pattern:

- `Dockerfile`
- `commandline.cwl`
- `workflow.cwl`
- `stac-input.json`
- `stac-output.json`
- `run.sh`

Validate with:

```bash
maap-package-service validate-cwl commandline.cwl
```
"""


def _cwl_type(parameter: Parameter) -> str:
    return {
        "string": "string",
        "integer": "int",
        "float": "float",
        "boolean": "boolean",
        "file": "File",
        "directory": "Directory",
    }[parameter.type]


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
