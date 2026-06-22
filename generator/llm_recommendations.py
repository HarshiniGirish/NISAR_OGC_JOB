from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


RECOMMENDATION_SCHEMA_KEYS = {
    "recommended_entrypoint": str,
    "candidate_functions": list,
    "notebook_only_cells": list,
    "required_refactors": list,
    "suggested_inputs": list,
    "suggested_outputs": list,
    "risks_warnings": list,
    "confidence_score": (int, float),
}


def build_structured_recommendations(
    *,
    readiness_scan: dict[str, Any],
    mcp_defaults: dict[str, Any] | None = None,
    dependency_graph: dict[str, Any] | None = None,
    enabled: bool = False,
    provider: str = "auto",
    model: str = "",
) -> dict[str, Any]:
    fallback = rule_based_recommendations(readiness_scan, mcp_defaults, dependency_graph)
    if not enabled:
        fallback["status"] = "not_requested"
        fallback["message"] = "Structured LLM recommendations were not requested."
        return fallback

    resolved_provider = _resolve_provider(provider)
    if resolved_provider == "openai":
        result = _call_openai(readiness_scan, mcp_defaults or {}, dependency_graph or {}, model or "gpt-4o-mini")
    elif resolved_provider == "anthropic":
        result = _call_anthropic(
            readiness_scan,
            mcp_defaults or {},
            dependency_graph or {},
            model or "claude-3-5-sonnet-latest",
        )
    else:
        fallback["status"] = "skipped"
        fallback["message"] = f"Unsupported or unavailable LLM provider: {resolved_provider}"
        return fallback

    if result.get("status") != "completed":
        fallback["status"] = result.get("status", "failed")
        fallback["message"] = result.get("message", "")
        fallback["fallback_used"] = True
        return fallback

    validation = validate_recommendation_schema(result.get("recommendations", {}))
    if not validation["valid"]:
        fallback["status"] = "invalid_llm_output"
        fallback["message"] = "; ".join(validation["errors"])
        fallback["fallback_used"] = True
        return fallback

    recommendations = dict(result["recommendations"])
    recommendations.update(
        {
            "status": "completed",
            "provider": resolved_provider,
            "model": result.get("model", model),
            "schema_validation": validation,
            "fallback_used": False,
        }
    )
    return recommendations


