#!/usr/bin/env python3
"""Generate VEDA Black Marble Nightlights TileJSON and manifest outputs."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests
from pystac_client import Client

APP_NAME = "black_marble_veda"
APP_VERSION = "main"
APP_TARGET = "both"
APP_DESCRIPTION = "Request NASA VEDA Black Marble Nightlights TileJSON for a date and collection."
APP_BASE_CONTAINER = "mas.maap-project.org/root/maap-workspaces/base_images/pangeo:v4.1.1"
APP_RAM_MIN = 4
APP_CORES_MIN = 1
APP_OUTDIR_MAX = 5

DEFAULT_STAC_API_URL = "https://openveda.cloud/api/stac"
DEFAULT_RASTER_API_URL = "https://openveda.cloud/api/raster"
DEFAULT_COLLECTION_ID = "lakeview-nightlights-tornadoes-2024"
DEFAULT_DATE = "2024-03-14"
DEFAULT_CENTER = "40.496,-83.884"
DEFAULT_ZOOM = 12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch VEDA Black Marble Nightlights TileJSON and write a manifest."
    )
    parser.add_argument("--stac-api-url", default=DEFAULT_STAC_API_URL)
    parser.add_argument("--raster-api-url", default=DEFAULT_RASTER_API_URL)
    parser.add_argument("--collection-id", default=DEFAULT_COLLECTION_ID)
    parser.add_argument("--date", default=DEFAULT_DATE, help="Date or datetime used for STAC search.")
    parser.add_argument("--assets", default="", help="Optional render asset name; inferred from collection render metadata when omitted.")
    parser.add_argument("--rescale", default="", help="Optional raster API rescale value such as '0,60'.")
    parser.add_argument("--colormap-name", default="", help="Optional raster API colormap name.")
    parser.add_argument("--center", default=DEFAULT_CENTER, help="Map center as 'lat,lon' for downstream visualization metadata.")
    parser.add_argument("--zoom", type=int, default=DEFAULT_ZOOM)
    parser.add_argument("--dest", default=os.environ.get("USER_OUTPUT_DIR", "output"))
    parser.add_argument("--out-name", default="black_marble_tilejson.json")
    return parser.parse_args()


def normalize_datetime(value: str) -> str:
    if "T" in value:
        return value
    return f"{value}T00:00:00Z"


def parse_center(value: str) -> list[float]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError("--center must be 'lat,lon'")
    return [float(parts[0]), float(parts[1])]


def first_dashboard_render(collection) -> dict[str, Any]:
    renders = collection.extra_fields.get("renders", {})
    dashboard = renders.get("dashboard", {})
    return dashboard if isinstance(dashboard, dict) else {}


def infer_render_options(collection, item, args: argparse.Namespace) -> dict[str, str]:
    dashboard = first_dashboard_render(collection)
    assets = args.assets
    if not assets:
        render_assets = dashboard.get("assets") or []
        if render_assets:
            assets = str(render_assets[0])
        elif item.assets:
            assets = next(iter(item.assets))
        else:
            raise RuntimeError("No render assets found in STAC item or collection.")

    rescale = args.rescale
    if not rescale:
        rescale_values = dashboard.get("rescale") or []
        if rescale_values:
            first = rescale_values[0]
            if isinstance(first, (list, tuple)) and len(first) == 2:
                rescale = f"{first[0]},{first[1]}"

    return {
        "assets": assets,
        "rescale": rescale,
        "colormap_name": args.colormap_name,
    }


def fetch_black_marble_tilejson(args: argparse.Namespace) -> dict[str, Any]:
    client = Client.open(args.stac_api_url)
    results = client.search(
        collections=[args.collection_id],
        datetime=normalize_datetime(args.date),
    )
    items = list(results.items())
    if not items:
        raise RuntimeError(f"No STAC items found for {args.collection_id} at {args.date}")

    item = items[0]
    collection = item.get_collection()
    render_options = infer_render_options(collection, item, args)

    params = {"assets": render_options["assets"]}
    if render_options["rescale"]:
        params["rescale"] = render_options["rescale"]
    if render_options["colormap_name"]:
        params["colormap_name"] = render_options["colormap_name"]

    tilejson_url = (
        f"{args.raster_api_url.rstrip('/')}/collections/{args.collection_id}"
        f"/items/{item.id}/WebMercatorQuad/tilejson.json"
    )
    response = requests.get(tilejson_url, params=params, timeout=60)
    response.raise_for_status()

    tilejson = response.json()
    tilejson["_metadata"] = {
        "collection_id": args.collection_id,
        "item_id": item.id,
        "date": args.date,
        "assets": render_options["assets"],
        "rescale": render_options["rescale"],
        "colormap_name": render_options["colormap_name"],
        "center": parse_center(args.center),
        "zoom": args.zoom,
        "tilejson_url": response.url,
        "stac_api_url": args.stac_api_url,
        "raster_api_url": args.raster_api_url,
    }
    return tilejson


def main() -> None:
    args = parse_args()
    os.makedirs(args.dest, exist_ok=True)

    tilejson = fetch_black_marble_tilejson(args)
    tilejson_path = os.path.abspath(os.path.join(args.dest, args.out_name))
    manifest_path = os.path.abspath(os.path.join(args.dest, "manifest.json"))

    with open(tilejson_path, "w", encoding="utf-8") as file_obj:
        json.dump(tilejson, file_obj, indent=2)

    manifest = {
        "status": "OK",
        "tilejson": tilejson_path,
        "collection_id": args.collection_id,
        "date": args.date,
        "item_id": tilejson.get("_metadata", {}).get("item_id"),
        "assets": tilejson.get("_metadata", {}).get("assets"),
        "tiles": tilejson.get("tiles", []),
    }
    with open(manifest_path, "w", encoding="utf-8") as file_obj:
        json.dump(manifest, file_obj, indent=2)

    print("WROTE_TILEJSON:", tilejson_path)
    print("WROTE_MANIFEST:", manifest_path)
    print("OUTPUT_DIR:", os.path.abspath(args.dest))


if __name__ == "__main__":
    main()
