from __future__ import annotations

import argparse
from pathlib import Path

import xarray as xr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_uri", default="s3://example-bucket/sample.nc")
    parser.add_argument("--out_dir", default="output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = xr.open_dataset(args.input_uri)
    dataset.to_zarr(output_dir / "subset.zarr")


if __name__ == "__main__":
    main()
