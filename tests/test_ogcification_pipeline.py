from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from generator.dependency_graph import build_dependency_graph
from generator.dps_readiness_scan import scan_dps_readiness
from generator.llm_recommendations import (
    build_structured_recommendations,
    validate_recommendation_schema,
)
from generator.ogc_validator import validate_generated_package
from generator.suggested_notebook_v2 import emit_suggested_notebook_v2
from generator.suggested_notebook_v2 import _transform_source
from mcp_server.tools.default_resolver import resolve_default_values


class OgcificationPipelineTests(unittest.TestCase):
    def test_script_readiness_scanner_flags_hardcoded_path_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "workflow.py"
            script.write_text(
                """
import xarray as xr

def process():
    ds = xr.open_dataset('/tmp/input.nc')
    ds.to_zarr('output/subset.zarr')
""",
                encoding="utf-8",
            )

            scan = scan_dps_readiness(script, {})

        classifications = {unit["classification"] for unit in scan["units"]}
        self.assertIn("DPS-candidate-after-refactor", classifications)
        self.assertGreater(scan["summary"]["dps_suitability_score"], 0)
        self.assertTrue(
            any("/tmp/input.nc" in unit["hardcoded_values"] for unit in scan["units"])
        )

    def test_notebook_readiness_scanner_detects_plotting_cell(self) -> None:
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {"tags": ["parameters"]},
                    "source": ["bbox = ''\n"],
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": ["import matplotlib.pyplot as plt\n", "plt.show()\n"],
                },
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "analysis.ipynb"
            path.write_text(json.dumps(notebook), encoding="utf-8")
            scan = scan_dps_readiness(path, {})

        self.assertIn(
            "Notebook-only",
            {unit["classification"] for unit in scan["units"]},
        )

    def test_mcp_default_resolver_returns_provenance(self) -> None:
        result = resolve_default_values(
            evidence={
                "urls": ["s3://bucket/OPERA_L3_DISP-S1_V1/example.nc"],
                "operations": ["direct_s3"],
                "collections": ["OPERA_L3_DISP-S1_V1"],
            },
            dataset_facts={"live_metadata": False, "asset_inspection": {"variables": ["water_mask"]}},
            user_config={"inputs": {"bbox": {"default": "-1,-1,1,1"}}},
            stac_url="https://stac-browser.maap-project.org/?.language=en",
        )

        suggestions = {item["parameter"]: item for item in result["suggestions"]}
        self.assertEqual(suggestions["bbox"]["source"], "user app.yaml")
        self.assertEqual(suggestions["access_mode"]["suggested_value"], "s3")
        self.assertIn("source", suggestions["variables"])

    def test_dependency_graph_validates_known_and_rejects_unknown_llm_packages(self) -> None:
        graph = build_dependency_graph(
            detected_imports=["xarray", "unknown_module"],
            dependency_map={"xarray": "xarray", "unknown_module": None},
            implicit_dependencies={"conda": ["zarr<3"], "pip": []},
            resolved_dependencies={"conda": ["python=3.11", "xarray", "zarr<3"], "pip": []},
            source="ds.to_zarr('output/data.zarr')",
            llm_suggestions=["xarray", "definitely-not-a-real-package-for-test"],
        )

        self.assertEqual(graph["summary"]["validated_llm_suggestion_count"], 1)
        self.assertEqual(graph["summary"]["rejected_llm_suggestion_count"], 1)
        self.assertTrue(any(edge["trusted"] for edge in graph["edges"]))

    def test_llm_recommendation_schema_and_rule_based_fallback(self) -> None:
        payload = {
            "recommended_entrypoint": "main",
            "candidate_functions": [],
            "notebook_only_cells": [],
            "required_refactors": [],
            "suggested_inputs": [],
            "suggested_outputs": ["output"],
            "risks_warnings": [],
            "confidence_score": 0.8,
        }
        self.assertTrue(validate_recommendation_schema(payload)["valid"])
        recommendations = build_structured_recommendations(
            readiness_scan={
                "summary": {"dps_suitability_score": 80, "blocking_count": 0},
                "units": [
                    {
                        "name": "process",
                        "classification": "DPS-ready",
                        "dps_suitability_score": 90,
                        "reason": "writes output",
                        "detected_outputs": ["to_zarr"],
                    }
                ],
            },
            enabled=False,
        )
        self.assertEqual(recommendations["recommended_entrypoint"], "process")

    def test_ogc_validator_reports_pass_and_fail_cases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            package = Path(tmpdir)
            for name in ("run.sh", "build.sh", "Dockerfile", "application.cwl", "workflow.cwl"):
                (package / name).write_text("output\n", encoding="utf-8")
            (package / "env.yml").write_text("name: test\n", encoding="utf-8")
            (package / "algorithm.yml").write_text("inputs: []\n", encoding="utf-8")
            (package / "algorithm_config.yaml").write_text("inputs: []\n", encoding="utf-8")
            (package / "app.yaml").write_text(
                yaml.safe_dump({"input_schema": {"bbox": {"description": "bbox"}}}),
                encoding="utf-8",
            )

            report = validate_generated_package(package, target="both")

        self.assertFalse(any("Missing required file" in item for item in report["blocking_issues"]))

        with tempfile.TemporaryDirectory() as tmpdir:
            report = validate_generated_package(tmpdir, target="ogc")
        self.assertTrue(report["blocking_issues"])

    def test_suggested_notebook_v2_is_non_destructive(self) -> None:
        notebook = {
            "cells": [
                {"cell_type": "code", "metadata": {}, "source": ["import requests\n"]},
                {"cell_type": "code", "metadata": {}, "source": ["print('science')\n"]},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "analysis.ipynb"
            original_text = json.dumps(notebook)
            path.write_text(original_text, encoding="utf-8")
            report = emit_suggested_notebook_v2(
                path,
                tmpdir,
                readiness_scan={"units": [{"index": 0, "classification": "DPS-ready", "name": "cell 0"}]},
                recommendations={"suggested_inputs": [{"name": "bbox"}]},
                mcp_defaults={"suggestions": [{"parameter": "bbox", "suggested_value": ""}]},
            )

            self.assertEqual(path.read_text(encoding="utf-8"), original_text)
            self.assertTrue(Path(report["suggested_v2_notebook_path"]).exists())
            self.assertTrue((Path(tmpdir) / "notebook_v2_diff_report.json").exists())
            suggested = json.loads(Path(report["suggested_v2_notebook_path"]).read_text(encoding="utf-8"))
            suggested_source = "\n".join(
                "".join(cell.get("source", []))
                for cell in suggested["cells"]
                if cell.get("cell_type") == "code"
            )
            self.assertIn("import requests", suggested_source)
            self.assertIn(0, report["preserved_setup_cells"])

    def test_suggested_notebook_v2_rewrites_brittle_stac_asset_lookup(self) -> None:
        transformed = _transform_source("url = items_response['assets']['mean']['href']\n")

        self.assertIn("extract_asset_href", transformed)
        self.assertNotIn("['assets']['mean']['href']", transformed)

    def test_generator_cli_emits_new_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "generated"
            command = [
                sys.executable,
                "generator/generate_package.py",
                "--input",
                "input/nisar_access_subset.py",
                "--scan-dps-readiness",
                "--use-mcp-defaults",
                "--llm-recommendations",
                "--build-dependency-graph",
                "--validate-ogc",
                "--output-dir",
                str(output_dir),
            ]
            result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], check=False)

            self.assertEqual(result.returncode, 0)
            self.assertTrue((output_dir / "dps_readiness_report.json").exists())
            self.assertTrue((output_dir / "dependency_graph.json").exists())
            self.assertTrue((output_dir / "mcp_default_suggestions.json").exists())
            self.assertTrue((output_dir / "llm_recommendations.json").exists())
            self.assertTrue((output_dir / "ogc_validation_report.json").exists())
            self.assertTrue((output_dir / "final_readiness_report.json").exists())


if __name__ == "__main__":
    unittest.main()
