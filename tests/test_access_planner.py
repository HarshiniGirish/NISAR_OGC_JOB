from __future__ import annotations

import unittest

from generator.access_evidence import build_access_evidence
from generator.access_plan_validator import validate_access_plan
from generator.access_planner import plan_access, rule_based_access_plan


class AccessPlannerTests(unittest.TestCase):
    def test_opera_s3_netcdf_recommends_direct_s3_xarray(self) -> None:
        source_info = {
            "kind": "script",
            "path": "input/opera_access_structure.py",
            "source": """
import xarray as xr
from s3fs import S3FileSystem
url = "s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/example.nc"
ds = xr.open_dataset(url, chunks="auto")
wm = ds["water_mask"].isel(y=slice(0, 1024), x=slice(0, 1024))
wm.rio.to_raster("output/water_mask_subset.cog.tif", driver="COG")
""",
        }
        app_config = {
            "entrypoint": "opera_water_mask_to_cog.py",
            "inputs": {"idx_window": {"default": "0:1024,0:1024"}},
            "outputs": {"output": {"type": "directory"}},
            "resources": {},
        }
        analysis = {
            "data_access": {
                "s3": [{"evidence": "s3://asf-cumulus-prod-opera-products/example.nc"}],
                "cmr": [],
                "stac": [],
                "local": [],
            },
            "issues": [],
        }

        evidence = build_access_evidence(
            source_info=source_info,
            app_config=app_config,
            analysis=analysis,
            detected_imports=["xarray", "s3fs", "rioxarray"],
        )
        plan = rule_based_access_plan(evidence)

        self.assertEqual(plan["chosen_strategy"], "direct_s3_xarray")
        self.assertIn("netcdf", evidence["file_formats"])
        self.assertIn("index_subset", evidence["operations"])

    def test_nisar_hdf5_recommends_direct_s3_h5py(self) -> None:
        source_info = {
            "kind": "script",
            "path": "input/nisar_access_subset.py",
            "source": """
import h5py
import s3fs
s3_href = "s3://bucket/granule.h5"
with h5py.File("granule.h5") as h5f:
    arr = h5f["/science/LSAR/GCOV/grids/frequencyA/HHHH"]
""",
        }
        evidence = build_access_evidence(
            source_info=source_info,
            app_config={"entrypoint": "nisar_access_subset.py", "inputs": {"bbox": {}}, "outputs": {}},
            analysis={
                "data_access": {
                    "s3": [{"evidence": "s3://bucket/granule.h5"}],
                    "cmr": [],
                    "stac": [],
                    "local": [],
                },
                "issues": [],
            },
            detected_imports=["h5py", "s3fs"],
        )
        plan = rule_based_access_plan(evidence)

        self.assertEqual(plan["chosen_strategy"], "direct_s3_h5py")

    def test_invalid_ai_plan_is_rejected(self) -> None:
        validation = validate_access_plan(
            {"chosen_strategy": "run_arbitrary_shell", "required_dependencies": []},
            {"file_formats": ["netcdf"]},
        )

        self.assertFalse(validation["valid"])
        self.assertIn("Unsupported strategy", validation["errors"][0])

    def test_planner_falls_back_when_ai_not_requested(self) -> None:
        plan = plan_access(
            evidence={
                "imports": ["xarray", "s3fs"],
                "urls": ["s3://bucket/file.nc"],
                "file_formats": ["netcdf"],
                "operations": ["direct_s3", "index_subset"],
                "issues": [],
            },
            enabled=False,
            provider="openai",
            model="gpt-4o-mini",
        )

        self.assertEqual(plan["source"], "rule_based")
        self.assertEqual(plan["chosen_strategy"], "direct_s3_xarray")
        self.assertFalse(plan["fallback_used"])

    def test_veda_black_marble_recommends_stac_raster_api(self) -> None:
        source_info = {
            "kind": "script",
            "path": "input/black_marble_veda.py",
            "source": """
import requests
from pystac_client import Client
STAC_API_URL = "https://openveda.cloud/api/stac"
RASTER_API_URL = "https://openveda.cloud/api/raster"
client = Client.open(STAC_API_URL)
response = requests.get(f"{RASTER_API_URL}/collections/lakeview-nightlights-tornadoes-2024/items/item/WebMercatorQuad/tilejson.json")
""",
        }
        evidence = build_access_evidence(
            source_info=source_info,
            app_config={
                "entrypoint": "black_marble_veda.py",
                "inputs": {"collection_id": {"default": "lakeview-nightlights-tornadoes-2024"}},
                "outputs": {},
            },
            analysis={
                "data_access": {
                    "s3": [],
                    "cmr": [],
                    "stac": [{"evidence": "https://openveda.cloud/api/stac"}],
                    "local": [],
                },
                "issues": [],
            },
            detected_imports=["requests", "pystac_client"],
        )
        plan = rule_based_access_plan(
            evidence,
            {"access_options": {"raster_api": True}, "asset_inspection": {"format": "tilejson"}},
        )

        self.assertIn("raster_api", evidence["operations"])
        self.assertIn("tilejson", evidence["file_formats"])
        self.assertEqual(plan["chosen_strategy"], "stac_raster_api")


if __name__ == "__main__":
    unittest.main()
