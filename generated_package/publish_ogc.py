#!/usr/bin/env python3
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
