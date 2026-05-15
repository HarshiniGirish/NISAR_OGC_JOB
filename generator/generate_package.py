#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
TEMPLATES_DIR = ROOT / "templates"
GENERATOR_DIR = ROOT / "generator"
OUTPUT_DIR = ROOT / "generated_package"
PIP_ONLY_PACKAGES = {"maap-py"}
DEFAULT_SCRIPT_PATH = INPUT_DIR / "nisar_access_subset.py"
DEFAULT_BASE_CONTAINER = "mas.maap-project.org/root/maap-workspaces/custom_images/maap_base:v5.0.0"
DEFAULT_TARGET = "ogc"
EXCLUDED_RUNTIME_INPUTS = {"out_dir"}
IMPLICIT_DEPENDENCY_RULES = {
    ".to_zarr": {"conda": ["zarr", "numcodecs"], "pip": []},
    "s3fs": {"conda": ["fsspec", "boto3", "botocore"], "pip": []},
    "earthaccess": {"conda": ["requests"], "pip": []},
    "h5py": {"conda": ["h5netcdf"], "pip": []},
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value

    return merged


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


def slugify_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_").lower()
    return value or "generated_app"


def infer_repository_url() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ""

    url = result.stdout.strip()
    url = re.sub(r"https://[^/@]+@github\.com/", "https://github.com/", url)
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.removeprefix("git@github.com:")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def infer_repository_name(repository_url: str) -> str:
    if repository_url:
        return repository_url.rstrip("/").rsplit("/", 1)[-1]
    return ROOT.name


def safe_eval_expr(node: ast.AST, constants: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        return constants.get(node.id, "")

    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                parts.append(str(safe_eval_expr(value.value, constants)))
        return "".join(parts)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = safe_eval_expr(node.left, constants)
        right = safe_eval_expr(node.right, constants)
        return f"{left}{right}"

    if isinstance(node, (ast.List, ast.Tuple)):
        return [safe_eval_expr(item, constants) for item in node.elts]

    return ""


def collect_module_constants(tree: ast.AST) -> dict[str, Any]:
    constants: dict[str, Any] = {}

    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not target.id.isupper():
            continue
        constants[target.id] = safe_eval_expr(node.value, constants)

    return constants


def infer_type_from_argparse(keyword: ast.keyword | None) -> str:
    if keyword is None:
        return "string"

    value = keyword.value
    if isinstance(value, ast.Name):
        if value.id == "int":
            return "integer"
        if value.id == "float":
            return "float"
        if value.id == "bool":
            return "boolean"

    return "string"


def stringify_default(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def infer_argparse_inputs(script_path: Path) -> dict[str, dict[str, str]]:
    source = script_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = collect_module_constants(tree)
    inputs: dict[str, dict[str, str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue

        option_names = [
            arg.value
            for arg in node.args
            if isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and arg.value.startswith("--")
        ]
        if not option_names:
            continue

        name = option_names[0].lstrip("-").replace("-", "_")
        if name in EXCLUDED_RUNTIME_INPUTS:
            continue

        keywords = {keyword.arg: keyword for keyword in node.keywords if keyword.arg}
        default = safe_eval_expr(keywords["default"].value, constants) if "default" in keywords else ""
        description = safe_eval_expr(keywords["help"].value, constants) if "help" in keywords else ""
        choices = safe_eval_expr(keywords["choices"].value, constants) if "choices" in keywords else []
        input_type = infer_type_from_argparse(keywords.get("type"))

        action = safe_eval_expr(keywords["action"].value, constants) if "action" in keywords else ""
        if action in {"store_true", "store_false"}:
            input_type = "boolean"
            default = action == "store_false"

        if choices and not description:
            description = f"Allowed values: {', '.join(str(choice) for choice in choices)}."

        inputs[name] = {
            "type": input_type,
            "default": stringify_default(default),
            "description": str(description),
            "inferred": True,
        }

    return inputs


def infer_description(script_path: Path) -> str:
    source = script_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    docstring = ast.get_docstring(module)
    if not docstring:
        return f"OGC Application Package generated from {script_path.name}."
    first_paragraph = docstring.strip().split("\n\n", 1)[0]
    return " ".join(line.strip() for line in first_paragraph.splitlines() if line.strip())


def infer_app_config(script_path: Path, target: str) -> dict[str, Any]:
    name = slugify_name(script_path.stem)
    return {
        "name": name,
        "version": "main",
        "target": target,
        "entrypoint": script_path.name,
        "description": infer_description(script_path),
        "repository_url": infer_repository_url(),
        "base_container": DEFAULT_BASE_CONTAINER,
        "resources": {
            "ram_min": 8,
            "cores_min": 2,
            "outdir_max": 20,
        },
        "inputs": infer_argparse_inputs(script_path),
        "outputs": {
            "output": {
                "type": "directory",
                "path": "output",
                "description": "Output directory generated by the packaged application.",
            }
        },
        "dependencies": {
            "conda": ["python=3.11"],
            "pip": [],
        },
        "inference": {
            "mode": "python_only",
            "source": str(script_path.relative_to(ROOT) if script_path.is_relative_to(ROOT) else script_path),
            "manifest_required": False,
        },
    }


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


def detect_implicit_dependencies(script_path: Path, detected_imports: list[str]) -> dict[str, list[str]]:
    source = script_path.read_text(encoding="utf-8")
    conda_dependencies: set[str] = set()
    pip_dependencies: set[str] = set()

    for marker, dependency_groups in IMPLICIT_DEPENDENCY_RULES.items():
        if marker in source or marker in detected_imports:
            conda_dependencies.update(dependency_groups.get("conda", []))
            pip_dependencies.update(dependency_groups.get("pip", []))

    return {
        "conda": sorted(conda_dependencies),
        "pip": sorted(pip_dependencies),
    }


def resolve_dependencies(
    detected_imports: list[str],
    dependency_map: dict[str, Any],
    app_config: dict[str, Any],
    implicit_dependencies: dict[str, list[str]] | None = None,
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

    implicit_dependencies = implicit_dependencies or {}
    for package_name in implicit_dependencies.get("conda", []):
        conda_dependencies.add(str(package_name))

    for package_name in implicit_dependencies.get("pip", []):
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


def format_yaml_default(value: Any, input_type: str) -> str:
    if value in (None, ""):
        return quote_yaml_string("")

    input_type = input_type.lower()
    if input_type in {"int", "integer"}:
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return quote_yaml_string(value)

    if input_type in {"float", "double"}:
        try:
            return str(float(value))
        except (TypeError, ValueError):
            return quote_yaml_string(value)

    if input_type in {"bool", "boolean"}:
        if isinstance(value, bool):
            return "true" if value else "false"
        return "true" if str(value).lower() == "true" else "false"

    return quote_yaml_string(value)


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
        lines.append(f"    default: {format_yaml_default(default, input_type)}")

    return "\n".join(lines)


def build_cwl_inputs_block(inputs: dict[str, Any]) -> str:
    lines = []

    for name, config in inputs.items():
        default = config.get("default", "")
        input_type = config.get("type", "string")
        cwl_type_map = {
            "int": "int",
            "integer": "int",
            "float": "float",
            "double": "double",
            "boolean": "boolean",
            "bool": "boolean",
        }
        cwl_type = cwl_type_map.get(input_type, "string")

        lines.append(f"  {name}:")
        lines.append(f"    type: {cwl_type}")
        lines.append(f"    default: {format_yaml_default(default, input_type)}")
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
    inferred_inputs: dict[str, Any],
    implicit_dependencies: dict[str, list[str]],
    dependencies: dict[str, list[str]],
    generated_files: list[str],
) -> str:
    report = {
        "name": app_config.get("name"),
        "version": app_config.get("version"),
        "target": app_config.get("target"),
        "entrypoint": app_config.get("entrypoint"),
        "inference": app_config.get("inference", {}),
        "detected_imports": detected_imports,
        "inferred_inputs": inferred_inputs,
        "implicit_dependencies": implicit_dependencies,
        "resolved_dependencies": dependencies,
        "generated_files": generated_files,
        "notes": [
            "This package was generated from the Python file without requiring app.yml.",
            "The generated files should be reviewed before OGC execution or MAAP registration.",
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
        f"- Generation mode: `{app_config.get('inference', {}).get('mode', 'manifest')}`",
        f"- Manifest required: `{app_config.get('inference', {}).get('manifest_required', True)}`",
        "",
        "## Detected Imports",
        "",
    ]

    for item in detected_imports:
        markdown_lines.append(f"- `{item}`")

    markdown_lines.extend(["", "## Inferred CLI Inputs", ""])

    if inferred_inputs:
        markdown_lines.extend(
            [
                "| Input | Type | Default | Description |",
                "| --- | --- | --- | --- |",
            ]
        )
        for name, config in inferred_inputs.items():
            description = str(config.get("description", "")).replace("|", "\\|")
            default = str(config.get("default", "")).replace("|", "\\|")
            markdown_lines.append(
                f"| `{name}` | `{config.get('type', 'string')}` | `{default}` | {description} |"
            )
    else:
        markdown_lines.append("No command-line inputs were inferred.")

    markdown_lines.extend(["", "## Implicit Dependencies", ""])

    if implicit_dependencies.get("conda") or implicit_dependencies.get("pip"):
        for item in implicit_dependencies.get("conda", []):
            markdown_lines.append(f"- conda: `{item}`")
        for item in implicit_dependencies.get("pip", []):
            markdown_lines.append(f"- pip: `{item}`")
    else:
        markdown_lines.append("No implicit dependencies were added.")

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


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an OGC Application Package from a Python script. "
            "By default this does not require input/app.yml; it infers app metadata, "
            "CLI inputs, and dependencies from the Python file."
        )
    )
    parser.add_argument(
        "script",
        nargs="?",
        default=str(DEFAULT_SCRIPT_PATH),
        help="Python script to package. Defaults to input/nisar_access_subset.py.",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional app.yml override. Not required for Python-only generation.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        choices=["ogc", "dps", "ogc_dps"],
        help="Package target to record in generated metadata. Defaults to ogc.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory where generated package files are written.",
    )
    return parser.parse_args()


def main() -> None:
    cli_args = parse_cli_args()
    script_path = Path(cli_args.script)
    if not script_path.is_absolute():
        script_path = ROOT / script_path
    script_path = script_path.resolve()

    if not script_path.exists():
        raise FileNotFoundError(f"Input script not found: {script_path}")

    dependency_map_path = GENERATOR_DIR / "dependency_map.yml"

    app_config = infer_app_config(script_path, cli_args.target)
    if cli_args.manifest:
        manifest_path = Path(cli_args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = ROOT / manifest_path
        app_config = merge_dicts(app_config, load_yaml(manifest_path))
        app_config.setdefault("inference", {})
        app_config["inference"]["manifest_required"] = False
        app_config["inference"]["manifest_override"] = str(
            manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path
        )

    dependency_map = load_yaml(dependency_map_path)
    output_dir = Path(cli_args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir = output_dir.resolve()

    name = app_config["name"]
    version = str(app_config.get("version", "main"))
    entrypoint = Path(app_config.get("entrypoint") or script_path.name).name
    description = app_config.get("description", "")
    repository_url = app_config.get("repository_url", "")
    base_container = app_config.get("base_container", "")
    inputs = app_config.get("inputs", {})
    outputs = app_config.get("outputs", {})
    resources = app_config.get("resources", {})

    output_config = outputs.get("output", {})
    output_description = output_config.get("description", "Generated output directory.")

    entrypoint_src = script_path
    entrypoint_dst = output_dir / entrypoint

    detected_imports = detect_imports(entrypoint_src)
    implicit_dependencies = detect_implicit_dependencies(entrypoint_src, detected_imports)
    dependencies = resolve_dependencies(
        detected_imports,
        dependency_map,
        app_config,
        implicit_dependencies,
    )
    cwl_file_name = f"{name}.cwl"

    context = {
        "name": name,
        "version": version,
        "entrypoint": entrypoint,
        "description": description,
        "repository_url": repository_url,
        "repository_name": infer_repository_name(repository_url),
        "base_container": base_container,
        "output_description": output_description,
        "dependencies_block": build_dependencies_block(dependencies),
        "algorithm_inputs_block": build_algorithm_inputs_block(inputs),
        "cwl_inputs_block": build_cwl_inputs_block(inputs),
        "ram_min": str(resources.get("ram_min", 8)),
        "cores_min": str(resources.get("cores_min", 2)),
        "outdir_max": str(resources.get("outdir_max", 20)),
    }

    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(entrypoint_src, entrypoint_dst)

    generated_files = [entrypoint]

    files_to_generate = {
        "run.sh": "run.sh.template",
        "env.yml": "env.yml.template",
        "algorithm.yml": "algorithm.yml.template",
        "Dockerfile": "Dockerfile.template",
        cwl_file_name: "commandline.cwl.template",
    }

    for output_name, template_name in files_to_generate.items():
        rendered = render_template(template_name, context)
        output_path = output_dir / output_name
        write_text(output_path, rendered)
        generated_files.append(output_name)

    build_sh = build_build_script(name, entrypoint, detected_imports, dependency_map)

    write_text(output_dir / "build.sh", build_sh)
    make_executable(output_dir / "build.sh")
    generated_files.append("build.sh")

    requirements_txt = build_requirements_txt(dependencies)
    write_text(output_dir / "requirements.txt", requirements_txt)
    generated_files.append("requirements.txt")

    readme = f"""# {name}

This OGC Application Package was generated from a Python script by the package generator proof of concept.

The generator can run without an `app.yml` manifest. It infers command-line inputs from `argparse`, detects imports with the Python AST, resolves dependencies, and renders the package files from templates.

## Entrypoint

`{entrypoint}`

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `algorithm.yml`
- `{cwl_file_name}`
- `requirements.txt`
- `{entrypoint}`
- `report.md`

Review all generated files before OGC execution or MAAP DPS registration.
"""

    write_text(output_dir / "README.md", readme)
    generated_files.append("README.md")

    generated_files.append("report.md")
    report = build_report(
        app_config,
        detected_imports,
        inputs,
        implicit_dependencies,
        dependencies,
        generated_files,
    )
    write_text(output_dir / "report.md", report)

    make_executable(output_dir / "run.sh")

    print("Generated package files:")
    for file_name in generated_files:
        print(f" - {output_dir.relative_to(ROOT)}/{file_name}")


if __name__ == "__main__":
    main()
