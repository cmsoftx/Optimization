"""Dataset acquisition and loading for the DataCo Smart Supply Chain dataset.

Responsibilities
----------------
* Download the dataset from Kaggle (official API or authenticated HTTP) or
  ingest a manually downloaded zip.
* Load the order-item table with the correct encoding and parsed dates.
* Never invent columns: every column name used downstream is validated
  against the file actually loaded.
"""
from __future__ import annotations

import base64
import logging
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .config import get_path, load_config

log = logging.getLogger(__name__)

KAGGLE_DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/{ref}"

# Columns that the downstream pipeline relies on. Verified against the real file
# (see reports/phase1_dataset_inspection.md); loading fails loudly if absent.
REQUIRED_COLUMNS = [
    "Order Id", "Order Item Id", "Order Customer Id", "Customer Id",
    "order date (DateOrders)", "shipping date (DateOrders)",
    "Order Item Quantity", "Sales", "Order Item Total",
    "Category Name", "Department Name", "Product Name",
    "Customer City", "Customer State", "Customer Country", "Customer Zipcode",
    "Latitude", "Longitude",
    "Order City", "Order State", "Order Country", "Order Region", "Market",
    "Shipping Mode", "Days for shipping (real)", "Days for shipment (scheduled)",
    "Delivery Status", "Late_delivery_risk", "Order Status",
]
DATE_COLUMNS = ["order date (DateOrders)", "shipping date (DateOrders)"]


class DatasetNotFoundError(FileNotFoundError):
    """Raised when the raw dataset is missing, with acquisition instructions."""


# Acquisition
def _expected_files() -> list[str]:
    ds = load_config()["dataset"]
    return [ds["main_file"], ds["description_file"], ds["access_log_file"]]


def extract_zip(zip_path: str | Path, dest: str | Path | None = None) -> list[Path]:
    """Safely extract the expected CSVs from a Kaggle zip archive.

    Only the known dataset files are extracted, and member paths are
    sanitised to prevent path traversal.
    """
    zip_path = Path(zip_path)
    dest = Path(dest) if dest else get_path("raw_dir")
    dest.mkdir(parents=True, exist_ok=True)
    wanted = set(_expected_files())
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            name = Path(member.filename).name  # strip any directory component
            if name not in wanted:
                log.info("Skipping unexpected archive member %s", member.filename)
                continue
            target = dest / name
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    missing = wanted - {p.name for p in extracted}
    if Path(load_config()["dataset"]["main_file"]).name in missing:
        raise DatasetNotFoundError(f"Archive {zip_path} does not contain the main dataset file")
    return extracted


def download_dataset(dest: str | Path | None = None, force: bool = False) -> Path:
    """Download the dataset from Kaggle and extract it into ``data/raw``.

    Strategy:
      1. If the main CSV already exists and ``force`` is False, do nothing.
      2. Try the official ``kaggle`` package (uses ~/.kaggle/kaggle.json or
         KAGGLE_USERNAME / KAGGLE_KEY).
      3. Fall back to an authenticated HTTPS request to the Kaggle REST API.
    """
    cfg = load_config()["dataset"]
    dest = Path(dest) if dest else get_path("raw_dir")
    main_csv = dest / cfg["main_file"]
    if main_csv.exists() and not force:
        log.info("Dataset already present at %s", main_csv)
        return main_csv

    ref = cfg["kaggle_ref"]
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: WPS433

        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(ref, path=str(dest), unzip=False, quiet=False)
        zips = sorted(dest.glob("*.zip"), key=os.path.getmtime)
        if not zips:
            raise RuntimeError("Kaggle API reported success but no zip was written")
        extract_zip(zips[-1], dest)
        return main_csv
    except Exception as exc:  # pragma: no cover - depends on credentials/network
        log.warning("Kaggle package download failed (%s); trying HTTPS API", exc)

    zip_path = dest / "dataco.zip"
    req = urllib.request.Request(KAGGLE_DOWNLOAD_URL.format(ref=ref))
    user, key = os.environ.get("KAGGLE_USERNAME"), os.environ.get("KAGGLE_KEY")
    if user and key:
        token = base64.b64encode(f"{user}:{key}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp, zip_path.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
    except Exception as exc:
        raise DatasetNotFoundError(
            "Could not download the dataset from Kaggle. Either configure Kaggle API "
            "credentials (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY) or "
            "download the zip manually and run `python main.py download --zip <file>`. "
            f"Underlying error: {exc}"
        ) from exc
    extract_zip(zip_path, dest)
    return main_csv


# Loading
def raw_file_path(key: str = "main_file") -> Path:
    """Absolute path of a raw dataset file; raises with instructions if missing."""
    path = get_path("raw_dir") / load_config()["dataset"][key]
    if not path.exists():
        raise DatasetNotFoundError(
            f"{path} not found. Run `python main.py download` (Kaggle API) or place the "
            "CSV files from the Kaggle archive in data/raw/ (see data/raw/README.md)."
        )
    return path


def validate_columns(df: pd.DataFrame, required: list[str] | None = None) -> None:
    """Ensure every column the pipeline relies on exists in the loaded file."""
    required = required or REQUIRED_COLUMNS
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Dataset is missing expected columns: {missing}")


def load_raw_orders(path: str | Path | None = None, parse_dates: bool = True,
                    drop_pii: bool = False, nrows: int | None = None) -> pd.DataFrame:
    """Load the order-item level table exactly as published.

    Parameters
    ----------
    path : optional explicit CSV path (defaults to ``data/raw/<main_file>``).
    parse_dates : parse the two ``(DateOrders)`` columns to ``datetime64``.
    drop_pii : drop customer names/street/email/password columns.
    nrows : read only the first ``nrows`` rows (testing).
    """
    cfg = load_config()["dataset"]
    path = Path(path) if path else raw_file_path("main_file")
    df = pd.read_csv(path, encoding=cfg["encoding"], nrows=nrows, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    validate_columns(df)
    if parse_dates:
        for col in DATE_COLUMNS:
            df[col] = pd.to_datetime(df[col], format=cfg["date_format"], errors="coerce")
    if drop_pii:
        df = df.drop(columns=[c for c in cfg["pii_columns"] if c in df.columns])
    return df


def load_data_dictionary(path: str | Path | None = None) -> pd.DataFrame:
    """Load the publisher's field description file as a tidy table."""
    path = Path(path) if path else raw_file_path("description_file")
    dd = pd.read_csv(path, encoding="latin-1")
    dd.columns = ["field", "description"]
    dd["field"] = dd["field"].str.strip()
    dd["description"] = dd["description"].str.lstrip(": ").str.strip()
    return dd


def load_access_logs(path: str | Path | None = None, nrows: int | None = None) -> pd.DataFrame:
    """Load the web access log table (inspected only; not used for optimisation)."""
    path = Path(path) if path else raw_file_path("access_log_file")
    return pd.read_csv(path, nrows=nrows)
