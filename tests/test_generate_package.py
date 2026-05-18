from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from generator import generate_package as gen


class GeneratePackageTests(unittest.TestCase):
    def test_notebook_parameters_and_magic_are_analyzed(self) -> None:
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {"tags": ["parameters"]},
                    "source": ["threshold = 0.5\n", "product = 'NISAR'\n"],
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": ["%matplotlib inline\n", "result = threshold\n"],
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            notebook_path = Path(tmpdir) / "analysis.ipynb"
            notebook_path.write_text(json.dumps(notebook), encoding="utf-8")

            source_info = gen.read_source_file(notebook_path)
            inputs = gen.infer_inputs(source_info)
            analysis = gen.analyze_source(
                source_info,
                gen.detect_imports_from_source(source_info["source"]),
                inputs,
            )

        self.assertEqual(source_info["kind"], "notebook")
        self.assertEqual(source_info["parameters_cell_index"], 0)
        self.assertEqual(inputs["threshold"]["type"], "float")
        self.assertEqual(inputs["product"]["default"], "NISAR")
        self.assertIn("notebook_magic", {item["rule"] for item in analysis["issues"]})
        self.assertIn("implicit_notebook_state", {item["rule"] for item in analysis["issues"]})

    def test_static_analysis_flags_blocking_patterns(self) -> None:
        source_info = {
            "kind": "script",
            "source": "import os\nvalue = input('bbox')\nopen('/tmp/input.csv')\nsecret = os.getenv('TOKEN')\n",
            "code_units": [],
            "parameters_cell_index": None,
            "magic_lines": [],
        }

        analysis = gen.analyze_source(source_info, ["os"], {})
        rules = {item["rule"] for item in analysis["issues"]}

        self.assertIn("interactive_runtime", rules)
        self.assertIn("hardcoded_local_path", rules)
        self.assertIn("undeclared_environment_dependency", rules)
        self.assertTrue(
            any("/tmp/input.csv" in item["evidence"] for item in analysis["data_access"]["local"])
        )

    def test_manifest_aliases_merge_into_app_config_shape(self) -> None:
        normalized = gen.normalize_manifest_config(
            {
                "target": "ogc_dps",
                "base_container_preference": "example/base:latest",
                "input_schema": {"bbox": {"type": "string"}},
                "output_schema": {"output": {"type": "directory"}},
            }
        )

        self.assertEqual(normalized["target"], "both")
        self.assertEqual(normalized["base_container"], "example/base:latest")
        self.assertIn("bbox", normalized["inputs"])
        self.assertIn("output", normalized["outputs"])

    def test_algorithm_yml_shape_is_normalized(self) -> None:
        normalized = gen.normalize_manifest_config(
            {
                "algorithm_name": "operawatermask1",
                "algorithm_version": "ogc",
                "algorithm_description": "OPERA water mask",
                "code_repository": "https://github.com/MAAP-Project/OPERA_DPS_JOB.git",
                "ram_min": 10,
                "cores_min": 1,
                "inputs": [
                    {
                        "name": "SHORT_NAME",
                        "doc": "CMR short name",
                        "type": "string",
                    }
                ],
                "outputs": [{"name": "out", "type": "Directory"}],
            }
        )

        self.assertEqual(normalized["name"], "operawatermask1")
        self.assertEqual(normalized["version"], "ogc")
        self.assertEqual(normalized["description"], "OPERA water mask")
        self.assertEqual(normalized["resources"]["ram_min"], 10)
        self.assertIn("SHORT_NAME", normalized["inputs"])
        self.assertEqual(normalized["outputs"]["out"]["type"], "Directory")

    def test_openai_llm_analysis_skips_without_key(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            result = gen.run_llm_analysis(
                "{}",
                enabled=True,
                provider="openai",
                model=None,
                openai_model="gpt-4o-mini",
                anthropic_model="claude-3-5-sonnet-latest",
            )
        finally:
            if old_key is not None:
                os.environ["OPENAI_API_KEY"] = old_key

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["provider"], "openai")

    def test_opera_style_dependencies_and_access_are_detected(self) -> None:
        source = """
import xarray as xr
import rioxarray
from maap.maap import MAAP
from s3fs import S3FileSystem

maap = MAAP()
maap.searchCollection(cmr_host="cmr.earthdata.nasa.gov", short_name="OPERA_L3_DISP-S1_V1")
maap.searchGranule(limit=1)
maap.aws.earthdata_s3_credentials("https://cumulus.asf.alaska.edu/s3credentials")
fs = S3FileSystem()
ds = xr.open_dataset("s3://bucket/granule.nc")
ds.rio.to_raster("output/water_mask_subset.cog.tif", driver="COG")
"""
        imports = gen.detect_imports_from_source(source)
        implicit = gen.detect_implicit_dependencies_from_source(source, imports)
        analysis = gen.analyze_source(
            {
                "kind": "script",
                "source": source,
                "code_units": [],
                "parameters_cell_index": None,
                "magic_lines": [],
            },
            imports,
            {},
        )

        self.assertIn("rioxarray", imports)
        self.assertIn("rasterio", implicit["conda"])
        self.assertIn("netcdf4", implicit["conda"])
        self.assertGreaterEqual(len(analysis["data_access"]["cmr"]), 1)
        self.assertGreaterEqual(len(analysis["data_access"]["s3"]), 1)


if __name__ == "__main__":
    unittest.main()