def rule_based_recommendations(
    readiness_scan: dict[str, Any],
    mcp_defaults: dict[str, Any] | None = None,
    dependency_graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    units = readiness_scan.get("units", [])
    candidates = [
        unit
        for unit in units
        if unit.get("classification") in {"DPS-ready", "DPS-candidate-after-refactor"}
    ]
    candidates.sort(key=lambda item: item.get("dps_suitability_score", 0), reverse=True)
    notebook_only = [
        unit.get("name", "")
        for unit in units
        if unit.get("classification") == "Notebook-only"
    ]
    blocking = [
        unit
        for unit in units
        if unit.get("classification") == "Blocking issue"
    ]
    suggested_inputs = _suggested_inputs(readiness_scan, mcp_defaults or {})
    suggested_outputs = sorted(
        {
            output
            for unit in units
            for output in unit.get("detected_outputs", [])
        }
    )
    entrypoint = candidates[0].get("name", "") if candidates else ""
    if entrypoint.startswith("notebook cell"):
        entrypoint = "generated package entrypoint script"

    return {
        "status": "rule_based",
        "recommended_entrypoint": entrypoint,
        "candidate_functions": [
            {
                "name": unit.get("name", ""),
                "classification": unit.get("classification", ""),
                "score": unit.get("dps_suitability_score", 0),
                "reason": unit.get("reason", ""),
            }
            for unit in candidates
        ],
        "notebook_only_cells": notebook_only,
        "required_refactors": sorted(
            {
                refactor
                for unit in units
                for refactor in unit.get("suggested_refactors", [])
            }
        ),
        "suggested_inputs": suggested_inputs,
        "suggested_outputs": suggested_outputs or ["output"],
        "risks_warnings": [
            f"{unit.get('name')}: {unit.get('reason')}"
            for unit in blocking
        ],
        "confidence_score": _confidence_score(readiness_scan, dependency_graph or {}),
        "fallback_used": False,
    }


def validate_recommendation_schema(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["LLM recommendation payload must be a JSON object."]}
    for key, expected_type in RECOMMENDATION_SCHEMA_KEYS.items():
        if key not in payload:
            errors.append(f"Missing key: {key}")
            continue
        if not isinstance(payload[key], expected_type):
            errors.append(f"{key} has wrong type")
    if "confidence_score" in payload:
        try:
            value = float(payload["confidence_score"])
            if value < 0 or value > 1:
                errors.append("confidence_score must be between 0 and 1")
        except (TypeError, ValueError):
            errors.append("confidence_score must be numeric")
    return {"valid": not errors, "errors": errors}


def _suggested_inputs(readiness_scan: dict[str, Any], mcp_defaults: dict[str, Any]) -> list[dict[str, Any]]:
    detected = {
        name
        for unit in readiness_scan.get("units", [])
        for name in unit.get("detected_inputs", [])
    }
    suggestions_by_parameter = {
        item.get("parameter"): item
        for item in mcp_defaults.get("suggestions", [])
        if item.get("parameter")
    }
    result = []
    for name in sorted(detected | set(suggestions_by_parameter)):
        default = suggestions_by_parameter.get(name, {})
        result.append(
            {
                "name": name,
                "suggested_default": default.get("suggested_value", ""),
                "source": default.get("source", "static scan"),
                "user_can_override": True,
            }
        )
    return result


def _confidence_score(readiness_scan: dict[str, Any], dependency_graph: dict[str, Any]) -> float:
    summary = readiness_scan.get("summary", {})
    score = float(summary.get("dps_suitability_score", 0)) / 100.0
    unresolved = dependency_graph.get("summary", {}).get("unresolved_count", 0)
    blocking = summary.get("blocking_count", 0)
    score -= min(0.25, unresolved * 0.05)
    score -= min(0.35, blocking * 0.1)
    return round(max(0.0, min(1.0, score)), 2)


def _resolve_provider(provider: str) -> str:
    provider = provider.lower()
    if provider != "auto":
        return provider
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def _prompt(readiness_scan: dict[str, Any], mcp_defaults: dict[str, Any], dependency_graph: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Recommend DPS/OGCification actions from a readiness scan. Return JSON only.",
            "readiness_scan": readiness_scan,
            "mcp_default_suggestions": mcp_defaults,
            "dependency_graph": dependency_graph,
            "required_schema": {
                "recommended_entrypoint": "string",
                "candidate_functions": ["objects with name, reason, score"],
                "notebook_only_cells": ["cell identifiers"],
                "required_refactors": ["strings"],
                "suggested_inputs": ["objects with name, suggested_default, reason"],
                "suggested_outputs": ["strings"],
                "risks_warnings": ["strings"],
                "confidence_score": "number between 0 and 1",
            },
            "safety_rule": "Do not rewrite package files. Recommendations are advisory and must be validated.",
        },
        indent=2,
    )


def _call_openai(
    readiness_scan: dict[str, Any],
    mcp_defaults: dict[str, Any],
    dependency_graph: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "message": "OPENAI_API_KEY is not set."}
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only valid JSON matching the requested schema.",
                },
                {"role": "user", "content": _prompt(readiness_scan, mcp_defaults, dependency_graph)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return {"status": "completed", "model": model, "recommendations": json.loads(content)}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI recommendation failed: {exc}"}


def _call_anthropic(
    readiness_scan: dict[str, Any],
    mcp_defaults: dict[str, Any],
    dependency_graph: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "skipped", "message": "ANTHROPIC_API_KEY is not set."}
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 2000,
            "messages": [
                {
                    "role": "user",
                    "content": _prompt(readiness_scan, mcp_defaults, dependency_graph),
                }
            ],
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
        text = "\n".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return {"status": "completed", "model": model, "recommendations": json.loads(text)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"Anthropic recommendation failed: {exc}"}
