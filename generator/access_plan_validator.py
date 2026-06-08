from __future__ import annotations

from typing import Any

try:
    from .access_strategies import ALLOWED_STRATEGIES
except ImportError:
    from access_strategies import ALLOWED_STRATEGIES


def validate_access_plan(plan: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    strategy = str(plan.get("chosen_strategy", ""))
    errors: list[str] = []
    warnings: list[str] = []

    if strategy not in ALLOWED_STRATEGIES:
        errors.append(f"Unsupported strategy: {strategy or '<missing>'}")
    else:
        strategy_config = ALLOWED_STRATEGIES[strategy]
        valid_formats = set(strategy_config.get("valid_formats", []))
        evidence_formats = set(evidence.get("file_formats", []))
        if evidence_formats and valid_formats and not evidence_formats.intersection(valid_formats):
            warnings.append(
                "Chosen strategy does not directly match detected file formats: "
                + ", ".join(sorted(evidence_formats))
            )

    required_dependencies = plan.get("required_dependencies", [])
    if not isinstance(required_dependencies, list):
        errors.append("required_dependencies must be a list")

    for key in ("warnings", "implementation_hints"):
        if key in plan and not isinstance(plan[key], list):
            errors.append(f"{key} must be a list")

    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
    }
