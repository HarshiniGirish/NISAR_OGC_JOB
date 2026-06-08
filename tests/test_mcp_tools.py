from __future__ import annotations

import unittest

from mcp_server.access_mcp_server import call_tool
from mcp_server.tools.access_options import check_access_options
from mcp_server.tools.asset_inspection import inspect_asset
from mcp_server.tools.cmr import normalize_granule_metadata
from mcp_server.tools.cost_estimator import estimate_subset_cost
from mcp_server.tools.recommendation import build_dataset_facts, recommend_access_pattern


OPERA_GRANULE_FIXTURE = {
    "conceptId": "G4074720639-ASF",
    "dataCenter": "ASF",
    "granuleUr": "OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_20251013T134214Z_v1.0_20260310T213850Z",
    "granuleSize": 364.811,
    "relatedUrls": [
        {
            "url": "https://cumulus.asf.earthdatacloud.nasa.gov/OPERA/example.nc",
            "type": "GET DATA",
            "format": "netCDF-4",
        },
        {
            "url": "s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/example.nc",
            "type": "GET DATA VIA DIRECT ACCESS",
            "format": "netCDF-4",
        },
        {
            "url": "s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/example.zarr.json.gz",
            "type": "GET DATA VIA DIRECT ACCESS",
            "format": "Zarr",
        },
    ],
}


class McpToolTests(unittest.TestCase):
    def test_cmr_granule_fixture_is_normalized(self) -> None:
        facts = normalize_granule_metadata(OPERA_GRANULE_FIXTURE)

        self.assertEqual(facts["provider"], "ASF")
        self.assertEqual(facts["size_mb"], 364.811)
        self.assertEqual(len(facts["s3_urls"]), 2)
        self.assertEqual(len(facts["https_urls"]), 1)
        self.assertIn("zarr", facts["formats"])

    def test_access_options_detect_direct_s3_and_virtual_access(self) -> None:
        metadata = normalize_granule_metadata(OPERA_GRANULE_FIXTURE)
        options = check_access_options(collection="OPERA_L3_DISP-S1_V1", metadata=metadata)

        self.assertTrue(options["direct_s3"])
        self.assertTrue(options["https"])
        self.assertTrue(options["zarr"])
        self.assertTrue(options["virtual_access"])

    def test_asset_inspection_infers_opera_netcdf_shape(self) -> None:
        metadata = normalize_granule_metadata(OPERA_GRANULE_FIXTURE)
        asset = inspect_asset(metadata=metadata)

        self.assertEqual(asset["format"], "netcdf")
        self.assertIn("water_mask", asset["variables"])
        self.assertEqual(asset["dimensions"]["x"], 9548)

    def test_subset_cost_marks_small_window_low_risk(self) -> None:
        cost = estimate_subset_cost(
            dimensions={"y": 7915, "x": 9548},
            subset={"idx_window": "0:1024,0:1024"},
            variables=["water_mask"],
        )

        self.assertEqual(cost["estimated_cells"], 1024 * 1024)
        self.assertEqual(cost["risk"], "low")

    def test_recommendation_prefers_direct_s3_xarray(self) -> None:
        metadata = normalize_granule_metadata(OPERA_GRANULE_FIXTURE)
        asset = inspect_asset(metadata=metadata)
        options = check_access_options(collection="OPERA_L3_DISP-S1_V1", metadata=metadata)
        cost = estimate_subset_cost(
            dimensions=asset["dimensions"],
            subset={"idx_window": "0:1024,0:1024"},
            variables=asset["variables"],
        )
        recommendation = recommend_access_pattern({}, asset, options, cost)

        self.assertEqual(recommendation["recommended_strategies"][0], "direct_s3_xarray")
        self.assertIn("full_download", recommendation["avoid"])

    def test_build_dataset_facts_from_static_evidence(self) -> None:
        evidence = {
            "collections": ["OPERA_L3_DISP-S1_V1"],
            "urls": ["s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/example.nc"],
            "inputs": {"idx_window": {"default": "0:1024,0:1024"}},
        }
        facts = build_dataset_facts(evidence, live=False)

        self.assertEqual(facts["source"], "mcp_ready_local_tools")
        self.assertTrue(facts["access_options"]["direct_s3"])
        self.assertEqual(facts["recommendation"]["recommended_strategies"][0], "direct_s3_xarray")

    def test_mcp_server_registry_dispatches_tool(self) -> None:
        result = call_tool(
            "check_access_options",
            {"urls": ["s3://bucket/file.nc", "https://example/file.nc"]},
        )

        self.assertTrue(result["direct_s3"])
        self.assertTrue(result["https"])


if __name__ == "__main__":
    unittest.main()
