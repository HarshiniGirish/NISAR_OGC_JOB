from __future__ import annotations

import importlib.metadata
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
CONDA_FORGE_REPODATA_URL = "https://conda.anaconda.org/conda-forge/noarch/repodata.json"


def resolve_dynamic_dependency_map(
    *,
    detected_imports: list[str],
    dependency_map: dict[str, Any],
    enable_online_lookup: bool = False,
    llm_suggestions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve imports not covered by the curated map.

    The curated dependency_map.yml remains the trusted first source. This layer
    adds reviewable, provenance-tagged suggestions for imports that otherwise
    would be unresolved or misclassified.
    """

    llm_suggestions = llm_suggestions or {}
    package_distributions = importlib.metadata.packages_distributions()
    suggestions: list[dict[str, Any]] = []
    overrides: dict[str, str] = {}

    for module_name in sorted(set(detected_imports)):
        curated_value = dependency_map.get(module_name, "__missing__")
        if curated_value != "__missing__":
            suggestions.append(
                _suggestion(
                    module_name,
                    curated_value,
                    "dependency_map.yml",
                    "high",
                    curated_value is not None,
                    "Curated local dependency map entry.",
                    "conda" if curated_value else "stdlib",
                )
            )
            continue

        if _is_stdlib(module_name):
            suggestions.append(
                _suggestion(
                    module_name,
                    None,
                    "python stdlib",
                    "high",
                    False,
                    "Import is part of the Python standard library.",
                    "stdlib",
                )
            )
            continue

        local_package = _local_distribution(module_name, package_distributions)
        if local_package:
            suggestions.append(
                _suggestion(
                    module_name,
                    local_package,
                    "importlib.metadata",
                    "high",
                    True,
                    "Installed package metadata maps this import to a distribution.",
                    "conda",
                )
            )
            overrides[module_name] = local_package
            continue

        online = _online_lookup(module_name) if enable_online_lookup else {}
        if online.get("package"):
            package = str(online["package"])
            suggestions.append(
                _suggestion(
                    module_name,
                    package,
                    online.get("source", "online lookup"),
                    online.get("confidence", "medium"),
                    True,
                    online.get("reason", "Package found through online metadata lookup."),
                    online.get("manager", "conda"),
                )
            )
            overrides[module_name] = package
            continue

        llm_package = llm_suggestions.get(module_name)
        if llm_package and _valid_package_name(llm_package):
            suggestions.append(
                _suggestion(
                    module_name,
                    llm_package,
                    "llm_suggestion_unvalidated",
                    "low",
                    False,
                    "LLM suggested this package, but it needs online/local validation before use.",
                    "review",
                )
            )
        else:
            suggestions.append(
                _suggestion(
                    module_name,
                    None,
                    "unresolved",
                    "low",
                    False,
                    "No trusted dependency mapping found.",
                    "review",
                )
            )

    return {
        "source": "dynamic_dependency_resolver",
        "online_lookup_enabled": enable_online_lookup,
        "overrides": overrides,
        "suggestions": suggestions,
        "summary": {
            "detected_import_count": len(set(detected_imports)),
            "override_count": len(overrides),
            "unresolved_count": sum(1 for item in suggestions if item["source"] == "unresolved"),
            "stdlib_count": sum(1 for item in suggestions if item["manager"] == "stdlib"),
        },
    }


def write_dynamic_dependency_report(report: dict[str, Any], output_dir: str | Path) -> str:
    path = Path(output_dir) / "dynamic_dependency_resolution.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path.name


def merge_dependency_map_with_overrides(
    dependency_map: dict[str, Any], dynamic_report: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(dependency_map)
    for module_name, package_name in dynamic_report.get("overrides", {}).items():
        merged[module_name] = package_name
    return merged


def _suggestion(
    module_name: str,
    package_name: str | None,
    source: str,
    confidence: str,
    validated: bool,
    reason: str,
    manager: str,
) -> dict[str, Any]:
    return {
        "import": module_name,
        "package": package_name,
        "source": source,
        "confidence": confidence,
        "validated": validated,
        "reason": reason,
        "manager": manager,
    }


def _is_stdlib(module_name: str) -> bool:
    root = module_name.split(".", 1)[0]
    return root in getattr(sys, "stdlib_module_names", set())


def _local_distribution(module_name: str, package_distributions: dict[str, list[str]]) -> str:
    distributions = package_distributions.get(module_name) or package_distributions.get(
        module_name.replace("_", "-")
    )
    if not distributions:
        return ""
    return _normalize_distribution_name(distributions[0])


def _online_lookup(module_name: str) -> dict[str, Any]:
    candidates = [module_name, module_name.replace("_", "-")]
    for candidate in candidates:
        if _conda_forge_has_package(candidate):
            return {
                "package": candidate,
                "source": "conda-forge repodata",
                "confidence": "medium",
                "manager": "conda",
                "reason": "Package name was found in conda-forge repodata.",
            }
    for candidate in candidates:
        if _pypi_has_package(candidate):
            return {
                "package": candidate,
                "source": "PyPI metadata",
                "confidence": "medium",
                "manager": "pip",
                "reason": "Package name was found in PyPI metadata.",
            }
    return {}


def _conda_forge_has_package(package_name: str) -> bool:
    try:
        with urllib.request.urlopen(CONDA_FORGE_REPODATA_URL, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    packages = payload.get("packages", {})
    normalized = package_name.lower().replace("_", "-")
    return any(filename.split("-", 1)[0].lower() == normalized for filename in packages)


def _pypi_has_package(package_name: str) -> bool:
    if not _valid_package_name(package_name):
        return False
    url = PYPI_JSON_URL.format(package=package_name)
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def _normalize_distribution_name(value: str) -> str:
    return value.replace("_", "-").lower()


def _valid_package_name(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", value))
