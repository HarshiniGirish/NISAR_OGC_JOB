#!/usr/bin/env python3

from __future__ import annotations

import ast
import json
import shutil
import stat
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
TEMPLATES_DIR = ROOT / "templates"
GENERATOR_DIR = ROOT / "generator"
OUTPUT_DIR = ROOT / "generated_package"
PIP_ONLY_PACKAGES = {"maap-py"}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_executable(path: Path) -> None:
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_template(template_name: str, context: dict[str, str]) -> str:
    template_path = TEMPLATES_DIR / template_name
    text = template_path.read_text(encoding="utf-8")

    for key, value in context.items():
        text = text.replace("{{ " + key + " }}", value)

    return text


def detect_imports(script_path: Path) -> sorted:
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    return sorted(imports)


def resolve_dependencies(
    detected_imports: list[str],
    dependency_map: dict[str, Any],
    app_config: dict[str, Any],
) -> dict[str, list[str]]:
    conda_dependencies = set()
    pip_dependencies = set()

    for module_name in detected_imports:
        package_name = dependency_map.get(module_name)

        if package_name is None:
            continue

        package_name = str(package_name)
        if package_name in PIP_ONLY_PACKAGES:
            pip_dependencies.add(package_name)
        else:
            conda_dependencies.add(package_name)

    manifest_dependencies = app_config.get("dependencies", {})

    for package_name in manifest_dependencies.get("conda", []):
        conda_dependencies.add(str(package_name))

    for package_name in manifest_dependencies.get("pip", []):
        pip_dependencies.add(str(package_name))

    if not any(dep == "python" or dep.startswith("python=") for dep in conda_dependencies):
        conda_dependencies.add("python=3.11")

    if pip_dependencies:
        conda_dependencies.add("pip")

    return {
        "conda": sorted(conda_dependencies, key=sort_conda_dependency),
        "pip": sorted(pip_dependencies),
    }


def sort_conda_dependency(dependency: str) -> tuple[int, str]:
    if dependency == "python" or dependency.startswith("python="):
        return (0, dependency)
    if dependency == "pip":
        return (2, dependency)
    return (1, dependency)


def build_dependencies_block(dependencies: dict[str, list[str]]) -> str:
    conda_dependencies = dependencies.get("conda", [])
    pip_dependencies = dependencies.get("pip", [])

    if not conda_dependencies and not pip_dependencies:
        return "  - python=3.11"

    lines = []
    for dependency in conda_dependencies:
        lines.append(f"  - {dependency}")

    if pip_dependencies:
        if "pip" not in conda_dependencies:
            lines.append("  - pip")
        lines.append("  - pip:")
        for dependency in pip_dependencies:
            lines.append(f"      - {dependency}")

    return "\n".join(lines)


def quote_yaml_string(value: Any) -> str:
    return json.dumps(str(value))


def build_algorithm_inputs_block(inputs: dict[str, Any]) -> str:
    lines = []

    for name, config in inputs.items():
        input_type = config.get("type", "string")
        default = config.get("default", "")
        description = config.get("description", "")

        lines.append(f"  - name: {name}")
        lines.append(f"    label: {name}")
        lines.append(f"    doc: {quote_yaml_string(description)}")
        lines.append(f"    type: {input_type}")
        lines.append(f"    default: {quote_yaml_string(default)}")

    return "\n".join(lines)


def build_cwl_inputs_block(inputs: dict[str, Any]) -> str:
    lines = []

    for name, config in inputs.items():
        default = config.get("default", "")
        input_type = config.get("type", "string")
        cwl_type = "int" if input_type in {"int", "integer"} else "string"

        lines.append(f"  {name}:")
        lines.append(f"    type: {cwl_type}")
        lines.append(f"    default: {quote_yaml_string(default)}")
        lines.append("    inputBinding:")
        lines.append(f"      prefix: --{name}")

    return "\n".join(lines)


def build_requirements_txt(dependencies: dict[str, list[str]]) -> str:
    skip = {"python=3.11", "python"}
    pip_lines = []

    for dependency in dependencies.get("conda", []):
        if dependency in skip:
            continue
        if dependency == "pip" or dependency.startswith("python="):
            continue
        pip_lines.append(dependency)

    pip_lines.extend(dependencies.get("pip", []))

    return "\n".join(sorted(set(pip_lines))) + "\n"


def build_build_script(
    name: str,
    entrypoint: str,
    detected_imports: list[str],
    dependency_map: dict[str, Any],
) -> str:
    validation_imports = [
        module_name
        for module_name in detected_imports
        if dependency_map.get(module_name) is not None
    ]
    validation_import_block = "\n".join(f"import {module_name}" for module_name in validation_imports)

    return f"""#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)"
ENV_PREFIX="${{CONDA_ENV_PREFIX:-/opt/conda/envs/{name}}}"

if command -v conda >/dev/null 2>&1; then
  conda env remove -p "${{ENV_PREFIX}}" -y || true
  conda env create -f "${{basedir}}/env.yml" --prefix "${{ENV_PREFIX}}"
  conda clean -afy
  conda run -p "${{ENV_PREFIX}}" python -m py_compile "${{basedir}}/{entrypoint}"
  conda run -p "${{ENV_PREFIX}}" python - <<'PY'
{validation_import_block}
print("Environment validation successful.")
PY
else
  python -m pip install -r "${{basedir}}/requirements.txt"
  python -m py_compile "${{basedir}}/{entrypoint}"
fi
"""


