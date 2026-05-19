#!/usr/bin/env python3
"""OPERA DISP: extract water_mask, optionally subset it, and write a COG."""

from __future__ import annotations

import argparse
import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Optional, Tuple

import numpy as np
import pyproj
import requests
import rioxarray  # registers .rio
import xarray as xr
from maap.maap import MAAP
from s3fs import S3FileSystem
from shapely.geometry import box
from shapely.ops import transform as shp_transform

DEFAULT_TEMPORAL = "2025-10-01T13:42:14Z,2025-10-13T13:42:14Z"
DEFAULT_GRANULE_UR = (
    "OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_"
    "20251013T134214Z_v1.0_20260310T213850Z"
)
DEFAULT_S3_URL = (
    "s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/"
    "OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_"
    "20251013T134214Z_v1.0_20260310T213850Z/"
    "OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_"
    "20251013T134214Z_v1.0_20260310T213850Z.nc"
)
ASF_S3_CREDENTIALS_URL = "https://cumulus.asf.alaska.edu/s3credentials"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OPERA DISP: export water_mask to COG with optional bbox/index subsetting."
    )
    parser.add_argument("--short-name", default="OPERA_L3_DISP-S1_V1", help="CMR short name")
    parser.add_argument(
        "--temporal",
        default=DEFAULT_TEMPORAL,
        help="Temporal range 'YYYY-MM-DDTHH:MM:SSZ,YYYY-MM-DDTHH:MM:SSZ'",
    )
    parser.add_argument("--bbox", default=None, help="WGS84 bbox 'minx,miny,maxx,maxy'")
    parser.add_argument("--limit", type=int, default=10, help="Max granules to search")
    parser.add_argument("--granule-ur", default=DEFAULT_GRANULE_UR, help="Optional fixed GranuleUR")
    parser.add_argument("--tile", type=int, default=256, help="COG tile size")
    parser.add_argument("--compress", default="DEFLATE", help="COG compression")
    parser.add_argument(
        "--overview-resampling",
        default="nearest",
        help="COG overview resampling; nearest is recommended for masks",
    )
    parser.add_argument("--out-name", default="water_mask_subset.cog.tif", help="Output filename")
    parser.add_argument(
        "--dest",
        default=None,
        help="Relative output directory. The generated run.sh supplies this automatically.",
    )
    parser.add_argument(
        "--idx-window",
        default="0:1024,0:1024",
        help="Index window 'y0:y1,x0:x1'. Defaults to a small smoke-test subset.",
    )
    parser.add_argument("--s3-url", default=DEFAULT_S3_URL, help="Direct s3:// path to a .nc granule")
    args, _ = parser.parse_known_args()

    for attr in ("temporal", "bbox", "granule_ur", "s3_url", "dest"):
        value = getattr(args, attr)
        if value:
            setattr(args, attr, value.strip())

    return args


def parse_bbox(bbox_str: str) -> Tuple[float, float, float, float]:
    values = [float(value) for value in bbox_str.split(",")]
    if len(values) != 4:
        raise ValueError("bbox must be 'minx,miny,maxx,maxy'")
    minx, miny, maxx, maxy = values
    if minx >= maxx or miny >= maxy:
        raise ValueError("bbox min values must be < max values")
    return minx, miny, maxx, maxy


def ensure_wgs84_bbox_to_target(bbox_value, target_crs: Any):
    if not target_crs:
        return bbox_value
    transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs, always_xy=True).transform
    minx, miny, maxx, maxy = bbox_value
    return shp_transform(transformer, box(minx, miny, maxx, maxy)).bounds


def _extract_s3_url_from_result(result) -> Optional[str]:
    if isinstance(result, dict):
        try:
            urls = result["Granule"]["OnlineAccessURLs"]["OnlineAccessURL"]
            if isinstance(urls, list):
                for url_item in urls:
                    url = url_item.get("URL") if isinstance(url_item, dict) else url_item
                    if isinstance(url, str) and url.startswith("s3://"):
                        return url
            elif isinstance(urls, dict):
                url = urls.get("URL")
                if isinstance(url, str) and url.startswith("s3://"):
                    return url
        except Exception:
            pass

    if hasattr(result, "getDownloadUrl"):
        try:
            url = result.getDownloadUrl()
            if isinstance(url, str) and url.startswith("s3://"):
                return url
        except Exception:
            pass

    return None


