from __future__ import annotations

from typing import Any


def check_access_options(
    *, urls: list[str] | None = None, collection: str = "", metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    metadata = metadata or {}
    urls = urls or []
    urls = list(urls) + metadata.get("s3_urls", []) + metadata.get("https_urls", []) + metadata.get("zarr_urls", [])
    lower_urls = [str(url).lower() for url in urls]

    direct_s3 = any(url.startswith("s3://") for url in lower_urls)
    https = any(url.startswith(("http://", "https://")) for url in lower_urls)
    zarr = any("zarr" in url for url in lower_urls)
    stac = any("/api/stac" in url for url in lower_urls)
    raster_api = any("/api/raster" in url or "tilejson" in url for url in lower_urls)
    geotiff = any(url.endswith((".tif", ".tiff")) for url in lower_urls)
    netcdf = any(url.endswith(".nc") for url in lower_urls)

    return {
        "direct_s3": direct_s3,
        "https": https,
        "stac": stac,
        "raster_api": raster_api,
        "zarr": zarr,
        "geotiff": geotiff,
        "netcdf": netcdf,
        "harmony": infer_harmony_support(collection),
        "virtual_access": zarr or any(url.endswith(".json.gz") for url in lower_urls),
        "preferred_order": preferred_order(
            direct_s3=direct_s3,
            zarr=zarr,
            geotiff=geotiff,
            https=https,
            raster_api=raster_api,
        ),
    }


def infer_harmony_support(collection: str) -> bool:
    harmony_signals = ("SPL", "MODIS", "ATL", "GEDI")
    return collection.startswith(harmony_signals)


def preferred_order(*, direct_s3: bool, zarr: bool, geotiff: bool, https: bool, raster_api: bool) -> list[str]:
    order: list[str] = []
    if raster_api:
        order.append("stac_raster_api")
    if zarr:
        order.append("zarr_open_zarr")
    if direct_s3 and geotiff:
        order.append("direct_s3_rasterio")
    if direct_s3:
        order.append("direct_s3_xarray")
    if https:
        order.append("https_streaming")
    order.append("https_download_fallback")
    return order