def build_report(
    app_config: dict[str, Any],
    detected_imports: list[str],
    dependencies: dict[str, list[str]],
    generated_files: list[str],
) -> str:
    report = {
        "name": app_config.get("name"),
        "version": app_config.get("version"),
        "target": app_config.get("target"),
        "entrypoint": app_config.get("entrypoint"),
        "detected_imports": detected_imports,
        "resolved_dependencies": dependencies,
        "generated_files": generated_files,
        "notes": [
            "This package was generated by the OGC/DPS package generator PoC.",
            "The generated files should be reviewed before MAAP registration.",
            "Scientific correctness remains the responsibility of the algorithm author.",
        ],
    }

    markdown_lines = [
        f"# Generator Report: {app_config.get('name')}",
        "",
        "## Summary",
        "",
        f"- Algorithm name: `{app_config.get('name')}`",
        f"- Version: `{app_config.get('version')}`",
        f"- Target: `{app_config.get('target')}`",
        f"- Entrypoint: `{app_config.get('entrypoint')}`",
        "",
        "## Detected Imports",
        "",
    ]

    for item in detected_imports:
        markdown_lines.append(f"- `{item}`")

    markdown_lines.extend(["", "## Resolved Dependencies", ""])

    for item in dependencies.get("conda", []):
        markdown_lines.append(f"- conda: `{item}`")

    for item in dependencies.get("pip", []):
        markdown_lines.append(f"- pip: `{item}`")

    markdown_lines.extend(["", "## Generated Files", ""])

    for item in generated_files:
        markdown_lines.append(f"- `{item}`")

    markdown_lines.extend(
        [
            "",
            "## Machine-Readable Summary",
            "",
            "```json",
            json.dumps(report, indent=2),
            "```",
            "",
        ]
    )

    return "\n".join(markdown_lines)


def main() -> None:
    app_path = INPUT_DIR / "app.yml"
    dependency_map_path = GENERATOR_DIR / "dependency_map.yml"

    app_config = load_yaml(app_path)
    dependency_map = load_yaml(dependency_map_path)

    name = app_config["name"]
    version = str(app_config.get("version", "main"))
    entrypoint = app_config["entrypoint"]
    description = app_config.get("description", "")
    repository_url = app_config.get("repository_url", "")
    base_container = app_config.get("base_container", "")
    inputs = app_config.get("inputs", {})
    outputs = app_config.get("outputs", {})
    resources = app_config.get("resources", {})

    output_config = outputs.get("output", {})
    output_description = output_config.get("description", "Generated output directory.")

    entrypoint_src = INPUT_DIR / entrypoint
    entrypoint_dst = OUTPUT_DIR / entrypoint

    detected_imports = detect_imports(entrypoint_src)
    dependencies = resolve_dependencies(detected_imports, dependency_map, app_config)

    context = {
        "name": name,
        "version": version,
        "entrypoint": entrypoint,
        "description": description,
        "repository_url": repository_url,
        "base_container": base_container,
        "output_description": output_description,
        "dependencies_block": build_dependencies_block(dependencies),
        "algorithm_inputs_block": build_algorithm_inputs_block(inputs),
        "cwl_inputs_block": build_cwl_inputs_block(inputs),
        "ram_min": str(resources.get("ram_min", 8)),
        "cores_min": str(resources.get("cores_min", 2)),
        "outdir_max": str(resources.get("outdir_max", 20)),
    }

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    shutil.copy2(entrypoint_src, entrypoint_dst)

    generated_files = [entrypoint]

    files_to_generate = {
        "run.sh": "run.sh.template",
        "env.yml": "env.yml.template",
        "algorithm.yml": "algorithm.yml.template",
        "Dockerfile": "Dockerfile.template",
        "nisar_access_subset.cwl": "commandline.cwl.template",
    }

    for output_name, template_name in files_to_generate.items():
        rendered = render_template(template_name, context)
        output_path = OUTPUT_DIR / output_name
        write_text(output_path, rendered)
        generated_files.append(output_name)

    build_sh = build_build_script(name, entrypoint, detected_imports, dependency_map)

    write_text(OUTPUT_DIR / "build.sh", build_sh)
    make_executable(OUTPUT_DIR / "build.sh")
    generated_files.append("build.sh")

    requirements_txt = build_requirements_txt(dependencies)
    write_text(OUTPUT_DIR / "requirements.txt", requirements_txt)
    generated_files.append("requirements.txt")

    readme = f"""# {name}

This package was generated by the OGC/DPS package generator proof of concept.

## Entrypoint

`{entrypoint}`

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `algorithm.yml`
- `nisar_access_subset.cwl`
- `requirements.txt`
- `{entrypoint}`
- `report.md`

Review all generated files before registering or running this package in MAAP DPS.
"""

    write_text(OUTPUT_DIR / "README.md", readme)
    generated_files.append("README.md")

    generated_files.append("report.md")
    report = build_report(app_config, detected_imports, dependencies, generated_files)
    write_text(OUTPUT_DIR / "report.md", report)

    make_executable(OUTPUT_DIR / "run.sh")

    print("Generated package files:")
    for file_name in generated_files:
        print(f" - generated_package/{file_name}")


if __name__ == "__main__":
    main()
