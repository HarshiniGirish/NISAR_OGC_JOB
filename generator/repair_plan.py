from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def build_repair_plan(
    *,
    readiness_scan: dict[str, Any],
    analysis: dict[str, Any],
    validation_report: dict[str, Any],
    dependency_graph: dict[str, Any],
    access_plan: dict[str, Any],
    mcp_defaults: dict[str, Any],
    enabled: bool = False,
    provider: str = "auto",
    model: str = "",
) -> dict[str, Any]:
    fallback = rule_based_repair_plan(
        readiness_scan=readiness_scan,
        analysis=analysis,
        validation_report=validation_report,
        dependency_graph=dependency_graph,
        access_plan=access_plan,
        mcp_defaults=mcp_defaults,
    )
    if not enabled:
        fallback["status"] = "rule_based"
        fallback["message"] = "LLM repair plan was not requested."
        return fallback

    if _resolve_provider(provider) != "openai":
        fallback["status"] = "fallback"
        fallback["message"] = "OpenAI repair plan unavailable; using rule-based repair plan."
        return fallback

    result = _call_openai_repair_plan(
        readiness_scan=readiness_scan,
        analysis=analysis,
        validation_report=validation_report,
        dependency_graph=dependency_graph,
        access_plan=access_plan,
        mcp_defaults=mcp_defaults,
        model=model or "gpt-4o-mini",
    )
    if result.get("status") != "completed":
        fallback["status"] = "fallback"
        fallback["message"] = result.get("message", "OpenAI repair plan failed.")
        return fallback
    validation = validate_repair_plan(result.get("plan", {}))
    if not validation["valid"]:
        fallback["status"] = "fallback"
        fallback["message"] = "OpenAI repair plan failed schema validation: " + "; ".join(validation["errors"])
        return fallback
    plan = result["plan"]
    plan.update({"status": "completed", "provider": "openai", "model": result.get("model", model), "validation": validation})
    return plan


def rule_based_repair_plan(
    *,
    readiness_scan: dict[str, Any],
    analysis: dict[str, Any],
    validation_report: dict[str, Any],
    dependency_graph: dict[str, Any],
    access_plan: dict[str, Any],
    mcp_defaults: dict[str, Any],
) -> dict[str, Any]:
    safe_autofixes = []
    requires_user_review = []
    science_review_required = []
    blocking_fixes = []
    runtime_risks = []

    for issue in analysis.get("issues", []):
        rule = issue.get("rule")
        location = issue.get("location", "")
        if rule == "notebook_magic":
            blocking_fixes.append(
                {
                    "location": location,
                    "problem": issue.get("message", ""),
                    "recommended_fix": "Move shell setup into env.yml, Dockerfile, build.sh, or plain Python.",
                    "autofix_safe": False,
                }
            )
        elif rule == "hardcoded_local_path":
            safe_autofixes.append(
                {
                    "location": location,
                    "problem": issue.get("message", ""),
                    "fix": "Parameterize the path and route outputs under output_dir when possible.",
                    "autofix_safe": True,
                }
            )
        elif rule == "implicit_notebook_state":
            requires_user_review.append(
                {
                    "location": location,
                    "problem": issue.get("message", ""),
                    "fix": "Keep cell order explicit or refactor shared variables into functions.",
                }
            )

    for unit in readiness_scan.get("units", []):
        for refactor in unit.get("suggested_refactors", []):
            safe = "output_dir" in refactor or "local path" in refactor
            target = safe_autofixes if safe else requires_user_review
            target.append(
                {
                    "location": unit.get("name", ""),
                    "problem": refactor,
                    "fix": refactor,
                    "autofix_safe": safe,
                }
            )
        if unit.get("classification") == "Notebook-only" and unit.get("dependencies"):
            science_review_required.append(
                {
                    "location": unit.get("name", ""),
                    "reason": "Visualization or exploration cell should stay optional unless science owner wants it as an output.",
                }
            )

    if "direct_s3" in str(access_plan.get("chosen_strategy", "")) or "s3" in str(access_plan):
        runtime_risks.append(
            {
                "risk": "S3 credentials may fail, expire, or be unavailable in a target environment.",
                "mitigation": "Generate S3-to-HTTPS fallback logic or use staged inputs.",
            }
        )
    if validation_report.get("warnings"):
        for warning in validation_report["warnings"]:
            runtime_risks.append({"risk": warning, "mitigation": "Review before registration or production run."})

    return {
        "can_become_dps_job": not validation_report.get("blocking_issues", []),
        "overall_recommendation": _overall_recommendation(validation_report, blocking_fixes, requires_user_review),
        "recommended_entrypoint": "generated package entrypoint script",
        "blocking_fixes": _dedupe_dicts(blocking_fixes),
        "safe_autofixes": _dedupe_dicts(safe_autofixes + _generic_safe_autofixes()),
        "requires_user_review": _dedupe_dicts(requires_user_review),
        "science_review_required": _dedupe_dicts(science_review_required),
        "runtime_risks": _dedupe_dicts(runtime_risks),
        "confidence_score": _confidence(validation_report, dependency_graph),
    }


def validate_repair_plan(plan: dict[str, Any]) -> dict[str, Any]:
    errors = []
    required = {
        "can_become_dps_job": bool,
        "overall_recommendation": str,
        "recommended_entrypoint": str,
        "blocking_fixes": list,
        "safe_autofixes": list,
        "requires_user_review": list,
        "science_review_required": list,
        "runtime_risks": list,
        "confidence_score": (int, float),
    }
    if not isinstance(plan, dict):
        return {"valid": False, "errors": ["Repair plan must be an object."]}
    for key, expected in required.items():
        if key not in plan:
            errors.append(f"Missing key: {key}")
        elif not isinstance(plan[key], expected):
            errors.append(f"Wrong type for {key}")
    return {"valid": not errors, "errors": errors}


