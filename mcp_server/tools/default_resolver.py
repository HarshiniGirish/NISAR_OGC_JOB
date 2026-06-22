from __future__ import annotations

import re
from typing import Any


PARAMETERS = (
    "short_name",
    "collection_id",
    "concept_id",
    "version",
    "asset_href",
    "asset_key",
    "bbox",
    "datetime",
    "crs",
    "group",
    "variables",
    "access_mode",
    "example_input_file",
    "output_directory",
)

SHORT_NAME_RE = re.compile(r"\b[A-Z0-9]+(?:_[A-Z0-9]+)+(?:-[A-Z0-9]+)?_V\d+\b")
CONCEPT_ID_RE = re.compile(r"\b[CG]\d{6,}-[A-Z0-9_]+\b")
VERSION_RE = re.compile(r"(?:_V|v)(\d+(?:\.\d+)*)\b")
GROUP_RE = re.compile(r"(/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)+)")
CRS_RE = re.compile(r"\bEPSG:\d+\b", re.I)


def resolve_default_values(
    *,
    evidence: dict[str, Any] | None = None,
    dataset_facts: dict[str, Any] | None = None,
    user_config: dict[str, Any] | None = None,
    stac_url: str = "",
) -> dict[str, Any]:
    evidence = evidence or {}
    dataset_facts = dataset_facts or {}
    user_config = user_config or {}

    suggestions = []
    suggestions.extend(_from_user_config(user_config))
    suggestions.extend(_from_evidence(evidence, stac_url))
    suggestions.extend(_from_dataset_facts(dataset_facts))
    suggestions.extend(_fallbacks(evidence))

    deduped: dict[str, dict[str, Any]] = {}
    for suggestion in suggestions:
        parameter = suggestion.get("parameter", "")
        if not parameter:
            continue
        previous = deduped.get(parameter)
        if previous is None or _confidence_rank(suggestion) > _confidence_rank(previous):
            deduped[parameter] = suggestion

    return {
        "source": "mcp_default_resolver",
        "stac_url": stac_url,
        "live_metadata": bool(dataset_facts.get("live_metadata", False)),
        "suggestions": [deduped[key] for key in sorted(deduped)],
    }


def _suggestion(
    parameter: str,
    value: Any,
    source: str,
    confidence: str,
    reason: str,
    *,
    user_can_override: bool = True,
) -> dict[str, Any]:
    return {
        "parameter": parameter,
        "suggested_value": value,
        "source": source,
        "confidence": confidence,
        "reason": reason,
        "user_can_override": user_can_override,
    }


def _from_user_config(user_config: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    inputs = user_config.get("inputs", {})
    for name, config in inputs.items():
        if name not in PARAMETERS or not isinstance(config, dict) or config.get("default", "") in ("", None):
            continue
        suggestions.append(
            _suggestion(
                name,
                config["default"],
                "user app.yaml",
                "high",
                "User supplied this default in the app manifest.",
            )
        )
    return suggestions


def _from_evidence(evidence: dict[str, Any], stac_url: str) -> list[dict[str, Any]]:
    source_text = " ".join(
        [
            str(evidence.get("source", {}).get("path", "")),
            " ".join(str(url) for url in evidence.get("urls", [])),
            " ".join(str(item) for item in evidence.get("collections", [])),
        ]
    )
    suggestions = []
    short_names = SHORT_NAME_RE.findall(source_text)
    if short_names:
        suggestions.append(
            _suggestion(
                "short_name",
                short_names[0],
                "static source evidence",
                "medium",
                "Detected a collection-like short_name pattern in source URLs or inputs.",
            )
        )
    concept_ids = CONCEPT_ID_RE.findall(source_text)
    if concept_ids:
        parameter = "collection_id" if concept_ids[0].startswith("C") else "concept_id"
        suggestions.append(
            _suggestion(
                parameter,
                concept_ids[0],
                "static source evidence",
                "medium",
                "Detected a CMR concept-id pattern in source evidence.",
            )
        )
    version_match = VERSION_RE.search(source_text)
    if version_match:
        suggestions.append(
            _suggestion(
                "version",
                version_match.group(1),
                "static source evidence",
                "low",
                "Detected a version-like token in source evidence.",
            )
        )
    urls = [str(url) for url in evidence.get("urls", [])]
    if urls:
        suggestions.append(
            _suggestion(
                "asset_href",
                urls[0],
                "static source evidence",
                "medium",
                "Detected an asset URL in the user code.",
            )
        )
        suggestions.append(
            _suggestion(
                "access_mode",
                "s3" if urls[0].startswith("s3://") else "https",
                "static source evidence",
                "medium",
                "Access mode follows the detected asset URL scheme.",
            )
        )
    crs_match = CRS_RE.search(source_text)
    if crs_match:
        suggestions.append(
            _suggestion("crs", crs_match.group(0).upper(), "static source evidence", "medium", "Detected EPSG code.")
        )
    if stac_url:
        suggestions.append(
            _suggestion(
                "collection_id",
                "",
                "MAAP STAC endpoint context",
                "low",
                "MAAP STAC endpoint is configured; lookup can resolve this when collection hints are available.",
            )
        )
    return suggestions


def _from_dataset_facts(dataset_facts: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = []
    granule = dataset_facts.get("cmr_granule", {})
    collection = dataset_facts.get("cmr_collection", {})
    asset = dataset_facts.get("asset_inspection", {})
    urls = []
    for key in ("s3_urls", "https_urls", "zarr_urls"):
        urls.extend(granule.get(key, []) or [])
    if urls:
        suggestions.append(
            _suggestion(
                "asset_href",
                urls[0],
                "MAAP/STAC/CMR lookup",
                "high" if dataset_facts.get("live_metadata") else "medium",
                "Dataset facts found a candidate access URL.",
            )
        )
    concept_id = collection.get("concept_id") or collection.get("conceptId")
    if concept_id:
        suggestions.append(
            _suggestion(
                "collection_id",
                concept_id,
                "MAAP/STAC/CMR lookup",
                "high" if dataset_facts.get("live_metadata") else "medium",
                "Dataset facts include a collection concept id.",
            )
        )
    variables = asset.get("variables", [])
    if variables:
        suggestions.append(
            _suggestion(
                "variables",
                ",".join(str(item) for item in variables),
                "asset inspection",
                "medium",
                "Asset inspection detected readable variables.",
            )
        )
    groups = [value for value in asset.get("groups", []) if isinstance(value, str)]
    if groups:
        suggestions.append(
            _suggestion("group", groups[0], "asset inspection", "medium", "Asset inspection detected HDF5 groups.")
        )
    return suggestions


def _fallbacks(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = [
        _suggestion(
            "output_directory",
            "output",
            "documented generator fallback",
            "high",
            "Generated OGC/DPS packages write outputs under the output directory.",
        )
    ]
    operations = set(evidence.get("operations", []))
    if "direct_s3" in operations:
        value = "s3"
    elif "https_access" in operations:
        value = "https"
    else:
        value = "auto"
    suggestions.append(
        _suggestion(
            "access_mode",
            value,
            "documented fallback logic",
            "low",
            "Access mode fallback is derived from detected operations, not MAAP docs.",
        )
    )
    return suggestions


def _confidence_rank(suggestion: dict[str, Any]) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(str(suggestion.get("confidence", "")).lower(), 0)
