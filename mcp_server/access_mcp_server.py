from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

try:
    from .tools.access_options import check_access_options
    from .tools.asset_inspection import inspect_asset
    from .tools.cmr import get_cmr_collection, get_cmr_granule
    from .tools.cost_estimator import estimate_subset_cost
    from .tools.recommendation import build_dataset_facts, recommend_access_pattern
except ImportError:
    from tools.access_options import check_access_options
    from tools.asset_inspection import inspect_asset
    from tools.cmr import get_cmr_collection, get_cmr_granule
    from tools.cost_estimator import estimate_subset_cost
    from tools.recommendation import build_dataset_facts, recommend_access_pattern


TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "get_cmr_collection": get_cmr_collection,
    "get_cmr_granule": get_cmr_granule,
    "inspect_asset": inspect_asset,
    "check_access_options": check_access_options,
    "estimate_subset_cost": estimate_subset_cost,
    "build_dataset_facts": build_dataset_facts,
}


def call_tool(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "recommend_access_pattern":
        return recommend_access_pattern(
            payload.get("evidence", {}),
            payload.get("asset", {}),
            payload.get("access_options", {}),
            payload.get("subset_cost", {}),
        )

    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return {"status": "error", "message": f"Unknown tool: {name}"}
    return tool(**payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Call MCP-ready access metadata tools with JSON input.")
    parser.add_argument("tool", choices=sorted([*TOOL_REGISTRY, "recommend_access_pattern"]))
    parser.add_argument("--payload", default="-", help="JSON payload or '-' to read stdin.")
    args = parser.parse_args()

    payload_text = sys.stdin.read() if args.payload == "-" else args.payload
    payload = json.loads(payload_text or "{}")
    print(json.dumps(call_tool(args.tool, payload), indent=2))


if __name__ == "__main__":
    main()