def write_repair_plan(plan: dict[str, Any], output_dir: str | Path) -> list[str]:
    path = Path(output_dir)
    json_path = path / "llm_repair_plan.json"
    md_path = path / "llm_repair_plan.md"
    safe_json = path / "safe_autofix_report.json"
    safe_md = path / "safe_autofix_report.md"
    json_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_repair_plan_markdown(plan), encoding="utf-8")
    safe_report = build_safe_autofix_report(plan)
    safe_json.write_text(json.dumps(safe_report, indent=2) + "\n", encoding="utf-8")
    safe_md.write_text(render_safe_autofix_markdown(safe_report), encoding="utf-8")
    return [json_path.name, md_path.name, safe_json.name, safe_md.name]


def build_safe_autofix_report(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "plan_only",
        "message": "Safe fixes are reported for review; original notebooks are not overwritten.",
        "safe_autofixes": plan.get("safe_autofixes", []),
        "requires_user_review": plan.get("requires_user_review", []),
        "science_review_required": plan.get("science_review_required", []),
    }


def render_repair_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# LLM / Rule-Based Repair Plan",
        "",
        f"- Can become DPS job: `{plan.get('can_become_dps_job')}`",
        f"- Recommendation: {plan.get('overall_recommendation', '')}",
        f"- Recommended entrypoint: `{plan.get('recommended_entrypoint', '')}`",
        f"- Confidence: `{plan.get('confidence_score', '')}`",
        "",
    ]
    _section(lines, "Blocking fixes", plan.get("blocking_fixes", []))
    _section(lines, "Safe autofixes", plan.get("safe_autofixes", []))
    _section(lines, "Requires user review", plan.get("requires_user_review", []))
    _section(lines, "Science review required", plan.get("science_review_required", []))
    _section(lines, "Runtime risks", plan.get("runtime_risks", []))
    return "\n".join(lines) + "\n"


def render_safe_autofix_markdown(report: dict[str, Any]) -> str:
    lines = ["# Safe Autofix Report", "", report.get("message", ""), ""]
    _section(lines, "Safe autofixes", report.get("safe_autofixes", []))
    _section(lines, "Requires user review", report.get("requires_user_review", []))
    _section(lines, "Science review required", report.get("science_review_required", []))
    return "\n".join(lines) + "\n"


def _section(lines: list[str], title: str, items: list[dict[str, Any]]) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        text = item.get("problem") or item.get("fix") or item.get("risk") or item.get("reason") or str(item)
        location = item.get("location")
        if location:
            lines.append(f"- `{location}`: {text}")
        else:
            lines.append(f"- {text}")
        if item.get("fix") or item.get("recommended_fix") or item.get("mitigation"):
            lines.append(f"  - Action: {item.get('fix') or item.get('recommended_fix') or item.get('mitigation')}")
    lines.append("")


def _call_openai_repair_plan(**kwargs: Any) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "message": "OPENAI_API_KEY is not set."}
    model = kwargs.pop("model")
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only JSON matching the repair-plan schema. Do not overwrite code.",
                },
                {"role": "user", "content": _repair_prompt(kwargs)},
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
        return {"status": "completed", "model": model, "plan": json.loads(content)}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI repair plan failed: {exc}"}


def _repair_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Create an actionable DPS conversion repair plan from these reports.",
            "required_schema": {
                "can_become_dps_job": "boolean",
                "overall_recommendation": "string",
                "recommended_entrypoint": "string",
                "blocking_fixes": ["objects"],
                "safe_autofixes": ["objects"],
                "requires_user_review": ["objects"],
                "science_review_required": ["objects"],
                "runtime_risks": ["objects"],
                "confidence_score": "0..1",
            },
            "safety": "Only propose. Do not rewrite source. Mark science-sensitive changes as review required.",
            **payload,
        },
        indent=2,
    )


def _resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    return "openai" if os.environ.get("OPENAI_API_KEY") else "none"


def _generic_safe_autofixes() -> list[dict[str, Any]]:
    return [
        {
            "problem": "MAAP API method names may vary across maap-py versions.",
            "fix": "Use compatibility wrappers for searchGranule/search_granule and searchCollection/search_collection.",
            "autofix_safe": True,
        },
        {
            "problem": "Direct data downloads may fail with 401/403/503.",
            "fix": "Use safe_get_data() to write an access-failure manifest and continue report generation.",
            "autofix_safe": True,
        },
        {
            "problem": "Output directory may be missing.",
            "fix": "Create output_dir before writing outputs.",
            "autofix_safe": True,
        },
    ]


def _overall_recommendation(
    validation_report: dict[str, Any], blocking_fixes: list[dict[str, Any]], reviews: list[dict[str, Any]]
) -> str:
    if validation_report.get("blocking_issues") or blocking_fixes:
        return "Yes, after blocking issues are fixed."
    if reviews:
        return "Yes, after user/science review of refactor items."
    return "Yes, structurally ready; run smoke tests and review science outputs."


def _confidence(validation_report: dict[str, Any], dependency_graph: dict[str, Any]) -> float:
    score = 0.75
    if validation_report.get("ogc_ready"):
        score += 0.1
    if validation_report.get("maap_dps_ready"):
        score += 0.1
    score -= min(0.25, 0.05 * len(validation_report.get("blocking_issues", [])))
    score -= min(0.15, 0.03 * dependency_graph.get("summary", {}).get("unresolved_count", 0))
    return round(max(0.0, min(1.0, score)), 2)


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped
