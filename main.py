"""Command-line entry point for the optimisation pipeline.

Phases are added incrementally. Currently available:

    python main.py download [--zip PATH] [--force]   # acquire the Kaggle dataset
    python main.py inspect                            # Phase 1 dataset inspection
    python main.py preprocess                         # Phase 2 cleaning, zones, EDA
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


def cmd_preprocess(_: argparse.Namespace) -> int:
    from src.demand_analytics import run_demand_analytics
    from src.preprocessing import run_preprocessing
    from src.reports import write_phase2_report
    from src.visualization import make_phase2_figures

    pre = run_preprocessing(write=True)
    tables = run_demand_analytics(pre.items, pre.orders, pre.zones, pre.zone_daily, write=True)
    figs = make_phase2_figures(pre.zones, pre.zone_daily, tables)
    write_phase2_report(pre, tables)
    rec = pre.reconciliation
    print(f"Reconciliation: {int(rec['passed'].sum())}/{len(rec)} checks passed")
    print(pre.zones.groupby("network").agg(zones=("zone_id", "size"), orders=("n_orders", "sum"),
                                           units=("units", "sum")).to_string())
    print(f"{len(figs)} figures written; report: reports/phase2_preprocessing_eda.md")
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
    sub.add_parser("preprocess", help="Phase 2: cleaning, demand zones, EDA").set_defaults(func=cmd_preprocess)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except DatasetNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
