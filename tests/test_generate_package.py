from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
