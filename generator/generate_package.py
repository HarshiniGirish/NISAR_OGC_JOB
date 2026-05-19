#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
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
DEFAULT_PANGEO_CONTAINER = "mas.maap-project.org/root/maap-workspaces/base_images/pangeo:v4.1.1"
DEFAULT_TARGET = "both"
TARGET_ALIASES = {"ogc_dps": "both", "ogc-dps": "both"}
EXCLUDED_RUNTIME_INPUTS = {"out_dir", "output_dir", "dest", "outdir"}
PYTHON_SOURCE_SUFFIXES = {".py"}
NOTEBOOK_SOURCE_SUFFIXES = {".ipynb"}
EXECUTABLE_SOURCE_SUFFIXES = {".run", ".sh", ".bash", ".zsh"}
OUTPUT_ARGUMENT_NAMES = {"out_dir", "output_dir", "output", "dest", "outdir"}
IMPLICIT_DEPENDENCY_RULES = {
    ".to_zarr": {"conda": ["zarr<3", "numcodecs<0.16"], "pip": []},
    ".rio.to_raster": {"conda": ["rioxarray", "rasterio"], "pip": []},
    "driver=\"COG\"": {"conda": ["rasterio"], "pip": []},
    "driver='COG'": {"conda": ["rasterio"], "pip": []},
    "open_dataset": {"conda": ["dask", "h5netcdf", "netcdf4", "scipy"], "pip": []},
    "s3fs": {"conda": ["fsspec", "boto3", "botocore"], "pip": []},
    "earthaccess": {"conda": ["requests"], "pip": []},
    "h5py": {"conda": ["h5netcdf"], "pip": []},
}
DATA_READ_CALL_MARKERS = (
    "open",
    "Path",
    "read_csv",
    "read_json",
    "read_parquet",
    "read_table",
    "open_dataset",
    "open_dataarray",
    "open_zarr",
    "to_raster",
    "File",
    "rasterio.open",
)
LOCAL_PATH_PREFIXES = (
    "/home/",
    "/Users/",
    "/tmp/",
    "/mnt/",
    "/data/",
    "/workspace/",
    "./",
    "../",
)
LOCAL_FILE_EXTENSIONS = (
    ".csv",
    ".json",
    ".parquet",
    ".tif",
    ".tiff",
    ".nc",
    ".h5",
    ".hdf5",
    ".zarr",
    ".geojson",
)
KNOWN_GLOBAL_NAMES = {
    "False",
    "None",
    "True",
    "__file__",
    "__name__",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "open",
    "print",
    "range",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
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


def normalize_manifest_config(manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(manifest)

    legacy_key_map = {
        "algorithm_name": "name",
        "algorithm_version": "version",
        "algorithm_description": "description",
        "code_repository": "repository_url",
        "base_container_url": "base_container",
    }
    for old_key, new_key in legacy_key_map.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized.pop(old_key)

    if "target" in normalized:
        normalized["target"] = normalize_target(str(normalized["target"]))
    if "base_container_preference" in normalized and "base_container" not in normalized:
        normalized["base_container"] = normalized.pop("base_container_preference")
    resources = normalized.get("resources", {})
    if not isinstance(resources, dict):
        resources = {}
    for resource_key in ("ram_min", "cores_min", "outdir_max"):
        if resource_key in normalized:
            resources[resource_key] = normalized.pop(resource_key)
    if resources:
        normalized["resources"] = resources
    if "input_schema" in normalized:
        normalized["inputs"] = merge_dicts(
            normalized.get("inputs", {}), normalized.pop("input_schema") or {}
        )
    if "output_schema" in normalized:
        normalized["outputs"] = merge_dicts(
            normalized.get("outputs", {}), normalized.pop("output_schema") or {}
        )
    if isinstance(normalized.get("inputs"), list):
        normalized["inputs"] = normalize_io_list(normalized["inputs"])
    if isinstance(normalized.get("outputs"), list):
        normalized["outputs"] = normalize_io_list(normalized["outputs"])

    return normalized


def normalize_io_list(items: list[Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict) or "name" not in item:
            continue
        name = str(item["name"])
        normalized[name] = {
            "type": item.get("type", "string"),
            "default": item.get("default", ""),
            "description": item.get("description") or item.get("doc", ""),
            "cli_option": item.get("cli_option", ""),
        }
    return normalized


def discover_manifest(cli_manifest: str, source_path: Path) -> Path | None:
    if cli_manifest:
        manifest_path = Path(cli_manifest)
        if not manifest_path.is_absolute():
            manifest_path = ROOT / manifest_path
        return manifest_path.resolve()
    return None


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


def normalize_target(value: str | None) -> str:
    target = (value or DEFAULT_TARGET).strip().lower()
    target = TARGET_ALIASES.get(target, target)
    if target not in {"ogc", "dps", "both"}:
        raise ValueError("target must be one of: ogc, dps, both")
    return target


def target_includes(target: str, requested: str) -> bool:
    normalized = normalize_target(target)
    return normalized == "both" or normalized == requested


def infer_base_container(detected_imports: list[str], current_base_container: str) -> str:
    if current_base_container != DEFAULT_BASE_CONTAINER:
        return current_base_container

    pangeo_signals = {"dask", "geopandas", "rasterio", "rioxarray"}
    if pangeo_signals.intersection(detected_imports):
        return DEFAULT_PANGEO_CONTAINER

    return current_base_container


def source_label(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def get_call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = get_call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    return ""


def get_assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()

    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            names.update(get_assigned_names(item))
    elif isinstance(node, ast.Attribute):
        return names

    return names


def infer_type_from_value(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "string"


def source_kind_for_path(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix in NOTEBOOK_SOURCE_SUFFIXES:
        return "notebook"
    if suffix in PYTHON_SOURCE_SUFFIXES:
        return "script"
    if suffix in EXECUTABLE_SOURCE_SUFFIXES:
        return "executable"
    return "script"


def is_python_source(source_info: dict[str, Any]) -> bool:
    return source_info.get("kind") in {"script", "notebook"}


def normalize_notebook_code(source: str) -> tuple[str, list[dict[str, Any]]]:
    normalized_lines = []
    magic_lines = []

    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("%", "!", "?")):
            normalized_lines.append(f"# NOTEBOOK_MAGIC_REMOVED: {line}")
            magic_lines.append(
                {
                    "line": lineno,
                    "source": line.strip(),
                    "message": "Notebook magic or shell escape is not portable in batch execution.",
                }
            )
        else:
            normalized_lines.append(line)

    return "\n".join(normalized_lines), magic_lines


def cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source)


def is_probable_parameter_cell(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    has_assignment = False
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            has_assignment = True
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        return False

    return has_assignment


def read_source_file(source_path: Path) -> dict[str, Any]:
    source_kind = source_kind_for_path(source_path)
    if source_kind != "notebook":
        source = source_path.read_text(encoding="utf-8")
        return {
            "kind": source_kind,
            "path": source_path,
            "source": source,
            "raw_source": source,
            "code_units": [{"index": 0, "source": source, "tags": [], "start_line": 1}],
            "parameters_source": "",
            "parameters_cell_index": None,
            "magic_lines": [],
        }

    notebook = json.loads(source_path.read_text(encoding="utf-8"))
    code_units = []
    script_parts = []
    parameters_source = ""
    parameters_cell_index = None
    magic_lines: list[dict[str, Any]] = []
    current_line = 1

    for cell_index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue

        raw_cell_source = cell_source(cell)
        normalized_source, cell_magic_lines = normalize_notebook_code(raw_cell_source)
        tags = list(cell.get("metadata", {}).get("tags", []))
        unit = {
            "index": cell_index,
            "source": normalized_source,
            "raw_source": raw_cell_source,
            "tags": tags,
            "start_line": current_line + 1,
        }
        code_units.append(unit)

        for magic_line in cell_magic_lines:
            magic_line["cell"] = cell_index
            magic_line["line"] = current_line + magic_line["line"]
            magic_lines.append(magic_line)

        script_parts.append(f"# %% notebook cell {cell_index}\n{normalized_source}")
        current_line += normalized_source.count("\n") + 2

        if parameters_source:
            continue
        if "parameters" in tags or (parameters_cell_index is None and is_probable_parameter_cell(normalized_source)):
            parameters_source = normalized_source
            parameters_cell_index = cell_index

    script_source = "\n\n".join(script_parts).strip() + "\n"
    return {
        "kind": "notebook",
        "path": source_path,
        "source": script_source,
        "raw_source": "\n\n".join(cell.get("raw_source", cell["source"]) for cell in code_units),
        "code_units": code_units,
        "parameters_source": parameters_source,
        "parameters_cell_index": parameters_cell_index,
        "magic_lines": magic_lines,
    }


def materialize_entrypoint(source_info: dict[str, Any], destination: Path) -> None:
    if source_info["kind"] == "notebook":
        write_text(destination, source_info["source"])
    else:
        shutil.copy2(source_info["path"], destination)
    if source_info["kind"] == "executable":
        make_executable(destination)


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


def infer_argparse_inputs_from_source(source: str) -> dict[str, dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    constants = collect_module_constants(tree)
    inputs: dict[str, dict[str, Any]] = {}

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

        cli_option = option_names[0]
        name = cli_option.lstrip("-").replace("-", "_")
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
            "source": "argparse",
            "cli_option": cli_option,
        }

    return inputs


def infer_argparse_inputs(script_path: Path) -> dict[str, dict[str, Any]]:
    return infer_argparse_inputs_from_source(script_path.read_text(encoding="utf-8"))


def infer_papermill_inputs(parameters_source: str) -> dict[str, dict[str, Any]]:
    if not parameters_source:
        return {}

    try:
        tree = ast.parse(parameters_source)
    except SyntaxError:
        return {}

    inputs: dict[str, dict[str, Any]] = {}
    constants: dict[str, Any] = {}

    for node in tree.body:
        target: ast.AST | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value_node = node.value

        if not isinstance(target, ast.Name) or value_node is None:
            continue
        if target.id.startswith("_") or target.id in EXCLUDED_RUNTIME_INPUTS:
            continue

        value = safe_eval_expr(value_node, constants)
        constants[target.id] = value
        inputs[target.id] = {
            "type": infer_type_from_value(value),
            "default": stringify_default(value),
            "description": "Papermill-style parameter inferred from the notebook parameters cell.",
            "inferred": True,
            "source": "papermill",
        }

    return inputs


def infer_description_from_source(source: str, source_path: Path) -> str:
    try:
        module = ast.parse(source)
    except SyntaxError:
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                description = stripped.lstrip("#").strip()
                if description and not description.startswith("!"):
                    return description
        return f"Application package generated from {source_path.name}."
    docstring = ast.get_docstring(module)
    if not docstring:
        return f"Application package generated from {source_path.name}."
    first_paragraph = docstring.strip().split("\n\n", 1)[0]
    return " ".join(line.strip() for line in first_paragraph.splitlines() if line.strip())


def infer_description(script_path: Path) -> str:
    return infer_description_from_source(script_path.read_text(encoding="utf-8"), script_path)


def infer_inputs(source_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not is_python_source(source_info):
        return {}
    inputs = infer_papermill_inputs(source_info.get("parameters_source", ""))
    inputs.update(infer_argparse_inputs_from_source(source_info["source"]))
    return inputs


def collect_source_metadata(source_info: dict[str, Any]) -> dict[str, Any]:
    if not is_python_source(source_info):
        return {}
    try:
        tree = ast.parse(source_info["source"])
    except SyntaxError:
        return {}
    return collect_module_constants(tree)


def infer_runtime_config(source_info: dict[str, Any]) -> dict[str, str]:
    runtime_type = "python" if is_python_source(source_info) else "executable"
    output_argument = ""

    if is_python_source(source_info):
        try:
            tree = ast.parse(source_info["source"])
        except SyntaxError:
            tree = None

        if tree is not None:
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
                for option_name in option_names:
                    normalized = option_name.lstrip("-").replace("-", "_")
                    if normalized in OUTPUT_ARGUMENT_NAMES:
                        output_argument = option_name
                        break
                if output_argument:
                    break

    return {
        "type": runtime_type,
        "output_argument": output_argument,
    }


def infer_app_config(source_path: Path, source_info: dict[str, Any], target: str) -> dict[str, Any]:
    metadata = collect_source_metadata(source_info)
    name = slugify_name(str(metadata.get("APP_NAME") or source_path.stem))
    entrypoint_suffix = ".py" if source_info["kind"] == "notebook" else source_path.suffix
    entrypoint = f"{name}{entrypoint_suffix}"
    return {
        "name": name,
        "version": str(metadata.get("APP_VERSION") or "main"),
        "target": normalize_target(str(metadata.get("APP_TARGET") or target)),
        "entrypoint": entrypoint,
        "description": str(
            metadata.get("APP_DESCRIPTION") or infer_description_from_source(source_info["source"], source_path)
        ),
        "repository_url": infer_repository_url(),
        "base_container": str(metadata.get("APP_BASE_CONTAINER") or DEFAULT_BASE_CONTAINER),
        "runtime": infer_runtime_config(source_info),
        "resources": {
            "ram_min": int(metadata.get("APP_RAM_MIN") or 8),
            "cores_min": int(metadata.get("APP_CORES_MIN") or 2),
            "outdir_max": int(metadata.get("APP_OUTDIR_MAX") or 20),
        },
        "inputs": infer_inputs(source_info),
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
            "mode": "notebook" if source_info["kind"] == "notebook" else "python_only",
            "source": source_label(source_path),
            "source_kind": source_info["kind"],
            "parameters_cell_index": source_info.get("parameters_cell_index"),
            "manifest_required": False,
        },
    }


def detect_imports_from_source(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])

    return sorted(imports)


def detect_imports(script_path: Path) -> list[str]:
    return detect_imports_from_source(script_path.read_text(encoding="utf-8"))


def detect_implicit_dependencies_from_source(
    source: str, detected_imports: list[str]
) -> dict[str, list[str]]:
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


def detect_implicit_dependencies(script_path: Path, detected_imports: list[str]) -> dict[str, list[str]]:
    return detect_implicit_dependencies_from_source(
        script_path.read_text(encoding="utf-8"), detected_imports
    )


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
        lines.append(f"      prefix: {config.get('cli_option') or '--' + name}")

    return "\n".join(lines) if lines else "  {}"


def build_cwl_workflow_inputs_block(inputs: dict[str, Any]) -> str:
    lines = []

    for name, config in inputs.items():
        input_type = config.get("type", "string")
        cwl_type_map = {
            "int": "int",
            "integer": "int",
            "float": "float",
            "double": "double",
            "boolean": "boolean",
            "bool": "boolean",
        }
        lines.append(f"  {name}: {cwl_type_map.get(input_type, 'string')}")

    return "\n".join(lines) if lines else "  {}"


def build_cwl_workflow_step_inputs_block(inputs: dict[str, Any]) -> str:
    lines = [f"      {name}: {name}" for name in inputs]
    return "\n".join(lines) if lines else "      {}"


def build_stac_input_manifest(app_config: dict[str, Any], inputs: dict[str, Any]) -> str:
    properties = {
        name: {
            "type": config.get("type", "string"),
            "default": config.get("default", ""),
            "description": config.get("description", ""),
        }
        for name, config in inputs.items()
    }
    manifest = {
        "type": "FeatureCollection",
        "features": [],
        "links": [],
        "metadata": {
            "application": app_config.get("name"),
            "role": "sample-input-manifest",
            "input_schema": properties,
        },
    }
    return json.dumps(manifest, indent=2) + "\n"


def build_stac_output_manifest(app_config: dict[str, Any], outputs: dict[str, Any]) -> str:
    manifest = {
        "type": "FeatureCollection",
        "features": [],
        "links": [],
        "metadata": {
            "application": app_config.get("name"),
            "role": "expected-output-manifest",
            "output_schema": outputs,
        },
    }
    return json.dumps(manifest, indent=2) + "\n"


def build_generated_app_manifest(app_config: dict[str, Any]) -> str:
    manifest = {
        "target": app_config.get("target"),
        "name": app_config.get("name"),
        "version": app_config.get("version"),
        "description": app_config.get("description", ""),
        "repository_url": app_config.get("repository_url", ""),
        "base_container_preference": app_config.get("base_container", ""),
        "runtime": app_config.get("runtime", {}),
        "resources": app_config.get("resources", {}),
        "input_schema": app_config.get("inputs", {}),
        "output_schema": app_config.get("outputs", {}),
        "dependencies": app_config.get("dependencies", {}),
        "inference": app_config.get("inference", {}),
    }
    return yaml.safe_dump(manifest, sort_keys=False)


def build_runtime_output_arg(output_argument: str) -> str:
    if not output_argument:
        return ""
    return f' {output_argument} "${{OUTDIR}}"'


def build_run_commands(runtime_config: dict[str, Any], entrypoint: str) -> dict[str, str]:
    output_arg = build_runtime_output_arg(str(runtime_config.get("output_argument", "")))
    runtime_type = runtime_config.get("type", "python")

    if runtime_type == "executable":
        return {
            "conda": (
                f'  conda run --live-stream -p "${{ENV_PREFIX}}" '
                f'bash "${{basedir}}/{entrypoint}"{output_arg} "$@"'
            ),
            "local": f'  bash "${{basedir}}/{entrypoint}"{output_arg} "$@"',
        }

    return {
        "conda": (
            f'  conda run --live-stream -p "${{ENV_PREFIX}}" \\\n'
            f'    python "${{basedir}}/{entrypoint}"{output_arg} "$@"'
        ),
        "local": f'  "${{PYTHON_BIN}}" "${{basedir}}/{entrypoint}"{output_arg} "$@"',
    }


def build_llm_prompt(app_config: dict[str, Any], analysis: dict[str, Any]) -> str:
    payload = {
        "task": (
            "Review this generated MAAP DPS / OGC Application Package analysis. "
            "Identify semantic reproducibility or scaling risks that rule-based linters may miss, "
            "especially hidden cell-order dependencies and undeclared environment state."
        ),
        "app": {
            "name": app_config.get("name"),
            "target": app_config.get("target"),
            "inputs": app_config.get("inputs", {}),
            "outputs": app_config.get("outputs", {}),
            "resources": app_config.get("resources", {}),
        },
        "static_analysis": analysis,
        "response_format": [
            "List blocking issues first.",
            "For each issue, include remediation that can be applied before registration.",
            "If no blocking issues are found, say what residual risks remain.",
        ],
    }
    return json.dumps(payload, indent=2)


def resolve_llm_provider(requested_provider: str) -> str:
    provider = requested_provider.lower()
    if provider != "auto":
        return provider
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"


def run_llm_analysis(
    prompt: str,
    enabled: bool,
    provider: str,
    model: str | None,
    openai_model: str,
    anthropic_model: str,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "not_requested",
            "message": (
                "Pass --llm-analysis with OPENAI_API_KEY or ANTHROPIC_API_KEY to run the "
                "optional semantic analysis pass. The prompt is saved for manual ChatGPT review."
            ),
        }

    provider = resolve_llm_provider(provider)
    if provider == "openai":
        return run_openai_analysis(prompt, model or openai_model)
    if provider == "anthropic":
        return run_anthropic_analysis(prompt, model or anthropic_model)

    return {
        "status": "failed",
        "message": f"Unsupported LLM provider: {provider}. Use openai, anthropic, or auto.",
    }


def run_anthropic_analysis(prompt: str, model: str) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "status": "skipped",
            "provider": "anthropic",
            "message": "ANTHROPIC_API_KEY is not set. llm_analysis_prompt.json was generated for offline review.",
        }

    body = json.dumps(
        {
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "message": f"Anthropic API analysis failed: {exc}",
        }

    response_text = "\n".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    return {
        "status": "completed",
        "provider": "anthropic",
        "model": model,
        "response": response_text,
    }


def run_openai_analysis(prompt: str, model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "status": "skipped",
            "provider": "openai",
            "message": "OPENAI_API_KEY is not set. llm_analysis_prompt.json was generated for manual ChatGPT review.",
        }

    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You review MAAP DPS and OGC application packages for reproducibility, "
                        "portability, and scaling risks. Give actionable remediation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "provider": "openai",
            "message": f"OpenAI API analysis failed: {exc}",
        }

    choices = payload.get("choices", [])
    response_text = ""
    if choices:
        message = choices[0].get("message", {})
        response_text = str(message.get("content", "")).strip()

    return {
        "status": "completed",
        "provider": "openai",
        "model": model,
        "response": response_text,
    }


def build_dps_registration_script(config_file_name: str = "algorithm_config.yaml") -> str:
    return f'''#!/usr/bin/env python3
"""Register the generated DPS algorithm with a configured MAAP API endpoint.

Environment variables:
- MAAP_API_URL: base URL for the MAAP API.
- MAAP_API_TOKEN or MAAP_TOKEN: bearer token for registration.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml


def main() -> None:
    package_dir = Path(__file__).resolve().parent
    config = yaml.safe_load((package_dir / "{config_file_name}").read_text(encoding="utf-8"))
    api_url = os.environ.get("MAAP_API_URL", "").rstrip("/")
    token = os.environ.get("MAAP_API_TOKEN") or os.environ.get("MAAP_TOKEN")
    if not api_url or not token:
        raise SystemExit("Set MAAP_API_URL and MAAP_API_TOKEN before DPS registration.")

    payload = json.dumps(config).encode("utf-8")
    request = urllib.request.Request(
        f"{{api_url}}/api/algorithms",
        data=payload,
        headers={{
            "authorization": f"Bearer {{token}}",
            "content-type": "application/json",
        }},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        sys.stdout.write(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
'''


def build_ogc_publish_script() -> str:
    return '''#!/usr/bin/env python3
"""Publish the generated OGC Application Package to a configured registry.

Environment variables:
- OGC_REGISTRY_URL: registry endpoint accepting multipart/package metadata.
- OGC_REGISTRY_TOKEN: optional bearer token.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    package_dir = Path(__file__).resolve().parent
    registry_url = os.environ.get("OGC_REGISTRY_URL", "").rstrip("/")
    token = os.environ.get("OGC_REGISTRY_TOKEN", "")
    if not registry_url:
        raise SystemExit("Set OGC_REGISTRY_URL before publishing.")

    payload = {
        "command_line_tool": (package_dir / "application.cwl").read_text(encoding="utf-8"),
        "workflow": (package_dir / "workflow.cwl").read_text(encoding="utf-8"),
        "stac_input": json.loads((package_dir / "stac-input.json").read_text(encoding="utf-8")),
        "stac_output": json.loads((package_dir / "stac-output.json").read_text(encoding="utf-8")),
    }
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{registry_url}/applications",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        sys.stdout.write(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
'''


def build_validation_script(target: str, cwl_file_name: str) -> str:
    cwl_commands = ""
    if target_includes(target, "ogc"):
        cwl_commands = f'''
if command -v cwltool >/dev/null 2>&1; then
  cwltool --validate "{cwl_file_name}"
  cwltool --validate workflow.cwl
else
  echo "cwltool not installed; skipping CWL validation."
fi
'''
    else:
        cwl_commands = 'echo "OGC target not requested; skipping CWL validation."\n'

    return f'''#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)"
cd "${{basedir}}"

PYTHON_BIN="${{PYTHON_BIN:-python3}}"
if ! command -v "${{PYTHON_BIN}}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"${{PYTHON_BIN}}" -m py_compile *.py
{cwl_commands}
if command -v docker >/dev/null 2>&1; then
  docker build -t "{target}-generated-app:local" .
else
  echo "docker not installed; skipping container build."
fi
'''


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


def issue(rule: str, severity: str, message: str, remediation: str, location: str = "") -> dict[str, str]:
    item = {
        "rule": rule,
        "severity": severity,
        "message": message,
        "remediation": remediation,
    }
    if location:
        item["location"] = location
    return item


def looks_like_local_file_path(value: str) -> bool:
    if not value or value.startswith(("s3://", "http://", "https://")):
        return False
    normalized = value.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        return True
    if normalized.startswith(LOCAL_PATH_PREFIXES):
        return True
    has_path_separator = "/" in normalized
    return has_path_separator and any(
        normalized.endswith(extension) for extension in LOCAL_FILE_EXTENSIONS
    )


def string_literals(node: ast.AST) -> list[str]:
    values = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.append(child.value)
    return values


def classify_data_reference(value: str) -> str | None:
    lowered = value.lower()
    if lowered.startswith("s3://") or "amazonaws.com" in lowered:
        return "s3"
    if "cmr.earthdata.nasa.gov" in lowered:
        return "cmr"
    if "s3credentials" in lowered and "earthdata" in lowered:
        return "s3"
    if "stac" in lowered and lowered.startswith(("http://", "https://")):
        return "stac"
    if looks_like_local_file_path(value):
        return "local"
    return None


def is_data_read_call(call_name: str) -> bool:
    lowered = call_name.lower()
    if lowered in {"open", "path", "pathlib.path", "h5py.file"}:
        return True
    return lowered.endswith(
        (
            ".open",
            ".read_csv",
            ".read_json",
            ".read_parquet",
            ".read_table",
            ".open_dataset",
            ".open_dataarray",
            ".open_zarr",
        )
    )


def add_data_access(
    data_access: dict[str, list[dict[str, Any]]],
    access_type: str,
    evidence: str,
    location: str,
) -> None:
    item = {"evidence": evidence, "location": location}
    if item not in data_access[access_type]:
        data_access[access_type].append(item)


def analyze_source(source_info: dict[str, Any], detected_imports: list[str], inputs: dict[str, Any]) -> dict[str, Any]:
    source = source_info["source"]
    data_access: dict[str, list[dict[str, Any]]] = {
        "s3": [],
        "stac": [],
        "cmr": [],
        "local": [],
    }
    issues: list[dict[str, str]] = []
    parse_errors = []

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        if source_info.get("kind") == "executable":
            for lineno, line in enumerate(source.splitlines(), start=1):
                location = f"line {lineno}"
                for value in re.findall(r"""(?:s3://|https?://|/|\./|\.\./)[^\s"']+""", line):
                    value = value.rstrip("),;")
                    access_type = classify_data_reference(value)
                    if access_type:
                        add_data_access(data_access, access_type, value, location)
                    elif looks_like_local_file_path(value):
                        add_data_access(data_access, "local", value, location)
                if re.search(r"\bread\s+-p\b|\bselect\b", line):
                    issues.append(
                        issue(
                            "interactive_runtime",
                            "error",
                            "Shell entrypoint appears to prompt interactively.",
                            "Replace prompts with declared app.yaml inputs or environment variables.",
                            location,
                        )
                    )
            if not inputs:
                issues.append(
                    issue(
                        "missing_declared_parameters",
                        "info",
                        "No app inputs were inferred or declared for this executable entrypoint.",
                        "Declare executable inputs in app.yaml so CWL/DPS metadata can be generated.",
                    )
                )
            return {
                "source_kind": source_info["kind"],
                "code_cell_count": len(source_info.get("code_units", [])),
                "parameters_cell_index": source_info.get("parameters_cell_index"),
                "data_access": data_access,
                "issues": issues,
                "parse_errors": [],
                "lint_tools": lint_tool_summary(source_info),
            }
        return {
            "source_kind": source_info["kind"],
            "code_cell_count": len(source_info.get("code_units", [])),
            "parameters_cell_index": source_info.get("parameters_cell_index"),
            "data_access": data_access,
            "issues": [
                issue(
                    "python_syntax_error",
                    "error",
                    f"Source could not be parsed: {exc.msg}.",
                    "Fix syntax errors before generating a scalable package.",
                    f"line {exc.lineno}",
                )
            ],
            "parse_errors": [{"message": exc.msg, "line": exc.lineno}],
            "lint_tools": lint_tool_summary(source_info),
        }

    for module_name in detected_imports:
        if module_name in {"s3fs", "boto3", "botocore"}:
            add_data_access(data_access, "s3", f"import {module_name}", "imports")
        if module_name in {"pystac", "pystac_client"}:
            add_data_access(data_access, "stac", f"import {module_name}", "imports")
        if module_name in {"earthaccess", "cmr"}:
            add_data_access(data_access, "cmr", f"import {module_name}", "imports")
        if module_name == "maap":
            add_data_access(data_access, "cmr", "import maap", "imports")

    for node in ast.walk(tree):
        location = f"line {getattr(node, 'lineno', '?')}"

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            access_type = classify_data_reference(node.value)
            if access_type:
                add_data_access(data_access, access_type, node.value, location)
            if looks_like_local_file_path(node.value):
                issues.append(
                    issue(
                        "hardcoded_local_path",
                        "warning",
                        f"Hardcoded local path detected: {node.value}",
                        "Declare the path as an input parameter or stage it inside the runtime output/work directory.",
                        location,
                    )
                )

        if isinstance(node, ast.Call):
            call_name = get_call_name(node.func)
            lowered_call_name = call_name.lower()
            call_strings = string_literals(node)
            if "earthaccess.search_data" in lowered_call_name or lowered_call_name.endswith(".search_data"):
                add_data_access(data_access, "cmr", call_name, location)
            if lowered_call_name.endswith((".searchcollection", ".searchgranule")):
                add_data_access(data_access, "cmr", call_name, location)
            if "earthdata_s3_credentials" in lowered_call_name:
                add_data_access(data_access, "s3", call_name, location)
            if "stac" in lowered_call_name or "pystac" in lowered_call_name:
                add_data_access(data_access, "stac", call_name, location)
            if "s3filesystem" in lowered_call_name:
                add_data_access(data_access, "s3", call_name, location)
            if lowered_call_name.endswith((".to_raster", ".rio.to_raster")):
                add_data_access(data_access, "local", call_name, location)
            if is_data_read_call(call_name):
                values_to_classify = call_strings[:1]
                for value in values_to_classify:
                    access_type = classify_data_reference(value)
                    if access_type:
                        add_data_access(data_access, access_type, f"{call_name}({value})", location)
            if lowered_call_name in {"input", "ipywidgets.interact"} or lowered_call_name.startswith("ipywidgets."):
                issues.append(
                    issue(
                        "interactive_runtime",
                        "error",
                        f"Interactive call `{call_name}` blocks headless DPS/OGC execution.",
                        "Replace interactive prompts/widgets with declared app.yaml or argparse inputs.",
                        location,
                    )
                )
            if lowered_call_name.endswith(("datetime.now", "datetime.utcnow", "date.today", "time.time", "uuid4")):
                issues.append(
                    issue(
                        "nondeterministic_time",
                        "warning",
                        f"Runtime-dependent value `{call_name}` can make outputs non-reproducible.",
                        "Pass timestamps/run IDs explicitly or write them only as provenance metadata.",
                        location,
                    )
                )
            if lowered_call_name.endswith(("getenv", "os.getenv")):
                env_name = call_strings[0] if call_strings else ""
                if env_name and env_name not in inputs:
                    issues.append(
                        issue(
                            "undeclared_environment_dependency",
                            "warning",
                            f"Environment variable `{env_name}` is read but not declared as an input.",
                            "Document required environment variables in app.yaml or convert them to explicit parameters.",
                            location,
                        )
                    )

        if isinstance(node, ast.Subscript):
            value_name = get_call_name(node.value)
            if value_name == "os.environ":
                env_name = ""
                if isinstance(node.slice, ast.Constant):
                    env_name = str(node.slice.value)
                if env_name and env_name not in inputs:
                    issues.append(
                        issue(
                            "undeclared_environment_dependency",
                            "warning",
                            f"Environment variable `{env_name}` is read but not declared as an input.",
                            "Document required environment variables in app.yaml or convert them to explicit parameters.",
                            location,
                        )
                    )

    stochastic_imports = {"random", "torch", "tensorflow", "sklearn"} & set(detected_imports)
    if any(marker in source for marker in ("np.random", "numpy.random", ".random.")):
        stochastic_imports.add("numpy")
    source_lower = source.lower()
    has_seed = any(marker in source_lower for marker in (".seed(", "manual_seed(", "random_state="))
    if stochastic_imports and not has_seed:
        issues.append(
            issue(
                "missing_random_seed",
                "warning",
                f"Stochastic libraries imported without an obvious seed: {', '.join(sorted(stochastic_imports))}.",
                "Set deterministic seeds or expose a seed parameter when random behavior affects outputs.",
            )
        )

    for magic_line in source_info.get("magic_lines", []):
        issues.append(
            issue(
                "notebook_magic",
                "error",
                magic_line["message"],
                "Move shell setup into Dockerfile/build.sh or convert notebook magic to normal Python code.",
                f"notebook cell {magic_line.get('cell')}, line {magic_line.get('line')}",
            )
        )

    issues.extend(detect_implicit_cell_state(source_info))

    if not inputs:
        issues.append(
            issue(
                "missing_declared_parameters",
                "info",
                "No app inputs were inferred or declared.",
                "Add argparse options, a Papermill parameters cell, or an app.yaml inputs section.",
            )
        )

    return {
        "source_kind": source_info["kind"],
        "code_cell_count": len(source_info.get("code_units", [])),
        "parameters_cell_index": source_info.get("parameters_cell_index"),
        "data_access": data_access,
        "issues": issues,
        "parse_errors": parse_errors,
        "lint_tools": lint_tool_summary(source_info),
    }


def detect_implicit_cell_state(source_info: dict[str, Any]) -> list[dict[str, str]]:
    if source_info["kind"] != "notebook":
        return []

    issues: list[dict[str, str]] = []
    previous_assignments: set[str] = set()
    imported_names: set[str] = set()

    for unit in source_info.get("code_units", []):
        try:
            tree = ast.parse(unit["source"])
        except SyntaxError:
            continue

        loaded_names: set[str] = set()
        assigned_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loaded_names.add(node.id)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.For, ast.With)):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = list(node.targets)
                elif isinstance(node, ast.AnnAssign):
                    targets = [node.target]
                elif isinstance(node, ast.For):
                    targets = [node.target]
                for target in targets:
                    assigned_names.update(get_assigned_names(target))

        state_dependencies = sorted(
            name
            for name in loaded_names
            if name in previous_assignments and name not in imported_names and name not in KNOWN_GLOBAL_NAMES
        )
        if state_dependencies:
            issues.append(
                issue(
                    "implicit_notebook_state",
                    "info",
                    "Notebook cell depends on variables from earlier cells: "
                    + ", ".join(state_dependencies),
                    "Generated scripts run cells top-to-bottom; keep this order explicit or refactor shared state into functions.",
                    f"notebook cell {unit['index']}",
                )
            )

        previous_assignments.update(assigned_names)

    return issues


def lint_tool_summary(source_info: dict[str, Any]) -> dict[str, Any]:
    recommended = ["ruff", "flake8", "mypy"]
    if source_info["kind"] == "notebook":
        recommended.extend(["nbqa ruff", "nbqa mypy", "pynblint", "julynter"])
    return {
        "executed": [],
        "recommended": recommended,
        "note": "Install these tools in CI to enforce the same reproducibility checks automatically.",
    }


def build_build_script(
    name: str,
    entrypoint: str,
    detected_imports: list[str],
    dependency_map: dict[str, Any],
    runtime_config: dict[str, Any],
) -> str:
    validation_imports = [
        module_name
        for module_name in detected_imports
        if dependency_map.get(module_name) is not None
    ]
    validation_import_block = "\n".join(f"import {module_name}" for module_name in validation_imports)
    if runtime_config.get("type") == "executable":
        conda_entrypoint_validation = f'  chmod +x "${{basedir}}/{entrypoint}"'
        local_entrypoint_validation = f'  chmod +x "${{basedir}}/{entrypoint}"'
    else:
        conda_entrypoint_validation = (
            f'  conda run -p "${{ENV_PREFIX}}" python -m py_compile "${{basedir}}/{entrypoint}"'
        )
        local_entrypoint_validation = f'  "${{PYTHON_BIN}}" -m py_compile "${{basedir}}/{entrypoint}"'

    return f"""#!/usr/bin/env bash
set -euo pipefail

basedir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)"

determine_env_prefix() {{
  if [ -n "${{CONDA_ENV_PREFIX:-}}" ]; then
    printf '%s\\n' "${{CONDA_ENV_PREFIX}}"
    return
  fi

  if [ -w /opt/conda/envs ] || {{ [ ! -e /opt/conda/envs ] && [ -w /opt/conda ]; }}; then
    printf '%s\\n' "/opt/conda/envs/{name}"
    return
  fi

  printf '%s\\n' "${{HOME}}/.conda/envs/{name}"
}}

ENV_PREFIX="$(determine_env_prefix)"

if command -v conda >/dev/null 2>&1; then
  mkdir -p "$(dirname "${{ENV_PREFIX}}")"
  conda env remove -p "${{ENV_PREFIX}}" -y || true
  conda env create -f "${{basedir}}/env.yml" --prefix "${{ENV_PREFIX}}"
  conda clean -afy
{conda_entrypoint_validation}
  conda run -p "${{ENV_PREFIX}}" python - <<'PY'
{validation_import_block}
print("Environment validation successful.")
PY
else
  PYTHON_BIN="${{PYTHON_BIN:-python3}}"
  if ! command -v "${{PYTHON_BIN}}" >/dev/null 2>&1; then
    PYTHON_BIN="python"
  fi
  "${{PYTHON_BIN}}" -m pip install -r "${{basedir}}/requirements.txt"
{local_entrypoint_validation}
fi
"""


def build_report(
    app_config: dict[str, Any],
    detected_imports: list[str],
    inferred_inputs: dict[str, Any],
    analysis: dict[str, Any],
    llm_analysis: dict[str, Any],
    implicit_dependencies: dict[str, list[str]],
    dependencies: dict[str, list[str]],
    generated_files: list[str],
) -> str:
    report = {
        "name": app_config.get("name"),
        "version": app_config.get("version"),
        "target": app_config.get("target"),
        "entrypoint": app_config.get("entrypoint"),
        "runtime": app_config.get("runtime", {}),
        "inference": app_config.get("inference", {}),
        "detected_imports": detected_imports,
        "inferred_inputs": inferred_inputs,
        "analysis": analysis,
        "llm_analysis": llm_analysis,
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
        f"- Runtime: `{app_config.get('runtime', {}).get('type', 'python')}`",
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

    markdown_lines.extend(["", "## Static Analysis", ""])

    issue_counts: dict[str, int] = {}
    for item in analysis.get("issues", []):
        severity = item.get("severity", "info")
        issue_counts[severity] = issue_counts.get(severity, 0) + 1

    if issue_counts:
        markdown_lines.append(
            "- Findings: "
            + ", ".join(f"{severity}={count}" for severity, count in sorted(issue_counts.items()))
        )
    else:
        markdown_lines.append("- Findings: none")

    markdown_lines.append(
        f"- Source kind: `{analysis.get('source_kind')}` with `{analysis.get('code_cell_count')}` code unit(s)"
    )
    markdown_lines.append("- Data access:")
    for access_type, items in analysis.get("data_access", {}).items():
        markdown_lines.append(f"  - `{access_type}`: {len(items)} signal(s)")

    if analysis.get("issues"):
        markdown_lines.extend(["", "| Severity | Rule | Location | Guidance |", "| --- | --- | --- | --- |"])
        for item in analysis["issues"]:
            guidance = str(item.get("remediation", "")).replace("|", "\\|")
            location = str(item.get("location", "")).replace("|", "\\|")
            markdown_lines.append(
                f"| `{item.get('severity')}` | `{item.get('rule')}` | {location} | {guidance} |"
            )

    markdown_lines.extend(["", "## LLM-Assisted Analysis", ""])
    markdown_lines.append(f"- Status: `{llm_analysis.get('status', 'not_requested')}`")
    if llm_analysis.get("provider"):
        markdown_lines.append(f"- Provider: `{llm_analysis['provider']}`")
    if llm_analysis.get("model"):
        markdown_lines.append(f"- Model: `{llm_analysis['model']}`")
    if llm_analysis.get("message"):
        markdown_lines.append(f"- Message: {llm_analysis['message']}")
    if llm_analysis.get("response"):
        markdown_lines.extend(["", llm_analysis["response"], ""])

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
        help="Python script or .ipynb notebook to package. Defaults to input/nisar_access_subset.py.",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional app.yaml/app.yml metadata override. Not required; generated app.yaml is always emitted.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        choices=["ogc", "dps", "both", "ogc_dps"],
        help="Package target to record in generated metadata. Defaults to ogc.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory where generated package files are written.",
    )
    parser.add_argument(
        "--llm-analysis",
        action="store_true",
        help="Invoke the optional LLM semantic analysis pass.",
    )
    parser.add_argument(
        "--llm-provider",
        default=os.environ.get("LLM_PROVIDER", "auto"),
        choices=["auto", "openai", "anthropic"],
        help="LLM provider for --llm-analysis. auto prefers OPENAI_API_KEY, then ANTHROPIC_API_KEY.",
    )
    parser.add_argument(
        "--llm-model",
        default=os.environ.get("LLM_MODEL", ""),
        help="Optional model override for the selected LLM provider.",
    )
    parser.add_argument(
        "--openai-model",
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="OpenAI/ChatGPT model name used with --llm-analysis.",
    )
    parser.add_argument(
        "--anthropic-model",
        default=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
        help="Anthropic model name used with --llm-analysis.",
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
    source_info = read_source_file(script_path)

    app_config = infer_app_config(script_path, source_info, cli_args.target)
    manifest_path = discover_manifest(cli_args.manifest, script_path)
    if manifest_path:
        app_config = merge_dicts(app_config, normalize_manifest_config(load_yaml(manifest_path)))
        app_config.setdefault("inference", {})
        app_config["inference"]["manifest_required"] = False
        app_config["inference"]["manifest_override"] = str(
            manifest_path.relative_to(ROOT) if manifest_path.is_relative_to(ROOT) else manifest_path
        )
    app_config["target"] = normalize_target(app_config.get("target"))

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
    inputs = app_config.get("inputs", {})
    outputs = app_config.get("outputs", {})
    resources = app_config.get("resources", {})
    runtime_config = app_config.get("runtime", infer_runtime_config(source_info))
    run_commands = build_run_commands(runtime_config, entrypoint)

    output_config = outputs.get("output", {})
    output_description = output_config.get("description", "Generated output directory.")

    entrypoint_dst = output_dir / entrypoint

    detected_imports = detect_imports_from_source(source_info["source"])
    app_config["base_container"] = infer_base_container(
        detected_imports, app_config.get("base_container", DEFAULT_BASE_CONTAINER)
    )
    base_container = app_config.get("base_container", "")
    implicit_dependencies = detect_implicit_dependencies_from_source(source_info["source"], detected_imports)
    if target_includes(app_config["target"], "dps"):
        implicit_dependencies.setdefault("conda", [])
        if "pyyaml" not in implicit_dependencies["conda"]:
            implicit_dependencies["conda"].append("pyyaml")
            implicit_dependencies["conda"].sort()
    dependencies = resolve_dependencies(
        detected_imports,
        dependency_map,
        app_config,
        implicit_dependencies,
    )
    analysis = analyze_source(source_info, detected_imports, inputs)
    llm_prompt = build_llm_prompt(app_config, analysis)
    llm_analysis = run_llm_analysis(
        llm_prompt,
        cli_args.llm_analysis,
        cli_args.llm_provider,
        cli_args.llm_model or None,
        cli_args.openai_model,
        cli_args.anthropic_model,
    )
    cwl_file_name = "application.cwl"

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
        "cwl_workflow_inputs_block": build_cwl_workflow_inputs_block(inputs),
        "cwl_workflow_step_inputs_block": build_cwl_workflow_step_inputs_block(inputs),
        "cwl_file_name": cwl_file_name,
        "conda_run_command": run_commands["conda"],
        "local_run_command": run_commands["local"],
        "ram_min": str(resources.get("ram_min", 8)),
        "cores_min": str(resources.get("cores_min", 2)),
        "outdir_max": str(resources.get("outdir_max", 20)),
    }

    if output_dir.exists():
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    materialize_entrypoint(source_info, entrypoint_dst)

    generated_files = [entrypoint]

    files_to_generate = {
        "run.sh": "run.sh.template",
        "env.yml": "env.yml.template",
        "Dockerfile": "Dockerfile.template",
    }

    if target_includes(app_config["target"], "dps"):
        files_to_generate["algorithm_config.yaml"] = "algorithm.yml.template"
        files_to_generate["algorithm.yml"] = "algorithm.yml.template"

    if target_includes(app_config["target"], "ogc"):
        files_to_generate[cwl_file_name] = "commandline.cwl.template"
        files_to_generate["workflow.cwl"] = "workflow.cwl.template"

    for output_name, template_name in files_to_generate.items():
        rendered = render_template(template_name, context)
        output_path = output_dir / output_name
        write_text(output_path, rendered)
        generated_files.append(output_name)

    build_sh = build_build_script(name, entrypoint, detected_imports, dependency_map, runtime_config)

    write_text(output_dir / "build.sh", build_sh)
    make_executable(output_dir / "build.sh")
    generated_files.append("build.sh")

    requirements_txt = build_requirements_txt(dependencies)
    write_text(output_dir / "requirements.txt", requirements_txt)
    generated_files.append("requirements.txt")

    write_text(output_dir / "app.yaml", build_generated_app_manifest(app_config))
    generated_files.append("app.yaml")

    write_text(output_dir / "analysis.json", json.dumps(analysis, indent=2) + "\n")
    generated_files.append("analysis.json")

    write_text(output_dir / "llm_analysis_prompt.json", llm_prompt + "\n")
    generated_files.append("llm_analysis_prompt.json")

    write_text(output_dir / "stac-input.json", build_stac_input_manifest(app_config, inputs))
    generated_files.append("stac-input.json")

    write_text(output_dir / "stac-output.json", build_stac_output_manifest(app_config, outputs))
    generated_files.append("stac-output.json")

    validate_sh = build_validation_script(app_config["target"], cwl_file_name)
    write_text(output_dir / "validate_package.sh", validate_sh)
    make_executable(output_dir / "validate_package.sh")
    generated_files.append("validate_package.sh")

    if target_includes(app_config["target"], "dps"):
        write_text(output_dir / "register_dps.py", build_dps_registration_script())
        make_executable(output_dir / "register_dps.py")
        generated_files.append("register_dps.py")

    if target_includes(app_config["target"], "ogc"):
        write_text(output_dir / "publish_ogc.py", build_ogc_publish_script())
        make_executable(output_dir / "publish_ogc.py")
        generated_files.append("publish_ogc.py")

    readme = f"""# {name}

This application package was generated from a Python script or notebook by the package generator proof of concept.

The generator can run without an `app.yaml` manifest, or it can merge a minimal manifest declaring target, schemas, resources, and base container preference. It infers command-line inputs from `argparse` and Papermill-style notebook parameters, detects imports with the Python AST, resolves dependencies, and renders the package files from templates.

## Entrypoint

`{entrypoint}`

Runtime type: `{runtime_config.get('type', 'python')}`.

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `requirements.txt`
- `app.yaml`
- `analysis.json`
- `llm_analysis_prompt.json`
- `{entrypoint}`
- `report.md`

Review `report.md` and `analysis.json` before OGC execution, MAAP DPS registration, or registry publication.

## Conda environment location

The generated scripts use `CONDA_ENV_PREFIX` when it is set. Otherwise they use
`/opt/conda/envs/{name}` when that location is writable, and fall back to the
user-writable path:

`$HOME/.conda/envs/{name}`

## Runtime tip

For remote sensing jobs, use the smallest representative input for a first
smoke test. If the generated CLI exposes a bbox, index-window, limit, or direct
granule/S3 URL parameter, prefer that over a full collection search.

## Optional LLM review

This package includes `llm_analysis_prompt.json`. You can paste it into ChatGPT
manually, or regenerate with `--llm-analysis --llm-provider openai` and
`OPENAI_API_KEY` set to call the OpenAI API from the terminal.

## Validation and publication

Run `./validate_package.sh` to compile Python, validate CWL when `cwltool` is installed, and build the container when Docker is available.

For DPS registration set `MAAP_API_URL` and `MAAP_API_TOKEN`, then run `./register_dps.py`.
For OGC publication set `OGC_REGISTRY_URL` (and optionally `OGC_REGISTRY_TOKEN`), then run `./publish_ogc.py`.
"""

    write_text(output_dir / "README.md", readme)
    generated_files.append("README.md")

    generated_files.append("report.md")
    report = build_report(
        app_config,
        detected_imports,
        inputs,
        analysis,
        llm_analysis,
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
