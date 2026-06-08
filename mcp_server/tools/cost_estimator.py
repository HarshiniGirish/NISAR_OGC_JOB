from __future__ import annotations

import re
from functools import reduce
from operator import mul
from typing import Any


def estimate_subset_cost(
    *,
    dimensions: dict[str, int] | None = None,
    subset: dict[str, Any] | None = None,
    variables: list[str] | None = None,
) -> dict[str, Any]:
    dimensions = dimensions or {}
    subset = subset or {}
    variables = variables or []
    full_cells = product(dimensions.values()) if dimensions else 0
    subset_cells = infer_subset_cells(dimensions, subset) or full_cells
    variable_count = max(len(variables), 1)
    estimated_cells = subset_cells * variable_count
    ratio = (subset_cells / full_cells) if full_cells else None

    if ratio is None:
        risk = "unknown"
    elif ratio <= 0.05:
        risk = "low"
    elif ratio <= 0.25:
        risk = "medium"
    else:
        risk = "high"

    warning = None
    if risk == "high":
        warning = "Requested subset is large relative to full dataset; avoid full download/write."
    elif risk == "unknown":
        warning = "Dataset dimensions were unavailable, so subset cost could not be estimated."

    return {
        "dimensions": dimensions,
        "subset": subset,
        "variables": variables,
        "full_cells": full_cells,
        "estimated_cells": estimated_cells,
        "subset_ratio": ratio,
        "risk": risk,
        "warning": warning,
    }


def infer_subset_cells(dimensions: dict[str, int], subset: dict[str, Any]) -> int:
    idx_window = str(subset.get("idx_window") or "")
    if idx_window:
        sizes = parse_idx_window(idx_window)
        if sizes:
            return product(sizes)

    bbox = str(subset.get("bbox") or "")
    if bbox and dimensions:
        # Without geotransform, use conservative 10% estimate for bbox subsetting.
        return max(1, int(product(dimensions.values()) * 0.10))

    return 0


def parse_idx_window(value: str) -> list[int]:
    matches = re.findall(r"(\d*)\s*:\s*(\d*)", value)
    sizes: list[int] = []
    for start_text, stop_text in matches:
        if not stop_text:
            continue
        start = int(start_text) if start_text else 0
        stop = int(stop_text)
        if stop > start:
            sizes.append(stop - start)
    return sizes


def product(values) -> int:
    values = [int(value) for value in values if value]
    if not values:
        return 0
    return reduce(mul, values, 1)
