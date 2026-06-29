from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ALLOWED_CLASSIFICATIONS = {
    "DPS-ready",
    "DPS-candidate-after-refactor",
    "Notebook-only",
    "Blocking issue",
}


def review_dps_readiness_with_ai(
    *,
    readiness_scan: dict[str, Any],
    analysis: dict[str, Any],
    mcp_defaults: dict[str, Any],
    dependency_graph: dict[str, Any],
    enabled: bool,
    provider: str = "auto",
    model: str = "",
) -> dict[str, Any]:
    fallback = _fallback_review(readiness_scan)
    if not enabled:
        fallback["status"] = "not_requested"
        fallback["message"] = "AI DPS-readiness review was not requested."
        return fallback

    if _resolve_provider(provider) != "openai":
        fallback["status"] = "fallback"
        fallback["message"] = "OpenAI is unavailable; using rule-based DPS-readiness scan."
        return fallback

    result = _call_openai_review(
        readiness_scan=readiness_scan,
        analysis=analysis,
        mcp_defaults=mcp_defaults,
        dependency_graph=dependency_graph,
        model=model or "gpt-4o-mini",
    )
    if result.get("status") != "completed":
        fallback["status"] = "fallback"
        fallback["message"] = result.get("message", "OpenAI DPS-readiness review failed.")
        return fallback

    validation = validate_ai_readiness_review(result.get("review", {}), readiness_scan)
    if not validation["valid"]:
        fallback["status"] = "fallback"
        fallback["message"] = "OpenAI DPS-readiness review failed validation: " + "; ".join(
            validation["errors"]
        )
        return fallback

    review = result["review"]
    review.update(
        {
            "status": "completed",
            "provider": "openai",
            "model": result.get("model", model),
            "validation": validation,
        }
    )
    return review


def validate_ai_readiness_review(review: dict[str, Any], readiness_scan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(review, dict):
        return {"valid": False, "errors": ["Review must be a JSON object."]}
    units = review.get("units")
    if not isinstance(units, list):
        errors.append("units must be a list.")
        return {"valid": False, "errors": errors}
    scan_names = {unit.get("name") for unit in readiness_scan.get("units", [])}
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            errors.append(f"unit {index} must be an object.")
            continue
        if unit.get("name") not in scan_names:
            errors.append(f"unit {index} references unknown unit name.")
        if unit.get("ai_classification") not in ALLOWED_CLASSIFICATIONS:
            errors.append(f"unit {index} has invalid ai_classification.")
        if not isinstance(unit.get("confidence", 0), (int, float)):
            errors.append(f"unit {index} confidence must be numeric.")
    if "recommended_dps_job" in review and not isinstance(review["recommended_dps_job"], dict):
        errors.append("recommended_dps_job must be an object.")
    return {"valid": not errors, "errors": errors}


def write_ai_readiness_review(review: dict[str, Any], output_dir: str | Path) -> list[str]:
    path = Path(output_dir)
    json_path = path / "ai_dps_readiness_review.json"
    md_path = path / "ai_dps_readiness_review.md"
    json_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_ai_readiness_review_markdown(review), encoding="utf-8")
    return [json_path.name, md_path.name]


def render_ai_readiness_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# AI DPS Readiness Review",
        "",
        f"- Status: `{review.get('status', '')}`",
        f"- Provider: `{review.get('provider', '')}`",
        f"- Model: `{review.get('model', '')}`",
        f"- Message: {review.get('message', '')}",
        "",
        "## Recommended DPS Job",
        "",
    ]
    job = review.get("recommended_dps_job", {})
    if job:
        for key, value in job.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("No AI job recommendation was provided.")
    lines.extend(["", "## Unit Reviews", ""])
    for unit in review.get("units", []):
        lines.append(
            "- `{name}`: {classification} (confidence {confidence}) — {reason}".format(
                name=unit.get("name", ""),
                classification=unit.get("ai_classification", ""),
                confidence=unit.get("confidence", ""),
                reason=unit.get("reason", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _fallback_review(readiness_scan: dict[str, Any]) -> dict[str, Any]:
    units = []
    for unit in readiness_scan.get("units", []):
        units.append(
            {
                "name": unit.get("name", ""),
                "rule_based_classification": unit.get("classification", ""),
                "ai_classification": unit.get("classification", ""),
                "final_recommendation": unit.get("classification", ""),
                "reason": unit.get("reason", ""),
                "required_refactors": unit.get("suggested_refactors", []),
                "confidence": min(0.95, max(0.1, unit.get("dps_suitability_score", 0) / 100)),
            }
        )
    dps_units = [unit for unit in units if unit["final_recommendation"] in {"DPS-ready", "DPS-candidate-after-refactor"}]
    return {
        "status": "rule_based",
        "provider": "rule_based",
        "model": "",
        "recommended_dps_job": {
            "entrypoint": dps_units[0]["name"] if dps_units else "",
            "shape": "discover -> access -> process -> write_outputs",
            "requires_human_review": True,
        },
        "units": units,
    }


def _call_openai_review(
    *,
    readiness_scan: dict[str, Any],
    analysis: dict[str, Any],
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
                    "content": (
                        "You review notebook cells for MAAP DPS suitability. Return only JSON. "
                        "Use AST/rule facts as evidence and do not invent source behavior."
                    ),
                },
                {"role": "user", "content": _prompt(readiness_scan, analysis, mcp_defaults, dependency_graph)},
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
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return {"status": "completed", "model": model, "review": json.loads(content)}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI DPS-readiness review failed: {exc}"}


def _prompt(
    readiness_scan: dict[str, Any],
    analysis: dict[str, Any],
    mcp_defaults: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "task": "Review DPS-readiness classifications and propose a final DPS job shape.",
            "allowed_classifications": sorted(ALLOWED_CLASSIFICATIONS),
            "required_schema": {
                "recommended_dps_job": {
                    "entrypoint": "string",
                    "shape": "string",
                    "required_inputs": ["strings"],
                    "required_outputs": ["strings"],
                    "requires_human_review": "boolean",
                },
                "units": [
                    {
                        "name": "must match readiness_scan.units[].name",
                        "rule_based_classification": "string",
                        "ai_classification": "one allowed classification",
                        "final_recommendation": "string",
                        "reason": "string",
                        "required_refactors": ["strings"],
                        "confidence": "number 0..1",
                    }
                ],
            },
            "readiness_scan": readiness_scan,
            "static_analysis": analysis,
            "mcp_defaults": mcp_defaults,
            "dependency_graph": dependency_graph,
        },
        indent=2,
    )


def _resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    return "openai" if os.environ.get("OPENAI_API_KEY") else "none"
