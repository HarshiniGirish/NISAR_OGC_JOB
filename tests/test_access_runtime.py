from __future__ import annotations

import unittest

from generator.access_runtime import build_access_runtime_module
from generator.generate_package import add_access_plan_dependencies


class AccessRuntimeTests(unittest.TestCase):
    def test_direct_s3_xarray_runtime_helper_is_rendered(self) -> None:
        module = build_access_runtime_module(
            {
                "chosen_strategy": "direct_s3_xarray",
                "source": "rule_based",
                "implementation_hints": ["Open with xarray chunks."],
                "warnings": [],
            },
            {
                "source": "mcp_ready_local_tools",
                "asset_inspection": {"format": "netcdf", "variables": ["water_mask"]},
                "access_options": {"direct_s3": True},
                "subset_cost": {"risk": "low"},
            },
        )

        self.assertIn('ACCESS_STRATEGY = "direct_s3_xarray"', module)
        self.assertIn("def open_xarray_dataset_from_s3", module)
        self.assertIn("xr.open_dataset", module)
        self.assertIn("s3fs.S3FileSystem", module)

    def test_direct_s3_h5py_runtime_helper_is_rendered(self) -> None:
        module = build_access_runtime_module(
            {"chosen_strategy": "direct_s3_h5py", "source": "rule_based"},
            {"asset_inspection": {"format": "hdf5"}},
        )

        self.assertIn("def download_s3_asset_to_tempfile", module)
        self.assertIn("def open_hdf5_file", module)
        self.assertIn("h5py.File", module)

    def test_access_plan_dependencies_are_added_to_environment(self) -> None:
        dependencies = add_access_plan_dependencies(
            {"conda": ["python=3.11"], "pip": []},
            {"required_dependencies": ["s3fs", "xarray"]},
        )

        self.assertIn("s3fs", dependencies["conda"])
        self.assertIn("xarray", dependencies["conda"])
        self.assertEqual(dependencies["pip"], [])

    def test_stac_raster_api_runtime_helper_is_rendered(self) -> None:
        module = build_access_runtime_module(
            {
                "chosen_strategy": "stac_raster_api",
                "source": "rule_based",
                "implementation_hints": ["Use raster API TileJSON endpoint."],
                "warnings": [],
            },
            {
                "source": "mcp_ready_local_tools",
                "asset_inspection": {"format": "tilejson", "variables": []},
                "access_options": {"stac": True, "raster_api": True},
            },
        )

        self.assertIn('ACCESS_STRATEGY = "stac_raster_api"', module)
        self.assertIn("def fetch_stac_item_tilejson", module)
        self.assertIn("Client.open", module)


if __name__ == "__main__":
    unittest.main()
