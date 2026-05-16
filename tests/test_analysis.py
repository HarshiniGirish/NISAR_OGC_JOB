from __future__ import annotations

from maap_package_service.analysis import analyze_artifact


def test_analysis_flags_hardcoded_local_paths(tmp_path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("import pandas as pd\npd.read_csv('/home/user/data.csv')\n", encoding="utf-8")

    report = analyze_artifact(script)

    assert "pandas" in report.imports
    assert any(finding.rule == "hardcoded-local-path" for finding in report.findings)
    assert report.has_blocking_findings()


def test_analysis_detects_missing_seed(tmp_path) -> None:
    script = tmp_path / "random_code.py"
    script.write_text("import random\nvalue = random.random()\n", encoding="utf-8")

    report = analyze_artifact(script)

    assert any(finding.rule == "missing-random-seed" for finding in report.findings)
