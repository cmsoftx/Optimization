"""Command-line entry point for the optimisation pipeline.

Phases are added incrementally. Currently available:

    python main.py download [--zip PATH] [--force]   # acquire the Kaggle dataset
    python main.py inspect                            # Phase 1 dataset inspection
    python main.py preprocess                         # Phase 2 cleaning, zones, EDA
    python main.py forecast                           # Phase 3 demand forecasting
    python main.py warehouse                          # Phase 4 CFLP (Pyomo + CBC)
    python main.py genetic                            # Phase 5 GA vs CFLP vs K-Means vs random
    python main.py routing                            # Phase 6 CVRP: NN / OR-Tools / Guided Local Search
    python main.py evaluate [--quick]                 # Phase 8 experiments A-E, checks, figures
    python main.py report                             # Phase 10 final report, viva questions, presentation
    python main.py all [--force]                      # whole pipeline (reuses valid Phase 2/3 outputs)
    streamlit run dashboard/app.py                    # Phase 9 dashboard
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


def cmd_forecast(_: argparse.Namespace) -> int:
    import pandas as pd

    from src.config import get_path
    from src.forecasting import run_phase3
    from src.reports import write_phase3_report
    from src.visualization import make_phase3_figures

    proc = get_path("processed_dir")
    zd = pd.read_csv(proc / "zone_daily_demand.csv", parse_dates=["date"])
    zones = pd.read_csv(proc / "demand_zones.csv")
    res = run_phase3(zd, zones, write=True)
    pw = res.runs["W"].predictions
    figs = make_phase3_figures(pw, None, res.evaluation, res.importance, res.selection, res.cflp)
    write_phase3_report(res)
    print(res.selection.to_string(index=False))
    print(f"{len(figs)} figures written; report: reports/phase3_forecasting_report.md")
    return 0


def cmd_warehouse(_: argparse.Namespace) -> int:
    from src.pipeline import run_warehouse

    for net, (prob, sol) in run_warehouse().items():
        print(f"{net}: {sol.n_open} warehouses, objective {sol.objective:,.2f} USD/week, "
              f"termination={sol.termination}, gap={sol.gap:.2e}, {sol.runtime_s:.1f}s")
    return 0


def cmd_genetic(_: argparse.Namespace) -> int:
    from src.pipeline import run_genetic

    c = run_genetic()["comparison"]
    print(c[["network", "method", "n_open", "total_cost", "gap_vs_cflp_pct", "feasible", "runtime_s"]].to_string(index=False))
    return 0


def cmd_routing(args: argparse.Namespace) -> int:
    from src.pipeline import run_routing

    c = run_routing(time_limit_s=args.time_limit)["comparison"]
    print(c[["network", "method", "vehicles", "total_distance_km", "total_duration_h", "all_feasible", "runtime_s"]].to_string(index=False))
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from src.pipeline import run_evaluate

    r = run_evaluate(run_experiments=not args.quick)
    print(f"consistency checks: {int(r['checks']['passed'].sum())}/{len(r['checks'])} passed; "
          f"{len(r['figures'])} figures; summary rows: {len(r['summary'])}")
    return 0


def cmd_report(_: argparse.Namespace) -> int:
    from src.final_reports import write_all_reports

    for p in write_all_reports():
        print("written:", p)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    from src.config import get_path

    proc, out = get_path("processed_dir"), get_path("outputs_dir")
    if args.force or not (proc / "zone_daily_demand.csv").exists():
        cmd_preprocess(args)
    if args.force or not (out / "cflp_zone_demand_forecast.csv").exists() or not (out / "unit_demand_predictions.csv").exists():
        cmd_forecast(args)
    for f in (cmd_warehouse, cmd_genetic, cmd_routing, cmd_evaluate, cmd_report):
        f(args)
    return 0


def main(argv: list[str] | None = None) -> int:
    from src.config import get_path

    log_dir = get_path("reports_dir") / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "pipeline.log")])
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("download", help="Download/extract the DataCo dataset")
    d.add_argument("--zip", help="Path to a manually downloaded Kaggle zip")
    d.add_argument("--force", action="store_true", help="Re-download even if present")
    d.set_defaults(func=cmd_download)
    sub.add_parser("inspect", help="Phase 1: dataset inspection").set_defaults(func=cmd_inspect)
    sub.add_parser("preprocess", help="Phase 2: cleaning, demand zones, EDA").set_defaults(func=cmd_preprocess)
    sub.add_parser("forecast", help="Phase 3: demand forecasting").set_defaults(func=cmd_forecast)
    sub.add_parser("warehouse", help="Phase 4: CFLP").set_defaults(func=cmd_warehouse)
    sub.add_parser("genetic", help="Phase 5: genetic algorithm and baselines").set_defaults(func=cmd_genetic)
    r = sub.add_parser("routing", help="Phase 6: CVRP")
    r.add_argument("--time-limit", type=float, default=None, help="GLS seconds per depot (default from config)")
    r.set_defaults(func=cmd_routing)
    e = sub.add_parser("evaluate", help="Phase 8: experiments, checks, figures")
    e.add_argument("--quick", action="store_true", help="skip experiments C-E (reuse saved results)")
    e.set_defaults(func=cmd_evaluate)
    sub.add_parser("report", help="Phase 10: final documents").set_defaults(func=cmd_report)
    a = sub.add_parser("all", help="run the full pipeline")
    a.add_argument("--force", action="store_true", help="also rerun preprocessing and forecasting")
    a.add_argument("--quick", action="store_true", help="skip experiments C-E")
    a.add_argument("--time-limit", type=float, default=None)
    a.set_defaults(func=cmd_all)
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (DatasetNotFoundError, FileNotFoundError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
