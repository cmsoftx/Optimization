# Raw data (not committed)

Dataset: **DataCo Smart Supply Chain for Big Data Analysis**
(Kaggle: `shashwatwork/dataco-smart-supply-chain-for-big-data-analysis`).

Expected files after download/extraction:

| File | Size | Used by this project |
|---|---|---|
| `DataCoSupplyChainDataset.csv` | ~96 MB, 180,519 rows × 53 cols, Latin-1 encoded | Yes: primary order-item table |
| `DescriptionDataCoSupplyChain.csv` | 3 KB | Yes: data dictionary |
| `tokenized_access_logs.csv` | ~95 MB, 469,977 rows × 8 cols | Inspected only (web click-stream; no geography/quantities) |

## Option A: Kaggle API

1. Create an API token at kaggle.com → Settings → API → *Create New Token*.
2. Place `kaggle.json` in `~/.kaggle/` (chmod 600) **or** export
   `KAGGLE_USERNAME` and `KAGGLE_KEY`.
3. Run `python main.py download`.

Alternatively: `kaggle datasets download -d shashwatwork/dataco-smart-supply-chain-for-big-data-analysis -p data/raw --unzip`

## Option B: Manual upload

Download the zip from the Kaggle page in a browser, then either place the
extracted CSVs in this folder, or run:

    python main.py download --zip /path/to/archive.zip

The files contain customer first/last names and street addresses (emails
and passwords are masked as `XXXXXXXXX`). Keep them local; the pipeline
drops these columns from every processed output.