def _first_s3_from_umm(umm_item) -> Optional[str]:
    try:
        for url_item in umm_item["umm"].get("RelatedUrls", []):
            url = url_item.get("URL")
            if isinstance(url, str) and url.startswith("s3://"):
                return url
    except Exception:
        pass

    try:
        urls = umm_item["umm"]["OnlineAccessURLs"]["OnlineAccessURL"]
        if isinstance(urls, list):
            for url_item in urls:
                url = url_item.get("URL") if isinstance(url_item, dict) else url_item
                if isinstance(url, str) and url.startswith("s3://"):
                    return url
        elif isinstance(urls, dict):
            url = urls.get("URL")
            if isinstance(url, str) and url.startswith("s3://"):
                return url
    except Exception:
        pass

    return None


def maap_search_collection(maap: MAAP, **kwargs):
    if hasattr(maap, "search_collection"):
        return maap.search_collection(**kwargs)
    return maap.searchCollection(**kwargs)


def maap_search_granule(maap: MAAP, **kwargs):
    if hasattr(maap, "search_granule"):
        return maap.search_granule(**kwargs)
    return maap.searchGranule(**kwargs)


def get_earthdata_s3_credentials(maap: MAAP, credentials_url: str = ASF_S3_CREDENTIALS_URL) -> dict:
    if hasattr(maap, "aws") and hasattr(maap.aws, "earthdata_s3_credentials"):
        return maap.aws.earthdata_s3_credentials(credentials_url)
    raise RuntimeError(
        "This MAAP client does not expose aws.earthdata_s3_credentials. "
        "Run inside MAAP ADE or provide an environment with temporary AWS credentials."
    )


def pick_granule_url(maap: MAAP, short_name, temporal, bbox_value, limit, fixed_ur=None):
    collection = maap_search_collection(
        maap, cmr_host="cmr.earthdata.nasa.gov", short_name=short_name
    )
    if not collection:
        raise RuntimeError(f"No collection found for {short_name}")
    concept_id = collection[0].get("concept-id")

    query = {"cmr_host": "cmr.earthdata.nasa.gov", "collection_concept_id": concept_id}
    if temporal:
        query["temporal"] = temporal
    if bbox_value:
        query["bounding_box"] = bbox_value

    try:
        results = maap_search_granule(maap, limit=limit, **query)
    except ET.ParseError as exc:
        params = {
            "collection_concept_id": concept_id,
            "page_size": str(limit or 10),
        }
        if temporal:
            params["temporal"] = temporal
        if bbox_value:
            params["bounding_box"] = bbox_value
        if fixed_ur:
            params["granule_ur"] = fixed_ur

        response = requests.get(
            "https://cmr.earthdata.nasa.gov/search/granules.umm_json",
            params=params,
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"CMR UMM-JSON request failed: status={response.status_code} url={response.url}"
            ) from exc
        items = response.json().get("items", [])
        if not items:
            raise RuntimeError("No granules found in UMM-JSON fallback.")
        if fixed_ur:
            items = [item for item in items if item.get("umm", {}).get("GranuleUR") == fixed_ur]
            if not items:
                raise RuntimeError(f"GranuleUR '{fixed_ur}' not found in UMM-JSON results.")
        s3_url = _first_s3_from_umm(items[0])
        if not s3_url:
            raise RuntimeError("Could not find s3:// URL in UMM-JSON item.")
        creds = get_earthdata_s3_credentials(maap)
        return s3_url, {"granule": items[0], "aws_creds": creds}

    if not results:
        raise RuntimeError("No granules found.")

    def _granule_ur(result):
        if isinstance(result, dict):
            return result.get("Granule", {}).get("GranuleUR")
        return getattr(result, "GranuleUR", None)

    if fixed_ur:
        picked = next((result for result in results if _granule_ur(result) == fixed_ur), None)
        if picked is None:
            raise RuntimeError(f"GranuleUR '{fixed_ur}' not found in SDK results.")
    else:
        picked = results[0]

    s3_url = _extract_s3_url_from_result(picked)
    if not (isinstance(s3_url, str) and s3_url.startswith("s3://")) and hasattr(
        picked, "getDownloadUrl"
    ):
        try:
            candidate = picked.getDownloadUrl()
            if isinstance(candidate, str) and candidate.startswith("s3://"):
                s3_url = candidate
        except Exception:
            pass

    if not (isinstance(s3_url, str) and s3_url.startswith("s3://")):
        params = {
            "collection_concept_id": concept_id,
            "page_size": str(limit or 10),
        }
        if temporal:
            params["temporal"] = temporal
        if bbox_value:
            params["bounding_box"] = bbox_value
        response = requests.get(
            "https://cmr.earthdata.nasa.gov/search/granules.xml",
            params=params,
            timeout=60,
        )
        raise RuntimeError(
            "Could not resolve s3:// URL from granule metadata.\n"
            f"SDK results XML head ({len(response.text[:1000])} chars):\n{response.text[:1000]}"
        )

    creds = get_earthdata_s3_credentials(maap)
    return s3_url, {"granule": picked, "aws_creds": creds}


