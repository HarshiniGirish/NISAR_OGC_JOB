from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


CMR_GRANULE_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
CMR_COLLECTION_URL = "https://cmr.earthdata.nasa.gov/search/collections.umm_json"


def get_cmr_collection(short_name: str, *, live: bool = False) -> dict[str, Any]:
    """Return collection metadata from CMR when live lookup is enabled."""
    if not short_name:
        return {"status": "skipped", "reason": "short_name not provided"}
    if not live:
        return {"status": "not_requested", "short_name": short_name}

    payload = fetch_json(CMR_COLLECTION_URL, {"short_name": short_name, "page_size": "1"})
    items = payload.get("items", [])
    if not items:
        return {"status": "not_found", "short_name": short_name}

    item = items[0]
    umm = item.get("umm", {})
    return {
        "status": "found",
        "short_name": short_name,
        "concept_id": item.get("meta", {}).get("concept-id"),
        "provider": item.get("meta", {}).get("provider-id"),
        "title": umm.get("EntryTitle"),
        "version": umm.get("Version"),
    }


def get_cmr_granule(
    *,
    granule_ur: str = "",
    concept_id: str = "",
    short_name: str = "",
    live: bool = False,
    fixture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return normalized granule facts from a fixture or optional live CMR lookup."""
    if fixture:
        return normalize_granule_metadata(fixture)

    if not live:
        return {
            "status": "not_requested",
            "granule_ur": granule_ur,
            "concept_id": concept_id,
            "short_name": short_name,
        }

    params = {"page_size": "1"}
    if concept_id:
        params["concept_id"] = concept_id
    if granule_ur:
        params["granule_ur"] = granule_ur
    if short_name:
        params["short_name"] = short_name

    payload = fetch_json(CMR_GRANULE_URL, params)
    items = payload.get("items", [])
    if not items:
        return {"status": "not_found", "granule_ur": granule_ur, "concept_id": concept_id}
    return normalize_granule_metadata(items[0])


def normalize_granule_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Normalize CMR search page JSON or UMM-G item JSON into compact facts."""
    if "umm" in metadata:
        umm = metadata.get("umm", {})
        meta = metadata.get("meta", {})
        related_urls = umm.get("RelatedUrls", [])
        granule_ur = umm.get("GranuleUR")
        concept_id = meta.get("concept-id")
        provider = meta.get("provider-id")
    else:
        umm = metadata
        related_urls = metadata.get("relatedUrls") or metadata.get("RelatedUrls") or []
        granule_ur = metadata.get("granuleUr") or metadata.get("GranuleUR")
        concept_id = metadata.get("conceptId") or metadata.get("id")
        provider = metadata.get("dataCenter") or metadata.get("provider")

    urls = extract_related_urls(related_urls)
    formats = sorted(
        {
            str(item.get("format", "")).lower()
            for item in related_urls
            if item.get("format")
        }
    )
    size_mb = umm.get("granuleSize") or umm.get("GranuleSize")
    if not size_mb:
        size_mb = infer_size_mb_from_archive(umm)

    return {
        "status": "found",
        "granule_ur": granule_ur,
        "concept_id": concept_id,
        "provider": provider,
        "size_mb": size_mb,
        "formats": formats,
        "s3_urls": urls["s3_urls"],
        "https_urls": urls["https_urls"],
        "zarr_urls": urls["zarr_urls"],
        "metadata_urls": urls["metadata_urls"],
        "related_url_count": len(related_urls),
        "temporal_extent": umm.get("temporalExtent") or umm.get("TemporalExtent") or {},
        "spatial_extent": umm.get("spatialExtent") or umm.get("SpatialExtent") or {},
    }


def extract_related_urls(related_urls: list[dict[str, Any]]) -> dict[str, list[str]]:
    s3_urls: list[str] = []
    https_urls: list[str] = []
    zarr_urls: list[str] = []
    metadata_urls: list[str] = []

    for item in related_urls:
        url = item.get("url") or item.get("URL") or ""
        if not isinstance(url, str):
            continue
        lower_url = url.lower()
        if url.startswith("s3://"):
            s3_urls.append(url)
        elif url.startswith(("http://", "https://")):
            https_urls.append(url)
        if "zarr" in lower_url:
            zarr_urls.append(url)
        if any(marker in lower_url for marker in (".xml", ".json", ".md5", "metadata")):
            metadata_urls.append(url)

    return {
        "s3_urls": sorted(set(s3_urls)),
        "https_urls": sorted(set(https_urls)),
        "zarr_urls": sorted(set(zarr_urls)),
        "metadata_urls": sorted(set(metadata_urls)),
    }


def infer_size_mb_from_archive(umm: dict[str, Any]) -> float | None:
    archive_items = (
        umm.get("dataGranule", {}).get("archiveAndDistributionInformation")
        or umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation")
        or []
    )
    sizes = [
        item.get("sizeInBytes") or item.get("SizeInBytes")
        for item in archive_items
        if isinstance(item, dict)
    ]
    sizes = [size for size in sizes if isinstance(size, (int, float))]
    if not sizes:
        return None
    return round(max(sizes) / 1_000_000, 3)


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))
