"""Command-line entry point for the optimisation pipeline.

Phases are added incrementally. Currently available:

    python main.py download [--zip PATH] [--force]   # acquire the Kaggle dataset
    python main.py inspect                            # Phase 1 dataset inspection
"""
from __future__ import annotations

import argparse
import logging
import sys

from src.data_loader import DatasetNotFoundError, download_dataset, extract_zip


def cmd_download(args: argparse.Namespace) -> int:
    if args.zip:
        files = extract_zip(args.zip)
        print("Extracted:", *[str(p) for p in files], sep="\n  ")
    else:
        print("Dataset at", download_dataset(force=args.force))
    return 0


def cmd_inspect(_: argparse.Namespace) -> int:
    from src.data_inspection import run_inspection

    r = run_inspection(write=True)
    print(f"Rows x cols: {r.shape}; orders: {r.facts['orders']:,}; customers: {r.facts['customers']:,}")
    print(r.integrity[r.integrity["violations"] > 0].to_string(index=False))
    print(r.coord_summary.to_string(index=False))
    print(r.regions.to_string(index=False))
    print("Report: reports/phase1_dataset_inspection.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("download", help="Download/extract the DataCo dataset")
    d.add_argument("--zip", help="Path to a manually downloaded Kaggle zip")
    d.add_argument("--force", action="store_true", help="Re-download even if present")
    d.set_defaults(func=cmd_download)
    sub.add_parser("inspect", help="Phase 1: dataset inspection").set_defaults(func=cmd_inspect)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except DatasetNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
