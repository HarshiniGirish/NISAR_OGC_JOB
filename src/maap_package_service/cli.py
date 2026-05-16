from __future__ import annotations

import argparse
import json
from pathlib import Path

from maap_package_service.analysis import analyze_artifact
from maap_package_service.generator import generate_packages
from maap_package_service.manifest import load_manifest
from maap_package_service.reporting import write_analysis_report
from maap_package_service.validation import validate_cwl


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Analyze scripts/notebooks and generate MAAP DPS or OGC packages."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Run static analysis.")
    analyze_parser.add_argument("artifact", help="Python script or notebook to analyze.")
    analyze_parser.add_argument("--app", required=True, help="Path to app.yaml.")
    analyze_parser.add_argument("--out", default="", help="Optional JSON report path.")

    generate_parser = subparsers.add_parser("generate", help="Generate target packages.")
    generate_parser.add_argument("artifact", help="Python script or notebook to package.")
    generate_parser.add_argument("--app", required=True, help="Path to app.yaml.")
    generate_parser.add_argument("--out", default="generated", help="Output directory.")
    generate_parser.add_argument(
        "--target",
        choices=["dps", "ogc", "both"],
        default=None,
        help="Override manifest target.",
    )

    validate_parser = subparsers.add_parser("validate-cwl", help="Validate CWL with cwltool.")
    validate_parser.add_argument("cwl", help="Path to commandline.cwl or workflow.cwl.")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        manifest = load_manifest(args.app)
        report = analyze_artifact(args.artifact, manifest)
        if args.out:
            write_analysis_report(report, args.out)
            print(f"Wrote analysis report to {args.out}")
        else:
            print(report.to_json())
        return

    if args.command == "generate":
        manifest = load_manifest(args.app)
        generated = generate_packages(args.artifact, manifest, args.out, args.target)
        for target, paths in generated.items():
            print(f"Generated {target} package:")
            for path in paths:
                print(f" - {Path(path)}")
        return

    if args.command == "validate-cwl":
        result = validate_cwl(args.cwl)
        print(json.dumps(result.to_dict(), indent=2))
        raise SystemExit(0 if result.status in {"passed", "skipped"} else 1)


if __name__ == "__main__":
    main()
