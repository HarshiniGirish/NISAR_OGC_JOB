from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
from typing import Any


IMPLICIT_RULE_DESCRIPTIONS = {
    ".to_zarr": "Zarr output requires zarr and compatible numcodecs.",
    "s3://": "S3 URLs require filesystem/authentication helpers.",
    "s3fs": "s3fs import implies fsspec, boto3, and botocore runtime support.",
    "rasterio.open": "Rasterio reader requires rasterio.",
    "h5py.File": "HDF5 reader requires h5py.",
    "open_dataset": "xarray open_dataset may require backend engines.",
    "earthaccess.login": "Earthdata login requires earthaccess.",
    "MAAP()": "MAAP client usage requires maap-py.",
}


def build_dependency_graph(
    *,
    detected_imports: list[str],
    dependency_map: dict[str, Any],
    implicit_dependencies: dict[str, list[str]],
    resolved_dependencies: dict[str, list[str]],
    source: str,
    llm_suggestions: list[str] | None = None,
) -> dict[str, Any]:
    llm_suggestions = llm_suggestions or []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for module_name in sorted(detected_imports):
        package = dependency_map.get(module_name)
        nodes.append({"id": f"import:{module_name}", "type": "import", "name": module_name})
        if package:
            nodes.append({"id": f"package:{package}", "type": "package", "name": package, "trusted": True})
            edges.append(
                {
                    "from": f"import:{module_name}",
                    "to": f"package:{package}",
                    "reason": "manual dependency_map.yml",
                    "trusted": True,
                }
            )
        elif package is None:
            nodes.append({"id": f"stdlib:{module_name}", "type": "stdlib_or_unmapped", "name": module_name})
        else:
            unresolved.append(module_name)

    for manager, packages in implicit_dependencies.items():
        for package in packages:
            nodes.append({"id": f"package:{package}", "type": "package", "name": package, "trusted": True})
            edges.append(
                {
                    "from": f"implicit:{manager}",
                    "to": f"package:{package}",
                    "reason": _implicit_reason(package, source),
                    "trusted": True,
                }
            )

    for manager, packages in resolved_dependencies.items():
        for package in packages:
            nodes.append({"id": f"resolved:{manager}:{package}", "type": "resolved", "name": package})

    validated_llm = []
    rejected_llm = []
    for package in llm_suggestions:
        validation = validate_package_suggestion(package, dependency_map)
        item = {"package": package, **validation}
        if validation["valid"]:
            validated_llm.append(item)
            nodes.append({"id": f"package:{package}", "type": "package", "name": package, "trusted": False})
            edges.append(
                {
                    "from": "llm:suggestion",
                    "to": f"package:{package}",
                    "reason": "LLM suggestion validated before use",
                    "trusted": False,
                }
            )
        else:
            rejected_llm.append(item)

    deduped_nodes = {node["id"]: node for node in nodes}
    graph = {
        "summary": {
            "import_count": len(detected_imports),
            "resolved_conda_count": len(resolved_dependencies.get("conda", [])),
            "resolved_pip_count": len(resolved_dependencies.get("pip", [])),
            "implicit_count": sum(len(items) for items in implicit_dependencies.values()),
            "unresolved_count": len(unresolved),
            "validated_llm_suggestion_count": len(validated_llm),
            "rejected_llm_suggestion_count": len(rejected_llm),
        },
        "nodes": list(deduped_nodes.values()),
        "edges": edges,
        "unresolved_imports": unresolved,
        "validated_llm_suggestions": validated_llm,
        "rejected_llm_suggestions": rejected_llm,
    }
    return graph


def write_dependency_graph(graph: dict[str, Any], output_dir: str | Path) -> str:
    path = Path(output_dir) / "dependency_graph.json"
    path.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    return path.name


def validate_package_suggestion(package: str, dependency_map: dict[str, Any]) -> dict[str, Any]:
    trusted_packages = {str(value) for value in dependency_map.values() if value}
    if package in trusted_packages:
        return {
            "valid": True,
            "source": "manual dependency mapping",
            "reason": "Suggested package already appears in dependency_map.yml.",
        }
    package_root = package.split("=", 1)[0].split("<", 1)[0].split(">", 1)[0]
    try:
        importlib.metadata.version(package_root)
    except importlib.metadata.PackageNotFoundError:
        return {
            "valid": False,
            "source": "package metadata lookup",
            "reason": "Package is not installed locally and is not in the trusted dependency map.",
        }
    return {
        "valid": True,
        "source": "package metadata lookup",
        "reason": "Package metadata is available in the local Python environment.",
    }


def _implicit_reason(package: str, source: str) -> str:
    for marker, reason in IMPLICIT_RULE_DESCRIPTIONS.items():
        if marker in source:
            return reason
    if package in {"zarr<3", "numcodecs<0.16"}:
        return IMPLICIT_RULE_DESCRIPTIONS[".to_zarr"]
    if package in {"s3fs", "fsspec", "boto3", "botocore"}:
        return IMPLICIT_RULE_DESCRIPTIONS["s3://"]
    return "Implicit dependency rule from generator."