def open_remote_dataset(granule_url: str, aws_creds: dict) -> xr.Dataset:
    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

    s3 = S3FileSystem(
        key=aws_creds["accessKeyId"],
        secret=aws_creds["secretAccessKey"],
        token=aws_creds["sessionToken"],
        client_kwargs={"region_name": "us-west-2"},
    )
    _ = s3.info(granule_url)

    io_params = dict(decode_cf=True, mask_and_scale=True, cache=False)
    for engine in ["h5netcdf", "netcdf4", "scipy"]:
        try:
            file_obj = s3.open(granule_url, "rb")
            ds = xr.open_dataset(file_obj, engine=engine, chunks="auto", **io_params)
            _ = list(ds.sizes.items())[:1]
            return ds
        except Exception:
            continue

    raise RuntimeError(f"Failed to open {granule_url} with h5netcdf/netcdf4/scipy")


def get_water_mask(ds: xr.Dataset) -> xr.DataArray:
    if "water_mask" not in ds:
        raise RuntimeError("Dataset has no 'water_mask' variable.")
    data_array = ds["water_mask"]
    if "time" in data_array.dims and data_array.sizes.get("time", 1) > 1:
        data_array = data_array.isel(time=0)
    if "band" in data_array.dims and data_array.sizes.get("band", 1) == 1:
        data_array = data_array.isel(band=0, drop=True)
    return data_array > 0


def subset_bbox(data_array: xr.DataArray, bbox_value) -> xr.DataArray:
    if data_array.rio.crs is None:
        data_array = data_array.rio.write_crs("EPSG:4326")
    target_bbox = ensure_wgs84_bbox_to_target(bbox_value, data_array.rio.crs)
    return data_array.rio.clip_box(*target_bbox)


def subset_idx(data_array: xr.DataArray, idx_spec: str) -> xr.DataArray:
    y_spec, x_spec = idx_spec.split(",")
    y0, y1 = [int(value) if value else None for value in y_spec.split(":")]
    x0, x1 = [int(value) if value else None for value in x_spec.split(":")]
    return data_array.isel(y=slice(y0, y1), x=slice(x0, x1))


def write_cog(
    data_array: xr.DataArray,
    out_path: str,
    nodata_val=255,
    tile=256,
    compress="DEFLATE",
    overview_resampling="nearest",
):
    data_array = data_array.astype("uint8").rio.write_nodata(nodata_val, inplace=False)
    data_array.rio.to_raster(
        out_path,
        driver="COG",
        dtype="uint8",
        nodata=nodata_val,
        blockxsize=tile,
        blockysize=tile,
        compress=compress,
        overview_resampling=overview_resampling,
        BIGTIFF="IF_NEEDED",
    )
    return out_path


def main() -> None:
    args = parse_args()
    print(
        json.dumps(
            {
                "args": {
                    "short_name": args.short_name,
                    "temporal": args.temporal,
                    "bbox": args.bbox,
                    "limit": args.limit,
                    "granule_ur": args.granule_ur,
                    "s3_url": args.s3_url,
                }
            }
        )
    )

    out_dir = args.dest or os.environ.get("USER_OUTPUT_DIR", "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.out_name)

    maap = MAAP()
    if args.s3_url:
        url = args.s3_url
        meta = {
            "granule": None,
            "aws_creds": get_earthdata_s3_credentials(maap),
        }
    else:
        url, meta = pick_granule_url(
            maap,
            args.short_name,
            args.temporal,
            args.bbox,
            args.limit,
            args.granule_ur,
        )

    ds = open_remote_dataset(url, meta["aws_creds"])
    try:
        water_mask = get_water_mask(ds)
        if args.idx_window:
            water_mask = subset_idx(water_mask, args.idx_window)
        elif args.bbox:
            water_mask = subset_bbox(water_mask, parse_bbox(args.bbox))

        out = write_cog(
            water_mask,
            out_path,
            tile=args.tile,
            compress=args.compress,
            overview_resampling=args.overview_resampling,
        )
        print(f"Saved COG to {out}")

        if os.path.exists(out):
            print(
                json.dumps(
                    {
                        "status": "OK",
                        "outfile": out,
                        "size_mb": round(os.path.getsize(out) / 1e6, 2),
                    }
                )
            )
        else:
            raise SystemExit(1)
    finally:
        try:
            ds.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
