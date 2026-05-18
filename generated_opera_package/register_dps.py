#!/usr/bin/env python3
"""Register the generated DPS algorithm with a configured MAAP API endpoint.

Environment variables:
- MAAP_API_URL: base URL for the MAAP API.
- MAAP_API_TOKEN or MAAP_TOKEN: bearer token for registration.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml


def main() -> None:
    package_dir = Path(__file__).resolve().parent
    config = yaml.safe_load((package_dir / "algorithm_config.yaml").read_text(encoding="utf-8"))
    api_url = os.environ.get("MAAP_API_URL", "").rstrip("/")
    token = os.environ.get("MAAP_API_TOKEN") or os.environ.get("MAAP_TOKEN")
    if not api_url or not token:
        raise SystemExit("Set MAAP_API_URL and MAAP_API_TOKEN before DPS registration.")

    payload = json.dumps(config).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url}/api/algorithms",
        data=payload,
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        sys.stdout.write(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
